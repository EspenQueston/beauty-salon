"""Ce que l'audit de securite a corrige, tenu par des tests.

Un test par correction, pour que la faille ne revienne pas sans bruit :

  - un fichier televerse ne garde jamais l'extension qu'il pretend : un
    `page.html` annonce en image sort en `.png`, jamais en page HTML ;
  - les preuves de versement n'entrent pas dans la mediatheque ;
  - la preuve d'un paiement d'abonnement ne se lit que par le proprietaire ;
  - ce que le salon paie a la plateforme ne s'affiche pas a l'equipe ;
  - une reference de paiement ne porte pas de caractere de controle ;
  - les exemptions de l'abonnement s'arretent au segment de chemin ;
  - factures, offres et tarifs ne se reecrivent pas depuis l'administration.
"""

import io
from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from apps.accounts.models import Membership
from apps.billing.middleware import _permise
from apps.billing.models import (
    Invoice,
    Plan,
    PlanPrice,
    Subscription,
    chemin_qr,
    type_du_qr,
)
from apps.media.models import MediaAsset, upload_to
from conftest import as_tenant
from tests.factories import MembershipFactory, UserFactory
from tests.test_abonnements import (
    ADMIN,
    _admin,
    _demande,
    abonnement_de,
    declarer,
    medias_temporaires,
    moyens,
    offres,
    png,
)

FIXTURES_PARTAGEES = (medias_temporaires, moyens, offres)


def image_png(nom: str, content_type: str = "image/png") -> SimpleUploadedFile:
    tampon = io.BytesIO()
    Image.new("RGB", (8, 8), "white").save(tampon, format="PNG")
    return SimpleUploadedFile(nom, tampon.getvalue(), content_type=content_type)


def equipier(salon, role=Membership.Role.MANAGER):
    user = UserFactory()
    MembershipFactory(tenant=salon.tenant, user=user, role=role)
    return user


# ---------------------------------------------------------------------------
# Televersements : l'extension vient du type verifie
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("nom", "type_mime", "attendu"),
    [
        ("page.html", "image/png", ".png"),
        ("../../etc/x.svg", "image/jpeg", ".jpg"),
        ("clip.php", "video/mp4", ".mp4"),
        ("<script>.webp", "image/webp", ".webp"),
        ("inconnu.exe", "application/x-msdownload", ".bin"),
    ],
)
def test_le_nom_range_ne_reprend_jamais_l_extension_televersee(nom, type_mime, attendu):
    asset = MediaAsset(
        tenant_id="00000000-0000-0000-0000-000000000001",
        content_type=type_mime,
        visibility=MediaAsset.Visibility.PUBLIC,
    )

    chemin = upload_to(asset, nom)

    fichier = chemin.rsplit("/", 1)[-1]
    assert fichier.endswith(attendu)
    assert ".." not in chemin and "<" not in chemin and ".html" not in chemin


@pytest.mark.django_db
def test_une_page_html_deguisee_en_image_est_rangee_en_png(api_client, salon_a):
    api_client.force_login(salon_a.owner)

    reponse = api_client.post(
        "/api/v1/media/",
        {"file": image_png("attaque.html"), "kind": "gallery"},
        format="multipart",
    )

    assert reponse.status_code == 201, reponse.json()
    with as_tenant(salon_a.tenant):
        asset = MediaAsset.objects.get(pk=reponse.json()["id"])
    assert asset.file.name.endswith(".png")


def test_un_qr_code_garde_une_extension_d_image():
    assert chemin_qr(None, "qr.html").endswith(".png")
    assert chemin_qr(None, "qr.JPG").endswith(".jpg")
    assert type_du_qr("prive/plateforme/qr/x.html") == "image/png"
    assert type_du_qr("prive/plateforme/qr/x.webp") == "image/webp"


# ---------------------------------------------------------------------------
# Les preuves de versement
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_la_mediatheque_ne_liste_ni_ne_supprime_une_preuve(api_client, salon_a, moyens):
    abonnement_de(salon_a)
    api_client.force_login(salon_a.owner)
    reponse = declarer(api_client, moyens["wechat"], proof=png())
    preuve_id = reponse.json()["proof_url"].split("/media/")[1].split("/")[0]

    liste = api_client.get("/api/v1/media/?kind=proof&page_size=100").json()
    ids = [asset["id"] for asset in liste["results"]] if isinstance(liste, dict) else liste

    assert preuve_id not in str(ids)
    assert api_client.delete(f"/api/v1/media/{preuve_id}/").status_code == 404
    assert (
        api_client.patch(
            f"/api/v1/media/{preuve_id}/", {"kind": "gallery"}, format="json"
        ).status_code
        == 404
    )


