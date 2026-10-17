"""Chaque pays avec son prestataire : SASPAY et KKIAPAY, de bout en bout.

Les reponses des prestataires sont simulees (leurs API ne sont pas appelees
ici) ; tout le reste est reel : catalogue, demande de paiement, montant,
verification, approbation, facture. Pour chaque pays couvert :

  - KKIAPAY (6 pays, XOF) : un paiement s'ouvre et se confirme ; les pays
    SASPAY sont refuses ;
  - SASPAY (13 pays) : un paiement s'ouvre dans la devise du pays et en USD
    (carte), la session est creee avec le bon pays et la bonne devise, et la
    confirmation prolonge l'abonnement ; les pays KKIAPAY sont refuses ;
  - le catalogue propose chaque pays avec son prestataire, et lui seul.
"""

import pytest

from apps.billing import kkiapay, saspay
from apps.billing import services as billing
from apps.billing.models import Invoice, Plan, PlanPrice, PlatformPaymentMethod, SubscriptionPaymentRequest
from conftest import as_tenant
from tests.test_abonnements import ADMIN, abonnement_de, medias_temporaires, moyens, offres
from tests.test_parrainage_v2 import politique_b
from tests.test_saspay import FauxSaspay

FIXTURES = (medias_temporaires, moyens, offres, politique_b)
pytestmark = ADMIN

KKIAPAY = sorted(kkiapay.PAYS_DOCUMENTES)
SASPAY = sorted(saspay.PAYS_COUVERTS)
# Un montant entier : les devises sans centimes (XOF, XAF, GNF...) l'exigent.
MONTANT = 15000


def preparer_salon(salon, pays, devise):
    salon.tenant.country, salon.tenant.currency = pays, devise
    salon.tenant.save(update_fields=["country", "currency"])
    abonnement_de(salon)
    mensuel = Plan.objects.get(code=Plan.Code.MONTHLY)
    PlanPrice.objects.update_or_create(
        plan=mensuel, currency=devise, defaults={"amount": MONTANT, "active": True}
    )


@pytest.fixture
def saspay_ouvert(settings, monkeypatch):
    settings.DEBUG = True
    settings.SASPAY_ENABLED = True
    settings.SASPAY_SANDBOX = True
    settings.SASPAY_TEST_SECRET_KEY = "sk_test_cle"
    settings.SASPAY_TEST_WEBHOOK_SECRET = "whsec_test"
    faux = FauxSaspay()
    monkeypatch.setattr(saspay.httpx, "request", faux)
    return faux


@pytest.fixture
def kkiapay_ouvert(settings):
    settings.DEBUG = True
    settings.KKIAPAY_ENABLED = True
    settings.KKIAPAY_SANDBOX = True
    settings.KKIAPAY_ALLOWED_COUNTRIES = KKIAPAY
    for suffixe in ("PUBLIC_KEY", "PRIVATE_KEY", "SECRET_KEY", "WEBHOOK_SECRET"):
        setattr(settings, "KKIAPAY_TEST_" + suffixe, "test-" + suffixe)


# ---------------------------------------------------------------------------
# SASPAY : les 13 pays, devise du pays et USD
# ---------------------------------------------------------------------------

# Chaque pays dans sa devise Mobile Money, et en USD (carte).
CAS_SASPAY = [
    (pays, devise)
    for pays in SASPAY
    for devise in sorted({saspay.MOBILE_MONEY.get(pays, saspay.DEVISE_CARTE), saspay.DEVISE_CARTE})
]


@pytest.mark.parametrize("pays, devise", CAS_SASPAY)
def test_saspay_ouvre_et_confirme_un_paiement(salon_a, offres, saspay_ouvert, pays, devise):
    preparer_salon(salon_a, pays, devise)
    moyen = PlatformPaymentMethod.objects.create(kind="saspay", country=pays, currency=devise)
    assert not moyen.problemes(), moyen.problemes()

    with as_tenant(salon_a.tenant):
        intention = saspay.preparer(
            salon_a.tenant.pk,
            salon_a.owner,
            {"plan": "monthly", "country": pays, "currency": devise, "method": moyen.pk},
        )

    _, _, corps, _ = saspay_ouvert.appels[0]
    assert corps["currency"] == devise and corps["amount"] == f"{MONTANT}.00"
    # La carte (USD) ne preselectionne aucun pays ; le Mobile Money, le sien
    # (et en RDC l'USD aussi, payable par portefeuille en dollars).
    assert corps.get("country") == (None if saspay.canal(pays, devise) == "carte" else pays)

    saspay_ouvert.statut = {"status": "PAID", "transaction_status": "SUCCESS"}
    saspay_ouvert.session = {"amount": f"{MONTANT}.00", "currency": devise}
    assert saspay.confirmer(intention["id"])["confirme"] is True
    with as_tenant(salon_a.tenant):
        assert SubscriptionPaymentRequest.objects.get().status == "approved"
        assert Invoice.objects.get().currency == devise


