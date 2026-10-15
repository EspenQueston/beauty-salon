"""SASPAY : l'abonnement depuis les pays africains que KKIAPAY ne couvre pas.

Ce que ces tests tiennent :

  - SASPAY et KKIAPAY ne se recouvrent jamais ; chaque pays SASPAY accepte
    sa devise Mobile Money et l'USD (carte), le Congo-Brazzaville l'USD seul ;
  - fermé tant que les clés manquent, et jamais en mode test hors DEBUG ;
  - le paiement ne s'active que sur la parole de l'API SASPAY — session
    payée, transaction réussie, montant, devise et session concordants —
    jamais sur celle du navigateur ni sur un webhook non signé ;
  - un webhook signé déclenche la vérification ; un horodatage trop vieux,
    une signature fausse sont refusés ; une API muette fait répondre 503 ;
  - un paiement abandonné est clos après une dernière vérification, et un
    paiement fait à la dernière minute n'est pas perdu ;
  - aucun administrateur ne peut approuver à la main un paiement SASPAY.
"""

import hashlib
import hmac
import json
import time
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.billing import saspay
from apps.billing import services as billing
from apps.billing.kkiapay import PAYS_DOCUMENTES
from apps.billing.models import (
    Invoice,
    PlanPrice,
    PlatformPaymentMethod,
    SaspayIntent,
    SubscriptionPaymentRequest,
)
from apps.tenants.models import Tenant
from conftest import as_tenant
from tests.test_abonnements import ADMIN, _admin, abonnement_de, medias_temporaires, moyens, offres
from tests.test_parrainage_v2 import politique_b

FIXTURES = (medias_temporaires, moyens, offres, politique_b)
pytestmark = ADMIN

SESSION = "c9a17e2c-4b1a-4f0e-9c3d-2a1b3c4d5e6f"
SECRET = "whsec_test"


class FauxSaspay:
    """L'API SASPAY, telle que la decrit sa documentation, en memoire."""

    def __init__(self):
        self.appels = []
        self.panne = False
        self.statut = {"status": "PENDING", "transaction_status": None}
        self.session = {"amount": "15000.00", "currency": "XAF"}

    def __call__(self, methode, url, json=None, timeout=None, headers=None):
        self.appels.append((methode, url, json, headers))
        if self.panne:
            raise saspay.httpx.ConnectError("injoignable")
        chemin = url.split("/api/v1", 1)[1]
        if methode == "POST" and chemin == "/checkout-sessions/":
            corps = {
                "id": SESSION,
                "checkout_url": "https://pay.saspay.me/checkout/abc",
                "status": "PENDING",
                **json,
            }
        elif chemin == f"/checkout-sessions/{SESSION}/status/":
            corps = {
                "id": SESSION,
                "transaction_id": "TX-1",
                "transaction_reference": "REF-1",
                **self.statut,
            }
        elif chemin == f"/checkout-sessions/{SESSION}/":
            intention = SaspayIntent.objects.first()
            corps = {
                "id": SESSION,
                "metadata": {"intention": str(intention.pk) if intention else ""},
                **self.session,
            }
        elif chemin == f"/checkout-sessions/{SESSION}/cancel/":
            corps = {"id": SESSION, "status": "CANCELLED"}
        else:
            raise AssertionError(f"Route inattendue : {methode} {chemin}")
        return Reponse(corps)


class Reponse:
    def __init__(self, corps):
        self.corps = corps

    def raise_for_status(self):
        pass

    def json(self):
        return self.corps


@pytest.fixture
def api(monkeypatch):
    faux = FauxSaspay()
    monkeypatch.setattr(saspay.httpx, "request", faux)
    return faux


@pytest.fixture
def config(settings, salon_a, offres, api):
    """Un salon au Cameroun, SASPAY ouvert en mode test, un paiement ouvert."""
    settings.DEBUG = True
    settings.SASPAY_ENABLED = True
    settings.SASPAY_SANDBOX = True
    settings.SASPAY_TEST_SECRET_KEY = "sk_test_cle"
    settings.SASPAY_TEST_WEBHOOK_SECRET = SECRET
    salon_a.tenant.country, salon_a.tenant.currency = "CM", "XAF"
    salon_a.tenant.save(update_fields=["country", "currency"])
    abonnement_de(salon_a)
    PlanPrice.objects.update_or_create(
        plan=offres["mensuel"], currency="XAF", defaults={"amount": 15000, "active": True}
    )
    moyen = PlatformPaymentMethod.objects.create(kind="saspay", country="CM", currency="XAF")
    corps = {"plan": "monthly", "country": "CM", "currency": "XAF", "method": moyen.pk}
    with as_tenant(salon_a.tenant):
        intention = saspay.preparer(salon_a.tenant.pk, salon_a.owner, corps)
    return intention, corps


