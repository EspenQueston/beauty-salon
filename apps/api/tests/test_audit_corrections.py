"""Corrections de l'audit du 16/10/2026 : les tests qui les tiennent.

Chaque section reprend un constat du rapport (output/audit-securite-2026-10-16.md)
et verifie le comportement corrige. Les prestataires y sont simules (doubles
de test) : ce ne sont pas des validations de l'integration reelle.
"""

import json
import time
from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.sessions.models import Session
from django.core import mail
from django.utils import timezone

from apps.accounts import reauth
from apps.audit.models import AuditLog
from apps.billing import kkiapay, saspay
from apps.billing import services as billing
from apps.billing.models import (
    Invoice,
    KkiapayIntent,
    PaiementARegulariser,
    PlanPrice,
    PlatformPaymentMethod,
    SaspayIntent,
    SubscriptionPaymentRequest,
)
from apps.parrainage.models import Remise
from apps.payments.models import PaymentChannel
from conftest import as_tenant
from tests.test_abonnements import ADMIN, abonnement_de, medias_temporaires, moyens, offres
from tests.test_deposit_payment import PASSWORD, login
from tests.test_parrainage import remise_pour
from tests.test_parrainage_v2 import kki_config, politique_b
from tests.test_saspay import SECRET, api, config, signer

FIXTURES = (medias_temporaires, moyens, offres, politique_b, kki_config, api, config)
pytestmark = ADMIN


def demande_de(salon):
    with as_tenant(salon.tenant):
        return SubscriptionPaymentRequest.objects.get()


def _modifier_session(client, **valeurs):
    cle = client.cookies["sessionid"].value
    s = Session.objects.get(session_key=cle)
    donnees = {**s.get_decoded(), **valeurs}
    Session.objects.filter(session_key=cle).update(session_data=Session.objects.encode(donnees))


# ---------------------------------------------------------------------------
# C-04 — moyens d'encaissement : reauthentification, journal, alerte
# ---------------------------------------------------------------------------


def test_C04_ecrire_un_moyen_exige_une_identite_recente(api_client, salon_a):
    salon_a.tenant.country = "CM"
    salon_a.tenant.save(update_fields=["country"])
    login(api_client, salon_a.owner)
    tete = {"HTTP_X_TENANT_ID": str(salon_a.tenant.pk)}
    url = "/api/v1/payment-channels/"

    # Juste apres la connexion : accepte.
    r = api_client.post(
        url, {"kind": "mobile_money", "instructions": "06 111 11 11"}, format="json", **tete
    )
    assert r.status_code == 201, r.content
    canal = r.json()["id"]

    # Onze minutes plus tard : refuse, sans rien modifier ; la lecture reste libre.
    _modifier_session(api_client, **{reauth.CLE: int(time.time()) - reauth.DUREE - 60})
    r = api_client.patch(f"{url}{canal}/", {"instructions": "07 999 99 99"}, format="json", **tete)
    assert r.status_code == 403 and r.json()["code"] == "reauth_requise"
    assert api_client.get(url, **tete).status_code == 200
    with as_tenant(salon_a.tenant):
        assert PaymentChannel.objects.get(pk=canal).instructions == "06 111 11 11"

    # Mauvais mot de passe : refuse. Bon mot de passe : la modification passe.
    faux = api_client.post("/api/v1/auth/reauth", {"password": "faux-mot-de-passe"}, format="json")
    assert faux.status_code == 400
    bon = api_client.post("/api/v1/auth/reauth", {"password": PASSWORD}, format="json")
    assert bon.status_code == 200
    r = api_client.patch(f"{url}{canal}/", {"instructions": "07 999 99 99"}, format="json", **tete)
    assert r.status_code == 200, r.content