@pytest.mark.django_db
def test_la_preuve_d_abonnement_ne_se_lit_que_par_le_proprietaire(api_client, salon_a, moyens):
    abonnement_de(salon_a)
    api_client.force_login(salon_a.owner)
    url = declarer(api_client, moyens["wechat"], proof=png()).json()["proof_url"]
    assert api_client.get(url).status_code == 200

    api_client.logout()
    api_client.force_login(equipier(salon_a))

    assert api_client.get(url).status_code == 404


@pytest.mark.django_db
def test_la_preuve_est_servie_en_bac_a_sable(api_client, salon_a, moyens):
    abonnement_de(salon_a)
    api_client.force_login(salon_a.owner)
    url = declarer(api_client, moyens["wechat"], proof=png()).json()["proof_url"]

    reponse = api_client.get(url)

    assert reponse["X-Content-Type-Options"] == "nosniff"
    assert "sandbox" in reponse["Content-Security-Policy"]


# ---------------------------------------------------------------------------
# Ce que voit l'equipe, ce que declare le proprietaire
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_l_equipe_ne_voit_pas_les_prix_de_la_plateforme(api_client, salon_a, offres):
    abonnement = abonnement_de(
        salon_a,
        statut=Subscription.Status.ACTIVE,
        fin=timezone.now() + timedelta(days=20),
        essai=False,
    )
    with as_tenant(salon_a.tenant):
        abonnement.plan = Plan.objects.get(code="monthly")
        abonnement.save(update_fields=["plan"])

    api_client.force_login(equipier(salon_a))
    acces = api_client.get("/api/v1/subscription/acces").json()
    assert acces["montee_en_gamme"] is None
    assert acces["peut_payer"] is False

    api_client.logout()
    api_client.force_login(salon_a.owner)
    assert api_client.get("/api/v1/subscription/acces").json()["montee_en_gamme"] is not None


@pytest.mark.django_db
def test_une_reference_avec_un_caractere_de_controle_est_refusee(api_client, salon_a, moyens):
    abonnement_de(salon_a)
    api_client.force_login(salon_a.owner)

    # Un caractere d'echappement (ESC) : DRF refuse deja l'octet nul, pas lui.
    reponse = declarer(api_client, moyens["wechat"], reference="REF" + chr(27) + "1234")

    assert reponse.status_code == 400
    assert reponse.json()["code"] == "reference_invalide"


def test_les_exemptions_s_arretent_au_segment():
    assert _permise("/api/v1/subscription")
    assert _permise("/api/v1/subscription/paiements")
    assert _permise("/api/v1/auth/logout")
    assert not _permise("/api/v1/subscriptions-export")
    assert not _permise("/api/v1/client/bookings")
    assert not _permise("/api/v1/services")


# ---------------------------------------------------------------------------
# L'administration ne reecrit pas l'argent
# ---------------------------------------------------------------------------


@ADMIN
def test_une_facture_ne_se_modifie_ni_ne_se_supprime(client, salon_a, moyens):
    abonnement_de(salon_a, fin=timezone.now() - timedelta(days=1))
    from apps.billing import services

    demande = _demande(salon_a, moyens["momo"])
    services.approuver_paiement(demande.id, administrateur=_admin())
    with as_tenant(salon_a.tenant):
        facture = Invoice.objects.get()
    client.force_login(_admin())

    client.post(
        reverse("admin:billing_invoice_change", args=[facture.pk]),
        {"amount": "1", "status": "void", "currency": "XAF"},
    )

    with as_tenant(salon_a.tenant):
        facture.refresh_from_db()
        assert facture.amount == Decimal("15000")
        assert facture.status == Invoice.Status.PAID
    assert client.get(reverse("admin:billing_invoice_add")).status_code == 403
    assert client.get(reverse("admin:billing_invoice_delete", args=[facture.pk])).status_code == 403


@ADMIN
def test_le_code_et_la_duree_d_une_offre_ne_changent_pas(client, offres):
    mensuel = offres["mensuel"]
    client.force_login(_admin())

    client.post(
        reverse("admin:billing_plan_change", args=[mensuel.pk]),
        {
            "code": "yearly",
            "name": "Mensuel",
            "billing_months": "12",
            "position": "10",
            "active": "on",
            "prices-TOTAL_FORMS": "0",
            "prices-INITIAL_FORMS": "0",
        },
    )

    mensuel.refresh_from_db()
    assert mensuel.code == "monthly"
    assert mensuel.billing_months == 1
    assert client.get(reverse("admin:billing_plan_delete", args=[mensuel.pk])).status_code == 403


@ADMIN
def test_un_tarif_garde_son_offre_et_sa_devise(client, offres):
    prix = PlanPrice.objects.get(plan=offres["mensuel"], currency="XAF")
    client.force_login(_admin())

    client.post(
        reverse("admin:billing_planprice_change", args=[prix.pk]),
        {"plan": str(offres["annuel"].pk), "currency": "CNY", "amount": "15000", "active": "on"},
    )

    prix.refresh_from_db()
    assert prix.plan_id == offres["mensuel"].pk
    assert prix.currency == "XAF"