def demande(salon):
    with as_tenant(salon.tenant):
        return SubscriptionPaymentRequest.objects.get()


def signer(corps: bytes, horodatage=None, secret=SECRET):
    horodatage = str(int(horodatage or time.time()))
    signature = hmac.new(
        secret.encode(), horodatage.encode() + b"." + corps, hashlib.sha256
    ).hexdigest()
    return {"HTTP_X_WEBHOOK_SIGNATURE": signature, "HTTP_X_WEBHOOK_TIMESTAMP": horodatage}


# ---------------------------------------------------------------------------
# Couverture
# ---------------------------------------------------------------------------


def test_saspay_et_kkiapay_ne_se_recouvrent_pas():
    assert not saspay.PAYS_COUVERTS & PAYS_DOCUMENTES
    assert set(Tenant.Country.values) >= saspay.PAYS_COUVERTS


@pytest.mark.parametrize(
    "pays, devises",
    [("KE", {"KES", "USD"}), ("CM", {"XAF", "USD"}), ("ML", {"XOF", "USD"}), ("CG", {"USD"}),
     ("BJ", set()), ("CN", set())],
)
def test_chaque_pays_a_ses_devises(pays, devises):
    assert saspay.devises_acceptees(pays) == devises


def test_ferme_sans_cles_et_en_mode_test_hors_debug(settings):
    settings.SASPAY_ENABLED = True
    settings.SASPAY_SANDBOX = True
    settings.DEBUG = True
    assert not saspay.disponible()
    settings.SASPAY_TEST_SECRET_KEY = "sk_test_cle"
    settings.SASPAY_TEST_WEBHOOK_SECRET = SECRET
    assert saspay.disponible()
    settings.DEBUG = False
    assert not saspay.disponible()


def test_un_moyen_saspay_mal_regle_n_est_pas_propose(config):
    hors_pays = PlatformPaymentMethod(kind="saspay", country="BJ", currency="XOF")
    mauvaise_devise = PlatformPaymentMethod(kind="saspay", country="CM", currency="XOF")
    carte = PlatformPaymentMethod(kind="saspay", country="CG", currency="USD")
    assert hors_pays.problemes()
    assert mauvaise_devise.problemes()
    assert not carte.problemes()


# ---------------------------------------------------------------------------
# Ouvrir un paiement
# ---------------------------------------------------------------------------


def test_preparer_ouvre_une_session_hebergee(salon_a, config, api):
    intention, _ = config

    assert intention["checkout_url"] == "https://pay.saspay.me/checkout/abc"
    methode, url, corps, entetes = api.appels[0]
    assert (methode, url) == ("POST", "https://api.saspay.me/api/v1/checkout-sessions/")
    assert entetes["Authorization"] == "Bearer sk_test_cle"
    assert corps["amount"] == "15000.00" and corps["currency"] == "XAF"
    assert corps["country"] == "CM"
    assert corps["return_url"].endswith(f"/abonnement?saspay={intention['id']}")
    assert corps["metadata"]["intention"] == intention["id"]
    d = demande(salon_a)
    assert d.status == "pending" and d.method_kind == "saspay"
    assert SaspayIntent.objects.get().session_id == SESSION


def test_un_second_clic_reprend_la_meme_session(salon_a, config, api):
    intention, corps = config
    with as_tenant(salon_a.tenant):
        assert saspay.preparer(salon_a.tenant.pk, salon_a.owner, corps)["id"] == intention["id"]
    assert len([a for a in api.appels if a[0] == "POST"]) == 1


def test_saspay_muet_ne_laisse_aucune_demande(settings, salon_a, offres, api):
    settings.DEBUG = True
    settings.SASPAY_ENABLED = True
    settings.SASPAY_TEST_SECRET_KEY = "sk_test_cle"
    settings.SASPAY_TEST_WEBHOOK_SECRET = SECRET
    salon_a.tenant.country, salon_a.tenant.currency = "KE", "KES"
    salon_a.tenant.save(update_fields=["country", "currency"])
    abonnement_de(salon_a)
    PlanPrice.objects.create(plan=offres["mensuel"], currency="KES", amount=1500)
    moyen = PlatformPaymentMethod.objects.create(kind="saspay", country="KE", currency="KES")
    api.panne = True

    with as_tenant(salon_a.tenant), pytest.raises(billing.PaiementRefuse) as exc:
        saspay.preparer(
            salon_a.tenant.pk,
            salon_a.owner,
            {"plan": "monthly", "country": "KE", "currency": "KES", "method": moyen.pk},
        )

    assert exc.value.code == "saspay_indisponible"
    assert not SaspayIntent.objects.exists()
    with as_tenant(salon_a.tenant):
        assert not SubscriptionPaymentRequest.objects.exists()