def test_C04_chaque_changement_est_journalise_et_annonce(
    api_client, salon_a, django_capture_on_commit_callbacks
):
    salon_a.tenant.country = "CM"
    salon_a.tenant.save(update_fields=["country"])
    login(api_client, salon_a.owner)
    tete = {"HTTP_X_TENANT_ID": str(salon_a.tenant.pk)}
    url = "/api/v1/payment-channels/"
    mail.outbox.clear()

    with django_capture_on_commit_callbacks(execute=True):
        canal = api_client.post(
            url, {"kind": "mobile_money", "instructions": "06 111 11 11"}, format="json", **tete
        ).json()["id"]
        api_client.patch(f"{url}{canal}/", {"instructions": "07 999 99 99"}, format="json", **tete)
        # Changer l'ordre d'affichage : rien a signaler.
        api_client.patch(f"{url}{canal}/", {"position": 3}, format="json", **tete)
        api_client.delete(f"{url}{canal}/", **tete)

    with as_tenant(salon_a.tenant):
        journal = list(
            AuditLog.objects.filter(action=AuditLog.Action.PAYMENT_CHANNEL_CHANGED).order_by(
                "created_at"
            )
        )
    assert [j.metadata["operation"] for j in journal] == ["creation", "modification", "suppression"]
    modif = journal[1].metadata
    assert "06 111 11 11" in modif["avant"] and "07 999 99 99" in modif["apres"]
    assert journal[1].actor_user_id == salon_a.owner.pk

    assert len(mail.outbox) == 3
    assert all(m.to == [salon_a.owner.email] for m in mail.outbox)
    assert "07 999 99 99" in mail.outbox[1].body and "06 111 11 11" in mail.outbox[1].body


# ---------------------------------------------------------------------------
# C-01 — un paiement confirme par le prestataire n'est plus refuse pour une
#        remise expiree
# ---------------------------------------------------------------------------


def _saspay_ouvert(settings):
    settings.DEBUG = True
    settings.SASPAY_ENABLED = True
    settings.SASPAY_SANDBOX = True
    settings.SASPAY_TEST_SECRET_KEY = "sk_test_cle"
    settings.SASPAY_TEST_WEBHOOK_SECRET = SECRET


def test_C01_paye_avec_remise_expiree_est_approuve(settings, salon_a, offres, api, politique_b):
    from apps.parrainage.maintenance import entretenir

    _saspay_ouvert(settings)
    salon_a.tenant.country, salon_a.tenant.currency = "CM", "XAF"
    salon_a.tenant.save(update_fields=["country", "currency"])
    abonnement_de(salon_a)
    PlanPrice.objects.update_or_create(
        plan=offres["mensuel"], currency="XAF", defaults={"amount": 15000, "active": True}
    )
    moyen = PlatformPaymentMethod.objects.create(kind="saspay", country="CM", currency="XAF")
    remise = remise_pour(salon_a.tenant, pourcentage="10")
    with as_tenant(salon_a.tenant):
        intention = saspay.preparer(
            salon_a.tenant.pk,
            salon_a.owner,
            {"plan": "monthly", "country": "CM", "currency": "XAF", "method": moyen.pk},
        )
    assert demande_de(salon_a).amount == Decimal("13500")
    r = Remise.objects.get(pk=remise.pk)
    r.conditions = {
        **r.conditions,
        "reservation_fin": (timezone.now() - timedelta(seconds=1)).isoformat(),
    }
    r.save(update_fields=["conditions"])

    # La maintenance du parrainage ne refuse plus un paiement integre en cours.
    entretenir()
    assert demande_de(salon_a).status == "pending"

    api.statut = {"status": "PAID", "transaction_status": "SUCCESS"}
    api.session = {"amount": "13500.00", "currency": "XAF"}
    assert saspay.confirmer(intention["id"])["confirme"] is True
    assert demande_de(salon_a).status == "approved"
    assert Remise.objects.get(pk=remise.pk).statut == "utilisee"


# ---------------------------------------------------------------------------
# C-02 — un succes SASPAY non applicable ouvre un dossier a regulariser
# ---------------------------------------------------------------------------


def test_C02_succes_apres_expiration_a_regulariser(api_client, salon_a, config, api):
    intention, _ = config
    SaspayIntent.objects.filter(pk=intention["id"]).update(
        expire_le=timezone.now() - timedelta(seconds=1)
    )
    saspay.expirer(intention["id"])  # encore PENDING chez SASPAY : expire
    assert SaspayIntent.objects.get(pk=intention["id"]).statut == "expire"

    api.statut = {"status": "PAID", "transaction_status": "SUCCESS"}
    api.session = {"amount": "15000.00", "currency": "XAF"}
    corps = json.dumps({"event": "transaction.success", "data": {"id": "TX-1"}}).encode()
    for _ in range(2):  # un webhook rejoue ne duplique pas le dossier
        r = api_client.post(
            "/api/v1/webhooks/saspay/test", corps, content_type="application/json", **signer(corps)
        )
        assert r.status_code == 200
    dossier = PaiementARegulariser.objects.get()
    assert (dossier.prestataire, dossier.motif) == ("saspay", "succes_apres_expiration")
    assert dossier.tenant_id == salon_a.tenant.pk and dossier.montant == Decimal("15000")
    assert AuditLog.objects.filter(action=AuditLog.Action.PAYMENT_TO_RECONCILE).count() == 1
    assert demande_de(salon_a).status == "rejected"  # rien d'applique automatiquement


