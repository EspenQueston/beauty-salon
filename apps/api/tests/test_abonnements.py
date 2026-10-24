"""Abonnements payants : tarifs, moyens, declaration, verification, acces.

Ce que ces tests tiennent, dans l'ordre ou un salon le vit :

  - le montant vient du tarif configure, jamais de la requete, et reste fige
    sur la demande ;
  - seuls les moyens actifs, complets et accordes au pays et a la devise sont
    proposes — et acceptes ;
  - declarer un paiement n'ouvre rien ; une seule demande attend a la fois ;
    une reference ne sert qu'une fois, tous salons confondus ;
  - l'approbation accorde un mois calendaire ou douze, une seule fois, meme
    sous deux clics simultanes ; elle prolonge une periode en cours ;
  - le refus est motive, et le salon le lit ;
  - apres 3 jours de grace, plus de nouvelle reservation et un tableau de
    bord en lecture seule — sauf la page Abonnement ;
  - un salon ne voit jamais les paiements ni les preuves d'un autre.
"""

import io
import threading
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connections
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from apps.accounts.models import Membership
from apps.audit.models import AuditLog
from apps.billing import services
from apps.billing.models import (
    Invoice,
    Plan,
    PlanPrice,
    PlatformPaymentMethod,
    Subscription,
    SubscriptionEvent,
    SubscriptionPaymentRequest,
)
from apps.billing.services import PaiementRefuse, acces_de, ajouter_mois, economie_annuelle
from apps.notifications.models import Notification, PlatformNotification
from conftest import as_tenant, salon_host
from tests.factories import MembershipFactory, UserFactory

URL_PAIEMENTS = "/api/v1/subscription/paiements"
URL_OFFRES = "/api/v1/subscription/offres"
URL_ACCES = "/api/v1/subscription/acces"
ADMIN = pytest.mark.django_db(databases=["default", "admin"], transaction=True)


def png(nom="capture.png") -> SimpleUploadedFile:
    tampon = io.BytesIO()
    Image.new("RGB", (8, 8), "white").save(tampon, format="PNG")
    return SimpleUploadedFile(nom, tampon.getvalue(), content_type="image/png")