def test_un_pays_kkiapay_est_refuse(settings, salon_a, config):
    _, corps = config
    salon_a.tenant.country = "BJ"
    salon_a.tenant.save(update_fields=["country"])
    with as_tenant(salon_a.tenant), pytest.raises(billing.PaiementRefuse) as exc:
        saspay.preparer(salon_a.tenant.pk, salon_a.owner, {**corps, "country": "BJ"})
    assert exc.value.code == "pays_non_pris_en_charge"


# ---------------------------------------------------------------------------
# Confirmer
# ---------------------------------------------------------------------------


def test_une_session_pas_encore_payee_n_active_rien(salon_a, config):
    intention, _ = config

    assert saspay.confirmer(intention["id"]) == {"confirme": False, "statut": "pending"}
    assert demande(salon_a).status == "pending"


def test_une_session_payee_prolonge_l_abonnement_une_fois(salon_a, config, api):
    intention, _ = config
    api.statut = {"status": "PAID", "transaction_status": "SUCCESS"}

    assert saspay.confirmer(intention["id"])["confirme"] is True
    assert saspay.confirmer(intention["id"])["confirme"] is True

    d = demande(salon_a)
    assert d.status == "approved" and d.reference == "REF-1"
    with as_tenant(salon_a.tenant):
        assert Invoice.objects.count() == 1
    i = SaspayIntent.objects.get()
    assert (i.statut, i.transaction_id) == ("confirme", "TX-1")


@pytest.mark.parametrize(
    "session",
    [{"amount": "14999.00"}, {"currency": "XOF"}, {"metadata": {"intention": "autre"}}],
)
def test_une_session_qui_ne_concorde_pas_n_active_rien(
    salon_a, config, api, session, monkeypatch
):
    intention, _ = config
    api.statut = {"status": "PAID", "transaction_status": "SUCCESS"}
    api.session = {"amount": "15000.00", "currency": "XAF", **session}
    original = api.__call__

    def appel(methode, url, **kw):
        reponse = original(methode, url, **kw)
        if url.endswith(f"/checkout-sessions/{SESSION}/") and "metadata" in session:
            reponse.corps["metadata"] = session["metadata"]
        return reponse

    monkeypatch.setattr(saspay.httpx, "request", appel)
    with pytest.raises(billing.PaiementRefuse):
        saspay.confirmer(intention["id"])
    assert demande(salon_a).status == "pending"
    with as_tenant(salon_a.tenant):
        assert not Invoice.objects.exists()


def test_un_echec_de_transaction_n_active_rien(salon_a, config, api):
    intention, _ = config
    api.statut = {"status": "PAID", "transaction_status": "FAILED"}
    assert saspay.confirmer(intention["id"])["confirme"] is False
    assert demande(salon_a).status == "pending"


def test_le_retour_du_salon_verifie_et_un_autre_salon_ne_voit_rien(
    api_client, salon_a, salon_b, config, api
):
    intention, _ = config
    api.statut = {"status": "PAID", "transaction_status": "SUCCESS"}

    api_client.force_login(salon_b.owner)
    autre = api_client.post(
        "/api/v1/billing/saspay/confirm", {"intention": intention["id"]}, format="json"
    )
    assert autre.status_code == 404

    api_client.force_login(salon_a.owner)
    reponse = api_client.post(
        "/api/v1/billing/saspay/confirm",
        {"intention": intention["id"]},
        format="json",
        HTTP_X_TENANT_ID=str(salon_a.tenant.pk),
    )
    assert reponse.status_code == 200, reponse.content
    assert reponse.json()["confirme"] is True
    assert demande(salon_a).status == "approved"


def test_aucun_administrateur_n_approuve_a_la_main(salon_a, config):
    with pytest.raises(billing.PaiementRefuse) as exc:
        billing.approuver_paiement(demande(salon_a).pk, administrateur=_admin())
    assert exc.value.code == "integration_requise"


# ---------------------------------------------------------------------------
# Webhook
# ---------------------------------------------------------------------------

URL = "/api/v1/webhooks/saspay/test"