def test_C02_montant_different_apres_succes_a_regulariser(salon_a, config, api):
    intention, _ = config
    api.statut = {"status": "PAID", "transaction_status": "SUCCESS"}
    api.session = {"amount": "1500.00", "currency": "XAF"}
    with pytest.raises(billing.PaiementRefuse):
        saspay.confirmer(intention["id"])
    assert PaiementARegulariser.objects.get().motif == "montant_invalide"
    assert demande_de(salon_a).status == "pending"


# ---------------------------------------------------------------------------
# C-03 — KKIAPAY : verifier avant d'expirer ; un succes tardif est regularise
# ---------------------------------------------------------------------------


def test_C03_kkiapay_verifie_avant_d_expirer(salon_a, kki_config, monkeypatch):
    i, _ = kki_config
    reponse = {"transactionId": "TX9", "status": "PENDING", "amount": 15000, "partnerId": i["id"]}
    monkeypatch.setattr(kkiapay, "verifier_transaction", lambda *a: dict(reponse))
    # Le navigateur annonce la transaction ; KKIAPAY ne l'a pas encore reglee.
    with pytest.raises(billing.PaiementRefuse) as exc:
        kkiapay.confirmer(i["id"], "TX9")
    assert exc.value.code == "paiement_en_cours"
    assert KkiapayIntent.objects.get(pk=i["id"]).transaction_annoncee == "TX9"

    KkiapayIntent.objects.filter(pk=i["id"]).update(expire_le=timezone.now() - timedelta(seconds=1))
    kkiapay.expirer(i["id"])  # toujours en cours : on n'expire pas
    assert KkiapayIntent.objects.get(pk=i["id"]).statut == "en_attente"

    reponse["status"] = "SUCCESS"
    kkiapay.expirer(i["id"])  # reglee entre-temps : appliquee
    assert KkiapayIntent.objects.get(pk=i["id"]).statut == "confirme"
    assert demande_de(salon_a).status == "approved"


def test_C03_kkiapay_succes_sur_paiement_clos_a_regulariser(
    api_client, salon_a, kki_config, monkeypatch
):
    i, _ = kki_config
    succes = {"transactionId": "TX9", "status": "SUCCESS", "amount": 15000, "partnerId": i["id"]}
    monkeypatch.setattr(kkiapay, "verifier_transaction", lambda *a: dict(succes))
    KkiapayIntent.objects.filter(pk=i["id"]).update(expire_le=timezone.now() - timedelta(seconds=1))
    kkiapay.expirer(i["id"])  # aucune transaction annoncee : expire
    payload = {"event": "transaction.success", "transactionId": "TX9", "partnerId": i["id"]}
    r = api_client.post(
        "/api/v1/webhooks/kkiapay/test",
        payload,
        format="json",
        HTTP_X_KKIAPAY_SECRET="test-WEBHOOK_SECRET",
    )
    assert r.status_code == 409
    dossier = PaiementARegulariser.objects.get()
    assert (dossier.prestataire, dossier.motif) == ("kkiapay", "succes_apres_expiration")


# ---------------------------------------------------------------------------
# C-05 — sessions : limite absolue, activite de fond ignoree
# ---------------------------------------------------------------------------


def test_C05_une_session_finit_14_jours_apres_la_connexion(api_client, salon_a):
    from apps.accounts import sessions as s

    login(api_client, salon_a.owner)
    tete = {"HTTP_X_TENANT_ID": str(salon_a.tenant.pk)}
    maintenant = int(time.time())
    # Active il y a une minute, mais connectee il y a 14 jours et une heure.
    _modifier_session(
        api_client,
        **{s.CLE: maintenant - 60, s.CLE_CONNEXION: maintenant - 14 * 86400 - 3600},
    )
    assert api_client.get("/api/v1/payment-channels/", **tete).status_code in (401, 403)