@pytest.fixture(autouse=True)
def medias_temporaires(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path


@pytest.fixture
def offres(db):
    """L'essai, le mensuel et l'annuel, avec leurs prix de test.

    Crees ici plutot que lus depuis la migration : les tests transactionnels
    vident les tables apres eux, donnees de migration comprises.
    """
    Plan.objects.get_or_create(code=Plan.Code.TRIAL, defaults={"name": "Essai"})
    mensuel, _ = Plan.objects.update_or_create(
        code=Plan.Code.MONTHLY,
        defaults={"name": "Mensuel", "billing_months": 1, "position": 10, "active": True},
    )
    annuel, _ = Plan.objects.update_or_create(
        code=Plan.Code.YEARLY,
        defaults={"name": "Annuel", "billing_months": 12, "position": 11, "active": True},
    )
    for plan, cny, xaf in ((mensuel, "99", "15000"), (annuel, "999", "150000")):
        PlanPrice.objects.update_or_create(
            plan=plan, currency="CNY", defaults={"amount": Decimal(cny), "active": True}
        )
        PlanPrice.objects.update_or_create(
            plan=plan, currency="XAF", defaults={"amount": Decimal(xaf), "active": True}
        )
    return {"mensuel": mensuel, "annuel": annuel}


@pytest.fixture
def moyens(offres):
    """Un WeChat Pay en Chine, un MTN au Congo — et trois qu'on ne doit pas voir."""
    wechat = PlatformPaymentMethod.objects.create(
        kind="wechat",
        country="CN",
        currency="CNY",
        qr_image=png("qr.png"),
        instructions="Scannez puis indiquez la référence.",
    )
    momo = PlatformPaymentMethod.objects.create(
        kind="mobile_money",
        provider_name="MTN MoMo",
        country="CG",
        currency="XAF",
        account_number="+242 06 000 00 00",
        account_holder="Beauty Salon SARL",
    )
    PlatformPaymentMethod.objects.create(
        kind="alipay", country="CN", currency="CNY", active=True
    )  # actif mais sans QR code : incomplet, jamais propose
    PlatformPaymentMethod.objects.create(
        kind="mobile_money",
        provider_name="Airtel",
        country="CG",
        currency="XAF",
        account_number="+242 05",
        account_holder="X",
        active=False,
    )
    PlatformPaymentMethod.objects.create(
        kind="mobile_money",
        provider_name="M-Pesa",
        country="CD",
        currency="USD",
        account_number="+243 81",
        account_holder="Y",
    )  # pas de tarif en USD : la devise n'est pas proposee
    return {"wechat": wechat, "momo": momo}


def abonnement_de(salon, *, statut=Subscription.Status.TRIALING, fin=None, essai=True):
    """Pose l'abonnement du salon dans l'etat voulu."""
    fin = fin or timezone.now() + timedelta(days=10)
    plan = Plan.objects.get(code=Plan.Code.TRIAL)
    with as_tenant(salon.tenant):
        abonnement, _ = Subscription.objects.update_or_create(
            tenant=salon.tenant,
            defaults={
                "plan": plan,
                "status": statut,
                "currency": salon.tenant.currency,
                "trial_ends_at": fin if essai else None,
                "current_period_start": fin - timedelta(days=14),
                "current_period_end": fin,
                "period_anchor": None,
                "anchor_months": 0,
            },
        )
    return abonnement


def connecter(client, user):
    client.force_login(user)
    return client


def declarer(
    client, moyen, *, plan="monthly", pays=None, devise=None, reference="REF-0001", **extra
):
    donnees = {
        "plan": plan,
        "country": pays or moyen.country,
        "currency": devise or moyen.currency,
        "method": str(moyen.id),
        "reference": reference,
        **extra,
    }
    return client.post(URL_PAIEMENTS, donnees, format="multipart")


# ---------------------------------------------------------------------------
# Tarifs et eligibilite
# ---------------------------------------------------------------------------


def test_l_economie_annuelle_se_compare_a_douze_mois():
    economie = economie_annuelle(Decimal("99"), Decimal("999"))

    assert economie["montant"] == Decimal("189")
    assert economie["pourcentage"] == 16
    assert economie_annuelle(Decimal("99"), None) is None
    # Pas d'« economie » quand l'annee coute plus cher que douze mois.
    assert economie_annuelle(Decimal("10"), Decimal("200")) is None


@pytest.mark.django_db
def test_seuls_les_moyens_actifs_complets_et_accordes_sont_proposes(api_client, salon_a, moyens):
    abonnement_de(salon_a)
    reponse = connecter(api_client, salon_a.owner).get(URL_OFFRES)

    assert reponse.status_code == 200
    proposes = {
        (pays["code"], devise["code"]): [m["libelle"] for m in devise["moyens"]]
        for pays in reponse.json()["pays"]
        for devise in pays["devises"]
    }
    assert proposes == {("CG", "XAF"): ["MTN MoMo"], ("CN", "CNY"): ["WeChat Pay"]}
    # Le QR code sort par une route authentifiee, jamais par /media/.
    wechat = next(p for p in reponse.json()["pays"] if p["code"] == "CN")["devises"][0]
    assert "/api/v1/subscription/moyens/" in wechat["moyens"][0]["qr_url"]
    assert wechat["economie"]["pourcentage"] == 16


@pytest.mark.django_db
def test_le_montant_vient_du_tarif_jamais_de_la_requete(api_client, salon_a, moyens):
    abonnement_de(salon_a)
    reponse = declarer(connecter(api_client, salon_a.owner), moyens["wechat"], amount="1")

    assert reponse.status_code == 201, reponse.json()
    assert Decimal(reponse.json()["amount"]) == Decimal("99")
    assert reponse.json()["status"] == "pending"


@pytest.mark.django_db
def test_un_prix_modifie_ne_change_pas_une_demande_envoyee(api_client, salon_a, moyens, offres):
    abonnement_de(salon_a)
    declarer(connecter(api_client, salon_a.owner), moyens["wechat"])
    PlanPrice.objects.filter(plan=offres["mensuel"], currency="CNY").update(amount=Decimal("149"))

    with as_tenant(salon_a.tenant):
        demande = SubscriptionPaymentRequest.objects.get()
    assert demande.amount == Decimal("99")
    assert demande.method_label == "WeChat Pay"


@pytest.mark.django_db
def test_une_devise_sans_tarif_est_refusee(api_client, salon_a, moyens):
    abonnement_de(salon_a)
    usd = PlatformPaymentMethod.objects.get(provider_name="M-Pesa")

    reponse = declarer(connecter(api_client, salon_a.owner), usd)

    assert reponse.status_code == 400
    assert reponse.json()["code"] == "tarif_absent"


@pytest.mark.django_db
def test_un_moyen_d_un_autre_pays_ou_incomplet_est_refuse(api_client, salon_a, moyens):
    abonnement_de(salon_a)
    client = connecter(api_client, salon_a.owner)

    ailleurs = declarer(client, moyens["wechat"], pays="CG", devise="XAF")
    incomplet = declarer(client, PlatformPaymentMethod.objects.get(kind="alipay"))

    assert ailleurs.json()["code"] == "moyen_indisponible"
    assert incomplet.json()["code"] == "moyen_indisponible"


# ---------------------------------------------------------------------------
# Declaration
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_declarer_n_ouvre_aucun_acces(api_client, salon_a, moyens):
    """Une capture se fabrique : seul un administrateur ouvre une periode."""
    abonnement = abonnement_de(salon_a, fin=timezone.now() - timedelta(days=5))
    client = connecter(api_client, salon_a.owner)

    reponse = declarer(client, moyens["momo"], proof=png())

    assert reponse.status_code == 201
    with as_tenant(salon_a.tenant):
        abonnement.refresh_from_db()
        assert abonnement.status == Subscription.Status.PENDING_PAYMENT
        assert not acces_de(abonnement).ouvert
        assert not Invoice.objects.exists()


@pytest.mark.django_db
def test_une_seule_demande_en_attente(api_client, salon_a, moyens):
    abonnement_de(salon_a)
    client = connecter(api_client, salon_a.owner)

    declarer(client, moyens["wechat"], reference="REF-0001")
    seconde = declarer(client, moyens["wechat"], reference="REF-0002")

    assert seconde.status_code == 409
    assert seconde.json()["code"] == "demande_en_attente"


@pytest.mark.django_db
def test_une_reference_ne_sert_qu_une_fois_meme_entre_salons(api_client, salon_a, salon_b, moyens):
    abonnement_de(salon_a)
    abonnement_de(salon_b)
    declarer(connecter(api_client, salon_a.owner), moyens["wechat"], reference="wx 12345")
    api_client.logout()

    # La meme transaction, autrement ecrite : espaces et casse ne comptent pas.
    reponse = declarer(connecter(api_client, salon_b.owner), moyens["wechat"], reference="WX12345")

    assert reponse.status_code == 409
    assert reponse.json()["code"] == "reference_deja_utilisee"


@pytest.mark.django_db
def test_une_preuve_d_un_autre_format_est_refusee(api_client, salon_a, moyens):
    abonnement_de(salon_a)
    tampon = io.BytesIO()
    Image.new("RGB", (8, 8), "white").save(tampon, format="GIF")
    gif = SimpleUploadedFile("capture.gif", tampon.getvalue(), content_type="image/gif")

    reponse = declarer(connecter(api_client, salon_a.owner), moyens["wechat"], proof=gif)

    assert reponse.status_code == 400
    assert "proof" in reponse.json()["detail"]


@pytest.mark.django_db
def test_la_preuve_est_privee_et_ne_se_lit_que_par_son_salon(api_client, salon_a, salon_b, moyens):
    abonnement_de(salon_a)
    reponse = declarer(connecter(api_client, salon_a.owner), moyens["wechat"], proof=png())
    url = reponse.json()["proof_url"]

    assert "/api/v1/media/" in url and "/fichier" in url
    assert api_client.get(url).status_code == 200
    api_client.logout()
    assert connecter(api_client, salon_b.owner).get(url).status_code == 404


@pytest.mark.django_db
def test_seul_le_proprietaire_paie(api_client, salon_a, moyens):
    abonnement_de(salon_a)
    gerante = UserFactory()
    MembershipFactory(tenant=salon_a.tenant, user=gerante, role=Membership.Role.MANAGER)
    client = connecter(api_client, gerante)

    assert declarer(client, moyens["wechat"]).status_code == 403
    acces = client.get(URL_ACCES)
    assert acces.status_code == 200
    assert acces.json()["peut_payer"] is False


@pytest.mark.django_db
def test_un_salon_ne_voit_pas_les_paiements_d_un_autre(api_client, salon_a, salon_b, moyens):
    abonnement_de(salon_a)
    abonnement_de(salon_b)
    declarer(connecter(api_client, salon_a.owner), moyens["wechat"])
    api_client.logout()

    reponse = connecter(api_client, salon_b.owner).get(URL_PAIEMENTS)

    assert reponse.status_code == 200
    assert reponse.json() == []


# ---------------------------------------------------------------------------
# Verification : approuver, refuser
# ---------------------------------------------------------------------------


def _demande(salon, moyen, *, reference="REF-0001", plan="monthly"):
    with as_tenant(salon.tenant):
        return services.soumettre_paiement(
            tenant_id=salon.tenant.id,
            utilisateur=salon.owner,
            code_offre=plan,
            pays=moyen.country,
            devise=moyen.currency,
            moyen_id=moyen.id,
            reference=reference,
        )


def _admin():
    return UserFactory(is_staff=True, is_superuser=True, is_platform_admin=True)


@ADMIN
def test_approuver_accorde_un_mois_une_facture_et_une_trace(salon_a, moyens):
    abonnement_de(salon_a, fin=timezone.now() - timedelta(days=1))
    demande = _demande(salon_a, moyens["momo"])
    admin = _admin()

    services.approuver_paiement(demande.id, administrateur=admin, note="Relevé MTN vérifié")

    with as_tenant(salon_a.tenant):
        demande.refresh_from_db()
        abonnement = Subscription.objects.get()
        assert demande.status == SubscriptionPaymentRequest.Status.APPROVED
        assert demande.reviewed_by == admin
        assert abonnement.status == Subscription.Status.ACTIVE
        # Periode echue : la nouvelle commence a l'approbation.
        assert abs((abonnement.current_period_start - timezone.now()).total_seconds()) < 60
        assert abonnement.current_period_end == ajouter_mois(
            demande.period_start, 1, salon_a.tenant.timezone
        )
        facture = Invoice.objects.get()
        assert facture.status == Invoice.Status.PAID
        assert facture.amount == Decimal("15000") and facture.currency == "XAF"
        assert SubscriptionEvent.objects.filter(kind="payment_approved").count() == 1
    assert AuditLog.objects.filter(action="subscription.payment_approved").count() == 1


@ADMIN
def test_payer_pendant_l_essai_commence_apres_l_essai(salon_a, moyens):
    fin_essai = timezone.now() + timedelta(days=6)
    abonnement_de(salon_a, fin=fin_essai)
    demande = _demande(salon_a, moyens["momo"], plan="yearly")

    services.approuver_paiement(demande.id, administrateur=_admin())

    with as_tenant(salon_a.tenant):
        demande.refresh_from_db()
        assert demande.period_start == fin_essai
        assert demande.period_end == ajouter_mois(fin_essai, 12, salon_a.tenant.timezone)


@ADMIN
def test_un_nouveau_paiement_prolonge_la_periode_en_cours(salon_a, moyens):
    abonnement_de(salon_a, fin=timezone.now() - timedelta(days=1))
    admin = _admin()
    premiere = _demande(salon_a, moyens["momo"], reference="REF-0001")
    services.approuver_paiement(premiere.id, administrateur=admin)
    seconde = _demande(salon_a, moyens["momo"], reference="REF-0002")

    services.approuver_paiement(seconde.id, administrateur=admin)

    with as_tenant(salon_a.tenant):
        premiere.refresh_from_db()
        seconde.refresh_from_db()
        # La seconde periode commence a la fin de la premiere, sans chevauchement.
        assert seconde.period_start == premiere.period_end
        # Et garde l'ancre : deux mois depuis le debut de la suite.
        assert seconde.period_end == ajouter_mois(premiere.period_start, 2, salon_a.tenant.timezone)


@ADMIN
def test_approuver_deux_fois_n_accorde_qu_une_periode(salon_a, moyens):
    abonnement_de(salon_a, fin=timezone.now() - timedelta(days=1))
    demande = _demande(salon_a, moyens["momo"])
    admin = _admin()
    services.approuver_paiement(demande.id, administrateur=admin)
    with as_tenant(salon_a.tenant):
        fin = Subscription.objects.get().current_period_end

    with pytest.raises(PaiementRefuse) as refus:
        services.approuver_paiement(demande.id, administrateur=admin)

    assert refus.value.code == "deja_traitee"
    with as_tenant(salon_a.tenant):
        assert Subscription.objects.get().current_period_end == fin
        assert Invoice.objects.count() == 1


@ADMIN
def test_deux_approbations_simultanees_n_accordent_qu_une_periode(salon_a, moyens):
    """Deux administrateurs, ou deux onglets, au meme instant : le verrou sur
    la demande fait attendre le second, qui la trouve deja traitee."""
    abonnement_de(salon_a, fin=timezone.now() - timedelta(days=1))
    demande = _demande(salon_a, moyens["momo"])
    admin = _admin()
    resultats: dict[int, str] = {}
    barriere = threading.Barrier(2)

    def approuver(index):
        try:
            barriere.wait(timeout=10)
            services.approuver_paiement(demande.id, administrateur=admin)
            resultats[index] = "ok"
        except PaiementRefuse as refus:
            resultats[index] = refus.code
        except Exception as erreur:  # noqa: BLE001 - on veut le voir
            resultats[index] = f"erreur: {erreur}"
        finally:
            for alias in ("default", "admin"):
                connections[alias].close()

    fils = [threading.Thread(target=approuver, args=(i,)) for i in range(2)]
    for fil in fils:
        fil.start()
    for fil in fils:
        fil.join(timeout=30)

    assert sorted(resultats.values()) == ["deja_traitee", "ok"], resultats
    with as_tenant(salon_a.tenant):
        assert Invoice.objects.count() == 1
        assert SubscriptionEvent.objects.filter(kind="payment_approved").count() == 1


@ADMIN
def test_refuser_exige_un_motif_que_le_salon_lit(api_client, salon_a, moyens):
    abonnement = abonnement_de(salon_a, fin=timezone.now() - timedelta(days=5))
    demande = _demande(salon_a, moyens["momo"])
    admin = _admin()

    with pytest.raises(PaiementRefuse):
        services.refuser_paiement(demande.id, administrateur=admin, motif="  ")
    services.refuser_paiement(
        demande.id, administrateur=admin, motif="Aucun versement reçu avec cette référence"
    )

    with as_tenant(salon_a.tenant):
        abonnement.refresh_from_db()
        assert abonnement.status == Subscription.Status.EXPIRED
    historique = connecter(api_client, salon_a.owner).get(URL_PAIEMENTS).json()
    assert historique[0]["status"] == "rejected"
    assert historique[0]["rejection_reason"] == "Aucun versement reçu avec cette référence"
    # Refusee, la reference se libere : le salon corrige et renvoie.
    assert _demande(salon_a, moyens["momo"]).status == "pending"


@ADMIN
def test_la_plateforme_est_prevenue_puis_le_salon(salon_a, moyens):
    abonnement_de(salon_a, fin=timezone.now() - timedelta(days=1))
    admin = _admin()
    demande = _demande(salon_a, moyens["momo"])

    assert PlatformNotification.objects.filter(genre="paiement_abonnement").count() == 1
    services.approuver_paiement(demande.id, administrateur=admin)
    with as_tenant(salon_a.tenant):
        notification = Notification.objects.get(genre="abonnement")
        assert notification.titre.startswith("Abonnement actif jusqu'au")
        assert notification.lien == "/abonnement"


@ADMIN
def test_l_administration_approuve_et_refuse_depuis_l_interface(client, salon_a, moyens):
    abonnement_de(salon_a, fin=timezone.now() - timedelta(days=1))
    demande = _demande(salon_a, moyens["momo"])
    client.force_login(_admin())

    fiche = client.get(
        reverse("admin:billing_subscriptionpaymentrequest_change", args=[demande.id])
    )
    assert fiche.status_code == 200
    assert "Approuver le paiement" in fiche.content.decode()

    reponse = client.post(
        reverse("admin:billing_subscriptionpaymentrequest_approuver", args=[demande.id]),
        {"note": "ok"},
    )
    assert reponse.status_code == 302
    with as_tenant(salon_a.tenant):
        demande.refresh_from_db()
        assert demande.status == "approved"


@ADMIN
def test_sans_permission_on_ne_decide_pas(client, salon_a, moyens):
    abonnement_de(salon_a, fin=timezone.now() - timedelta(days=1))
    demande = _demande(salon_a, moyens["momo"])
    lecteur = UserFactory(is_staff=True, is_platform_admin=True)
    from django.contrib.auth.models import Permission

    lecteur.user_permissions.add(Permission.objects.get(codename="view_subscriptionpaymentrequest"))
    client.force_login(lecteur)

    client.post(reverse("admin:billing_subscriptionpaymentrequest_approuver", args=[demande.id]))

    with as_tenant(salon_a.tenant):
        demande.refresh_from_db()
        assert demande.status == "pending"


@ADMIN
def test_une_prolongation_manuelle_est_justifiee_et_tracee(salon_a, moyens):
    abonnement_de(salon_a, fin=timezone.now() - timedelta(days=1))
    admin = _admin()

    with pytest.raises(PaiementRefuse):
        services.prolonger_manuellement(salon_a.tenant.id, administrateur=admin, mois=1, note="")
    services.prolonger_manuellement(
        salon_a.tenant.id, administrateur=admin, mois=1, note="Geste commercial"
    )

    with as_tenant(salon_a.tenant):
        abonnement = Subscription.objects.get()
        assert abonnement.status == Subscription.Status.ACTIVE
        assert acces_de(abonnement).ouvert
        assert not Invoice.objects.exists()  # rien n'a ete encaisse
        assert SubscriptionEvent.objects.filter(kind="manual_extension").count() == 1
    assert AuditLog.objects.filter(action="subscription.manual_change").count() == 1


# ---------------------------------------------------------------------------
# Periodes et acces
# ---------------------------------------------------------------------------


def test_fin_de_mois_prend_le_dernier_jour_puis_revient_au_jour_d_ancrage():
    ancre = datetime(2027, 1, 31, 10, 0, tzinfo=UTC)

    assert ajouter_mois(ancre, 1, "UTC") == datetime(2027, 2, 28, 10, 0, tzinfo=UTC)
    # Depuis l'ancre, pas depuis le 28 fevrier : on retrouve le 31.
    assert ajouter_mois(ancre, 2, "UTC") == datetime(2027, 3, 31, 10, 0, tzinfo=UTC)
    # Annee bissextile.
    assert ajouter_mois(datetime(2028, 1, 31, tzinfo=UTC), 1, "UTC").day == 29
    # Un an apres un 29 fevrier : le 28.
    assert ajouter_mois(datetime(2028, 2, 29, tzinfo=UTC), 12, "UTC") == datetime(
        2029, 2, 28, tzinfo=UTC
    )


def test_le_mois_se_compte_dans_le_fuseau_du_salon():
    # 17 h UTC le 30 janvier, c'est deja le 31 a Guangzhou.
    ancre = datetime(2027, 1, 30, 17, 0, tzinfo=UTC)

    fin = ajouter_mois(ancre, 1, "Asia/Shanghai")

    assert fin == datetime(2027, 2, 27, 17, 0, tzinfo=UTC)  # 28 fevrier, 1 h a Guangzhou


@pytest.mark.django_db
def test_trois_jours_de_grace_puis_fermeture(salon_a, offres):
    maintenant = timezone.now()
    en_grace = abonnement_de(salon_a, fin=maintenant - timedelta(days=2))
    assert acces_de(en_grace).raison == "grace" and acces_de(en_grace).ouvert

    ferme = abonnement_de(salon_a, fin=maintenant - timedelta(days=4))
    assert acces_de(ferme).raison == "expire" and not acces_de(ferme).ouvert


@pytest.mark.django_db
def test_une_suspension_ferme_meme_avec_une_periode_payee(salon_a, offres):
    abonnement = abonnement_de(salon_a, statut=Subscription.Status.SUSPENDED)

    assert not acces_de(abonnement).ouvert
    assert acces_de(abonnement).raison == "suspendu"


@pytest.mark.django_db
def test_sans_acces_les_reservations_publiques_s_arretent(api_client, salon_a, offres):
    abonnement_de(salon_a, fin=timezone.now() - timedelta(days=5))
    hote = {"HTTP_HOST": salon_host("blondrose")}

    reservation = api_client.post("/api/v1/public/bookings", {}, format="json", **hote)
    salon = api_client.get("/api/v1/public/salon", **hote)

    assert reservation.status_code == 403
    assert reservation.json()["code"] == "reservations_indisponibles"
    # Le mini-site reste en ligne, et dit que les reservations sont fermees.
    assert salon.status_code == 200
    assert salon.json()["reservations_ouvertes"] is False


@pytest.mark.django_db
def test_pendant_la_grace_les_reservations_restent_ouvertes(api_client, salon_a, offres):
    abonnement_de(salon_a, fin=timezone.now() - timedelta(days=1))
    hote = {"HTTP_HOST": salon_host("blondrose")}

    reservation = api_client.post("/api/v1/public/bookings", {}, format="json", **hote)

    # Refusee pour un formulaire vide, pas pour l'abonnement.
    assert reservation.status_code == 400
    assert api_client.get("/api/v1/public/salon", **hote).json()["reservations_ouvertes"] is True


@pytest.mark.django_db
def test_sans_acces_le_tableau_de_bord_passe_en_lecture_seule(api_client, salon_a, moyens):
    abonnement_de(salon_a, fin=timezone.now() - timedelta(days=5))
    client = connecter(api_client, salon_a.owner)

    ecriture = client.post("/api/v1/service-categories/", {"name": "Nouveau"}, format="json")
    lecture = client.get("/api/v1/service-categories/")
    paiement = declarer(client, moyens["momo"])

    assert ecriture.status_code == 402
    assert ecriture.json()["code"] == "abonnement_requis"
    assert lecture.status_code == 200
    # La page Abonnement reste utilisable : c'est par elle qu'on rouvre tout.
    assert paiement.status_code == 201


@pytest.mark.django_db
def test_un_salon_sans_abonnement_reste_ouvert(api_client, salon_a):
    """Cas de secours : fermer un salon par oubli serait pire qu'un jour
    offert. La tache quotidienne lui ouvre un essai."""
    client = connecter(api_client, salon_a.owner)

    reponse = client.post("/api/v1/service-categories/", {"name": "Nouveau"}, format="json")

    assert reponse.status_code != 402


# ---------------------------------------------------------------------------
# Les ecrans de l'administration s'ouvrent, avec des donnees reelles
# ---------------------------------------------------------------------------

ECRANS = [
    "admin:billing_plan_changelist",
    "admin:billing_planprice_changelist",
    "admin:billing_platformpaymentmethod_changelist",
    "admin:billing_platformpaymentmethod_add",
    "admin:billing_subscriptionpaymentrequest_changelist",
    "admin:billing_subscription_changelist",
    "admin:billing_subscriptionevent_changelist",
    "admin:billing_invoice_changelist",
]


@ADMIN
@pytest.mark.parametrize("route", ECRANS)
def test_chaque_ecran_d_abonnement_s_ouvre(client, salon_a, moyens, route):
    abonnement_de(salon_a, fin=timezone.now() - timedelta(days=1))
    admin = _admin()
    approuvee = _demande(salon_a, moyens["momo"], reference="REF-0001")
    services.approuver_paiement(approuvee.id, administrateur=admin)
    _demande(salon_a, moyens["wechat"], reference="REF-0002")
    client.force_login(admin)

    assert client.get(reverse(route)).status_code == 200


@ADMIN
def test_les_fiches_le_qr_et_la_preuve_s_ouvrent(client, salon_a, moyens, offres):
    abonnement = abonnement_de(salon_a)
    with as_tenant(salon_a.tenant):
        demande = services.soumettre_paiement(
            tenant_id=salon_a.tenant.id,
            utilisateur=salon_a.owner,
            code_offre="monthly",
            pays="CN",
            devise="CNY",
            moyen_id=moyens["wechat"].id,
            reference="REF-0001",
            preuve=png(),
        )
    client.force_login(_admin())

    for url in (
        reverse("admin:billing_plan_change", args=[offres["mensuel"].pk]),
        reverse("admin:billing_platformpaymentmethod_change", args=[moyens["wechat"].pk]),
        reverse("admin:billing_platformpaymentmethod_qr", args=[moyens["wechat"].pk]),
        reverse("admin:billing_subscription_change", args=[abonnement.pk]),
        reverse("admin:billing_subscriptionpaymentrequest_preuve", args=[demande.pk]),
    ):
        assert client.get(url).status_code == 200, url


@ADMIN
def test_prolonger_depuis_la_liste_demande_une_justification(client, salon_a, offres):
    abonnement = abonnement_de(salon_a, fin=timezone.now() - timedelta(days=5))
    client.force_login(_admin())
    liste = reverse("admin:billing_subscription_changelist")
    choix = {"action": "action_prolonger", "_selected_action": [str(abonnement.pk)]}

    page = client.post(liste, choix)
    assert page.status_code == 200
    assert "Justification" in page.content.decode()

    client.post(liste, {**choix, "confirmer": "1", "mois": "1", "note": "Panne de paiement"})

    with as_tenant(salon_a.tenant):
        abonnement.refresh_from_db()
        assert abonnement.status == Subscription.Status.ACTIVE
        assert acces_de(abonnement).ouvert