def evenement(nom="transaction.success", transaction="TX-1") -> bytes:
    return json.dumps(
        {"event": nom, "data": {"id": transaction, "status": "SUCCESS", "amount": "15000.00"}}
    ).encode()


def test_un_webhook_non_signe_ou_perime_est_refuse(api_client, salon_a, config, api):
    api.statut = {"status": "PAID", "transaction_status": "SUCCESS"}
    corps = evenement()
    poster = lambda **entetes: api_client.generic(  # noqa: E731
        "POST", URL, corps, content_type="application/json", **entetes
    )

    assert poster().status_code == 403
    assert poster(**signer(corps, secret="faux")).status_code == 403
    assert poster(**signer(corps, horodatage=time.time() - 600)).status_code == 403
    # Le corps modifie apres signature ne passe pas.
    entetes = signer(corps)
    assert api_client.generic(
        "POST", URL, evenement(transaction="TX-2"), content_type="application/json", **entetes
    ).status_code == 403
    assert demande(salon_a).status == "pending"


def test_un_webhook_signe_declenche_la_verification(api_client, salon_a, config, api):
    api.statut = {"status": "PAID", "transaction_status": "SUCCESS"}
    corps = evenement()

    for _ in range(2):
        reponse = api_client.generic(
            "POST", URL, corps, content_type="application/json", **signer(corps)
        )
        assert reponse.status_code == 200, reponse.content
        assert reponse.json()["confirme"] is True

    assert demande(salon_a).status == "approved"
    with as_tenant(salon_a.tenant):
        assert Invoice.objects.count() == 1


def test_un_autre_evenement_est_accuse_sans_effet(api_client, salon_a, config, api):
    api.statut = {"status": "PAID", "transaction_status": "SUCCESS"}
    corps = evenement("transaction.failed")
    reponse = api_client.generic(
        "POST", URL, corps, content_type="application/json", **signer(corps)
    )
    assert reponse.status_code == 200
    assert demande(salon_a).status == "pending"


def test_une_api_muette_fait_retenter_saspay(api_client, salon_a, config, api):
    api.panne = True
    corps = evenement()
    reponse = api_client.generic(
        "POST", URL, corps, content_type="application/json", **signer(corps)
    )
    assert reponse.status_code == 503
    assert demande(salon_a).status == "pending"


# ---------------------------------------------------------------------------
# Expiration et filet
# ---------------------------------------------------------------------------


def test_un_paiement_abandonne_est_clos_et_sa_session_annulee(salon_a, config, api):
    intention, _ = config
    SaspayIntent.objects.update(expire_le=timezone.now() - timedelta(seconds=1))

    saspay.entretenir()

    assert SaspayIntent.objects.get().statut == "expire"
    assert demande(salon_a).status == "rejected"
    assert any(url.endswith("/cancel/") for _, url, *_ in api.appels)


def test_un_paiement_de_derniere_minute_n_est_pas_perdu(salon_a, config, api):
    intention, _ = config
    SaspayIntent.objects.update(expire_le=timezone.now() - timedelta(seconds=1))
    api.statut = {"status": "PAID", "transaction_status": "SUCCESS"}

    saspay.entretenir()

    assert SaspayIntent.objects.get().statut == "confirme"
    assert demande(salon_a).status == "approved"


def test_une_api_muette_ne_clot_rien(salon_a, config, api):
    SaspayIntent.objects.update(expire_le=timezone.now() - timedelta(seconds=1))
    api.panne = True

    saspay.entretenir()

    assert SaspayIntent.objects.get().statut == "en_attente"
    assert demande(salon_a).status == "pending"


def test_le_filet_confirme_un_paiement_sans_webhook(salon_a, config, api):
    api.statut = {"status": "PAID", "transaction_status": "SUCCESS"}
    saspay.entretenir()
    assert demande(salon_a).status == "approved"


# ---------------------------------------------------------------------------
# Les nouveaux pays
# ---------------------------------------------------------------------------


def test_un_salon_peut_s_inscrire_au_kenya(api_client):
    reponse = api_client.post(
        "/api/v1/account/signup",
        {
            "salon_name": "Nairobi Glow",
            "slug": "nairobi-glow",
            "email": "owner@example.com",
            "password": "un-mot-de-passe-solide",
            "country": "KE",
            "timezone_name": "Africa/Nairobi",
            "currency": "KES",
            "accepts_terms": True,
        },
        format="json",
    )
    assert reponse.status_code == 201, reponse.content
    tenant = Tenant.objects.get(slug="nairobi-glow")
    assert (tenant.country, tenant.currency) == ("KE", "KES")