def test_C05_le_rafraichissement_de_fond_ne_prolonge_pas(api_client, salon_a):
    from apps.accounts import sessions as s

    login(api_client, salon_a.owner)
    tete = {"HTTP_X_TENANT_ID": str(salon_a.tenant.pk)}
    ancienne = int(time.time()) - 10 * 60
    _modifier_session(api_client, **{s.CLE: ancienne})
    cle = api_client.cookies["sessionid"].value
    api_client.get("/api/v1/payment-channels/", HTTP_X_ACTIVITE="fond", **tete)
    assert Session.objects.get(session_key=cle).get_decoded()[s.CLE] == ancienne
    api_client.get("/api/v1/payment-channels/", **tete)  # une vraie navigation compte
    assert Session.objects.get(session_key=cle).get_decoded()[s.CLE] > ancienne


# ---------------------------------------------------------------------------
# C-08 — preuve d'acompte : seulement un moyen propose par le salon
# ---------------------------------------------------------------------------


def test_C08_preuve_avec_un_moyen_absent_refusee(api_client, salon_a):
    from tests.test_deposit_payment import HOST, book, give_channel, require_deposit

    require_deposit(salon_a)
    give_channel(salon_a, PaymentChannel.Kind.WECHAT)
    cree = book(api_client, salon_a)
    url = "/api/v1/public/payment/proof"
    jeton = cree.data["payment_token"]
    r = api_client.post(
        url,
        {"token": jeton, "channel": "orange_money", "reference": "ABCD1234"},
        format="json",
        headers=HOST,
    )
    assert r.status_code == 400 and r.json()["code"] == "moyen_non_propose"
    r = api_client.post(
        url,
        {"token": jeton, "channel": "wechat", "reference": "ABCD1234"},
        format="json",
        headers=HOST,
    )
    assert r.status_code in (200, 201), r.content


# ---------------------------------------------------------------------------
# C-10 — deconnecter les autres appareils
# ---------------------------------------------------------------------------


def test_C10_deconnecter_les_autres_appareils(salon_a):
    from rest_framework.test import APIClient

    tete = {"HTTP_X_TENANT_ID": str(salon_a.tenant.pk)}
    ici, ailleurs = APIClient(), APIClient()
    login(ici, salon_a.owner)
    login(ailleurs, salon_a.owner)
    assert ailleurs.get("/api/v1/payment-channels/", **tete).status_code == 200

    assert ici.post("/api/v1/auth/sessions/autres").status_code == 200
    assert ici.get("/api/v1/payment-channels/", **tete).status_code == 200  # celle-ci reste
    assert ailleurs.get("/api/v1/payment-channels/", **tete).status_code in (401, 403)
    assert AuditLog.objects.filter(action=AuditLog.Action.AUTH_OTHER_SESSIONS_CLOSED).exists()


def test_C10_sans_usage_les_sessions_existantes_restent_valides(salon_a):
    """L'empreinte d'un compte qui n'a jamais ferme ses sessions est celle de
    Django : le deploiement ne deconnecte personne."""
    from django.contrib.auth.base_user import AbstractBaseUser

    user = salon_a.owner
    assert user.generation_sessions == 0
    assert user.get_session_auth_hash() == AbstractBaseUser._get_session_auth_hash(user)


# ---------------------------------------------------------------------------
# C-11 — rapprochement quotidien
# ---------------------------------------------------------------------------


def test_C11_rapprochement_trouve_les_deux_sens(salon_a, config, api):
    from apps.billing.rapprochement import rapprocher

    intention, _ = config
    # Expire ici, mais paye chez SASPAY.
    SaspayIntent.objects.filter(pk=intention["id"]).update(statut="expire")
    api.statut = {"status": "PAID", "transaction_status": "SUCCESS"}
    assert rapprocher()["saspay"]["ecarts"] == 1
    assert PaiementARegulariser.objects.get().motif == "paye_non_applique"
    # Confirme ici, mais pas paye chez SASPAY.
    SaspayIntent.objects.filter(pk=intention["id"]).update(statut="confirme")
    api.statut = {"status": "PENDING", "transaction_status": None}
    assert rapprocher()["saspay"]["ecarts"] == 1
    assert set(PaiementARegulariser.objects.values_list("motif", flat=True)) == {
        "paye_non_applique",
        "applique_sans_paiement",
    }
    assert rapprocher()["saspay"]["ecarts"] == 0  # deja signales : pas de doublon