@pytest.mark.parametrize("pays", KKIAPAY)
def test_saspay_refuse_les_pays_kkiapay(salon_a, offres, saspay_ouvert, pays):
    preparer_salon(salon_a, pays, "XOF")
    assert saspay.devises_acceptees(pays) == set()
    moyen = PlatformPaymentMethod(kind="saspay", country=pays, currency="XOF")
    assert moyen.problemes()
    with as_tenant(salon_a.tenant), pytest.raises(billing.PaiementRefuse) as exc:
        saspay.preparer(
            salon_a.tenant.pk,
            salon_a.owner,
            {"plan": "monthly", "country": pays, "currency": "XOF", "method": "00000000-0000-0000-0000-000000000000"},
        )
    assert exc.value.code == "pays_non_pris_en_charge"


# ---------------------------------------------------------------------------
# KKIAPAY : les 6 pays, XOF
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("pays", KKIAPAY)
def test_kkiapay_ouvre_et_confirme_un_paiement(salon_a, offres, kkiapay_ouvert, monkeypatch, pays):
    preparer_salon(salon_a, pays, "XOF")
    moyen = PlatformPaymentMethod.objects.create(kind="kkiapay", country=pays, currency="XOF")
    assert not moyen.problemes(), moyen.problemes()

    with as_tenant(salon_a.tenant):
        intention = kkiapay.preparer(
            salon_a.tenant.pk,
            salon_a.owner,
            {"plan": "monthly", "country": pays, "currency": "XOF", "method": moyen.pk},
        )
    assert intention["amount"] == MONTANT

    monkeypatch.setattr(
        kkiapay,
        "verifier_transaction",
        lambda *a: {"transactionId": "TX-" + pays, "status": "SUCCESS", "amount": MONTANT,
                    "currency": "XOF", "partnerId": intention["id"]},
    )
    assert kkiapay.confirmer(intention["id"], "TX-" + pays)["confirme"] is True
    with as_tenant(salon_a.tenant):
        assert SubscriptionPaymentRequest.objects.get().status == "approved"
        assert Invoice.objects.count() == 1


@pytest.mark.parametrize("pays", SASPAY)
def test_kkiapay_refuse_les_pays_saspay(salon_a, offres, kkiapay_ouvert, pays):
    devise = saspay.MOBILE_MONEY.get(pays, "XAF")
    preparer_salon(salon_a, pays, devise)
    with as_tenant(salon_a.tenant), pytest.raises(billing.PaiementRefuse) as exc:
        kkiapay.preparer(
            salon_a.tenant.pk,
            salon_a.owner,
            {"plan": "monthly", "country": pays, "currency": "XOF", "method": "00000000-0000-0000-0000-000000000000"},
        )
    assert exc.value.code == "pays_non_pris_en_charge"


# ---------------------------------------------------------------------------
# Le catalogue : chaque pays avec son prestataire, et lui seul
# ---------------------------------------------------------------------------


def test_le_catalogue_propose_chaque_pays_avec_son_prestataire(offres, saspay_ouvert, kkiapay_ouvert):
    mensuel = Plan.objects.get(code=Plan.Code.MONTHLY)
    for pays in KKIAPAY:
        PlatformPaymentMethod.objects.create(kind="kkiapay", country=pays, currency="XOF")
    for pays in SASPAY:
        for devise in {saspay.MOBILE_MONEY[pays], "USD"}:
            PlatformPaymentMethod.objects.create(kind="saspay", country=pays, currency=devise)
    for devise in {"XOF", "USD", *saspay.MOBILE_MONEY.values()}:
        PlanPrice.objects.update_or_create(plan=mensuel, currency=devise, defaults={"amount": MONTANT, "active": True})

    catalogue = {p["code"]: p for p in billing.catalogue_de_paiement()}

    for pays in KKIAPAY:
        genres = {m.kind for d in catalogue[pays]["devises"] for m in d["moyens"]}
        assert genres == {"kkiapay"}, pays
    for pays in SASPAY:
        devises = {d["code"]: {m.kind for m in d["moyens"]} for d in catalogue[pays]["devises"]}
        attendu = {saspay.MOBILE_MONEY[pays], "USD"}
        assert set(devises) == attendu, pays
        assert all(g == {"saspay"} for g in devises.values()), pays