# ---------------------------------------------------------------------------
# Controles de l'audit (doivent toujours resister)
# ---------------------------------------------------------------------------


def test_controle_isolation_et_falsifications(api_client, salon_a, salon_b, config, api):
    intention, corps = config
    login(api_client, salon_b.owner)
    tete_b = {"HTTP_X_TENANT_ID": str(salon_b.tenant.pk)}
    r = api_client.post(
        "/api/v1/billing/saspay/confirm", {"intention": intention["id"]}, format="json", **tete_b
    )
    assert r.status_code == 404
    api_client.logout()

    login(api_client, salon_a.owner)
    tete = {"HTTP_X_TENANT_ID": str(salon_a.tenant.pk)}
    autre = {**corps, "country": "KE", "currency": "KES"}
    assert api_client.post("/api/v1/billing/saspay", autre, format="json", **tete).status_code == 400
    with pytest.raises(billing.PaiementRefuse) as exc:
        billing.approuver_paiement(demande_de(salon_a).pk, administrateur=None)
    assert exc.value.code == "integration_requise"

    # Webhook faux, perime, puis rejoue : une seule facture.
    api.statut = {"status": "PAID", "transaction_status": "SUCCESS"}
    api.session = {"amount": "15000.00", "currency": "XAF"}
    corps_w = json.dumps({"event": "transaction.success", "data": {"id": "TX-1"}}).encode()
    url = "/api/v1/webhooks/saspay/test"
    faux = {"HTTP_X_WEBHOOK_SIGNATURE": "0" * 64, "HTTP_X_WEBHOOK_TIMESTAMP": str(int(time.time()))}
    assert api_client.post(url, corps_w, content_type="application/json", **faux).status_code == 403
    vieux = signer(corps_w, horodatage=time.time() - 600)
    assert api_client.post(url, corps_w, content_type="application/json", **vieux).status_code == 403
    for _ in range(3):
        r = api_client.post(url, corps_w, content_type="application/json", **signer(corps_w))
        assert r.status_code == 200
    with as_tenant(salon_a.tenant):
        assert Invoice.objects.count() == 1


# ---------------------------------------------------------------------------
# C-09 — l'espace pro ne repond qu'a l'espace pro ; CORS limite a l'API
# ---------------------------------------------------------------------------


def test_C09_un_mini_site_ne_peut_pas_appeler_l_espace_pro(api_client, salon_a, settings):
    domaine = settings.PLATFORM_DOMAIN
    login(api_client, salon_a.owner)
    tete = {"HTTP_X_TENANT_ID": str(salon_a.tenant.pk)}
    url = "/api/v1/payment-channels/"
    mini_site = {"HTTP_ORIGIN": f"https://{salon_a.tenant.slug}.{domaine}"}

    # Depuis un mini-site, avec la session d'une gerante : refuse.
    r = api_client.get(url, **tete, **mini_site)
    assert r.status_code == 403 and r.json()["code"] == "origine_refusee"
    r = api_client.post(url, {"kind": "wechat"}, format="json", **tete, **mini_site)
    assert r.status_code == 403
    # Depuis l'espace pro, ou sans Origin (meme origine, serveur) : accepte.
    assert api_client.get(url, **tete, HTTP_ORIGIN=f"https://app.{domaine}").status_code == 200
    assert api_client.get(url, **tete).status_code == 200
    # Les routes du mini-site restent ouvertes au mini-site.
    r = api_client.get("/api/v1/csrf", **mini_site)
    assert r.status_code == 200
    assert api_client.get("/api/v1/auth/session", **mini_site).status_code == 200


def test_C09_le_cors_ne_couvre_plus_l_administration(client, settings):
    origine = f"https://salon.{settings.PLATFORM_DOMAIN}"
    api = client.get("/api/v1/csrf", HTTP_ORIGIN=origine)
    assert api.headers.get("Access-Control-Allow-Origin") == origine
    admin = client.get(f"/{settings.ADMIN_PATH}", HTTP_ORIGIN=origine)
    assert "Access-Control-Allow-Origin" not in admin.headers
