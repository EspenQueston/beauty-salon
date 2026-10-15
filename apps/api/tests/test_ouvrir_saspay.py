"""`ouvrir_saspay` : la grille, et une commande qu'on peut rejouer sans crainte.

  - la grille couvre chaque devise SASPAY, en montants entiers, l'année
    moins chère que douze mois, et reste à ±10 % du prix chinois converti ;
  - l'aperçu n'écrit rien ;
  - appliquée, chaque pays SASPAY apparaît au catalogue avec ses devises
    (Mobile Money dans la devise du pays + USD), et lui seul ;
  - rejouée, elle ne crée rien de plus et ne touche jamais un tarif existant.
"""

from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import call_command

from apps.billing import saspay
from apps.billing import services as billing
from apps.billing.management.commands.ouvrir_saspay import GRILLE, OFFRES
from apps.billing.models import Plan, PlanPrice, PlatformPaymentMethod
from tests.test_abonnements import ADMIN

pytestmark = ADMIN

# Les prix CNY de référence et le taux du 15/10/2026 (USD -> devise).
CNY = (99, 999, 399, 4000)
TAUX = {
    "USD": 1, "CNY": 6.706494, "XAF": 586.734089, "XOF": 586.734089, "CDF": 2311.135178,
    "GHS": 11.686603, "GNF": 8798.084341, "KES": 129.725167, "MWK": 1738.970488,
    "NGN": 1331.826337, "RWF": 1477.991603, "TZS": 2632.532076, "UGX": 4016.572723,
    "ZMW": 19.972416,
}


def lancer(*args):
    sortie = StringIO()
    call_command("ouvrir_saspay", *args, stdout=sortie, stderr=sortie)
    return sortie.getvalue()


@pytest.fixture
def offres(db):
    """Les quatre offres payantes, en CNY seulement, comme en production."""
    for (code, nom, mois, groupe), cny in zip(
        (
            ("monthly", "Mensuel", 1, "standard"),
            ("yearly", "Annuel", 12, "standard"),
            ("pro_monthly", "Pro mensuel", 1, "pro"),
            ("pro_yearly", "Pro annuel", 12, "pro"),
        ),
        CNY,
        strict=True,
    ):
        plan, _ = Plan.objects.update_or_create(
            code=code,
            defaults={"name": nom, "billing_months": mois, "group": groupe, "active": True},
        )
        PlanPrice.objects.filter(plan=plan).delete()
        PlanPrice.objects.create(plan=plan, currency="CNY", amount=Decimal(cny))


@pytest.fixture
def saspay_actif(settings):
    settings.DEBUG = True
    settings.SASPAY_ENABLED = True
    settings.SASPAY_SANDBOX = True
    settings.SASPAY_TEST_SECRET_KEY = "sk_test_cle"
    settings.SASPAY_TEST_WEBHOOK_SECRET = "whsec_test"


def test_la_grille_couvre_chaque_devise_et_reste_coherente():
    assert set(GRILLE) == {"USD", *saspay.MOBILE_MONEY.values()}
    for devise, (std_mois, std_an, pro_mois, pro_an) in GRILLE.items():
        assert all(isinstance(m, int) and m > 0 for m in GRILLE[devise]), devise
        assert std_an < 12 * std_mois and pro_an < 12 * pro_mois, devise
        assert pro_mois > std_mois and pro_an > std_an, devise
        for montant, prix_cny in zip(GRILLE[devise], CNY, strict=True):
            converti = prix_cny / TAUX["CNY"] * TAUX[devise]
            assert abs(montant - converti) / converti < 0.10, (devise, montant, round(converti))


def test_l_apercu_n_ecrit_rien(offres):
    texte = lancer()
    assert "Aperçu seulement" in texte
    assert not PlatformPaymentMethod.objects.filter(kind="saspay").exists()
    assert not PlanPrice.objects.filter(currency="XAF").exists()


def test_appliquee_chaque_pays_saspay_est_au_catalogue(offres, saspay_actif):
    lancer("--appliquer")
    catalogue = {p["code"]: p for p in billing.catalogue_de_paiement()}
    for pays in saspay.PAYS_COUVERTS:
        attendu = {saspay.MOBILE_MONEY[pays], "USD"}
        devises = {d["code"]: {m.kind for m in d["moyens"]} for d in catalogue[pays]["devises"]}
        assert set(devises) == attendu, pays
        assert all(genres == {"saspay"} for genres in devises.values()), pays
        canaux = {d["code"]: d["canal"] for d in catalogue[pays]["devises"]}
        assert canaux == {d: saspay.canal(pays, d) for d in attendu}, pays
    # Les quatre offres, dans chaque devise, aux montants de la grille.
    for devise, montants in GRILLE.items():
        for code, montant in zip(OFFRES, montants, strict=True):
            prix = PlanPrice.objects.get(plan__code=code, currency=devise)
            assert prix.amount == Decimal(montant) and prix.active


def test_rejouee_elle_ne_cree_rien_et_ne_touche_aucun_tarif(offres, saspay_actif):
    mensuel = Plan.objects.get(code=Plan.Code.MONTHLY)
    PlanPrice.objects.create(plan=mensuel, currency="XAF", amount=Decimal("12345"))
    lancer("--appliquer")
    moyens_apres_un = PlatformPaymentMethod.objects.filter(kind="saspay").count()
    prix_apres_un = PlanPrice.objects.count()

    texte = lancer("--appliquer")
    assert PlatformPaymentMethod.objects.filter(kind="saspay").count() == moyens_apres_un == 26
    assert PlanPrice.objects.count() == prix_apres_un
    assert PlanPrice.objects.get(plan=mensuel, currency="XAF").amount == Decimal("12345")
    assert "conservé" in texte


def test_limitee_a_un_pays(offres, saspay_actif):
    lancer("--appliquer", "--pays", "cm")
    assert sorted(
        PlatformPaymentMethod.objects.filter(kind="saspay").values_list("country", "currency")
    ) == [("CM", "USD"), ("CM", "XAF")]
    assert set(PlanPrice.objects.values_list("currency", flat=True)) >= {"XAF", "USD"}
    assert not PlanPrice.objects.filter(currency="NGN").exists()
    assert "non couverts" in lancer("--pays", "BJ")


def test_la_devise_du_pays_passe_avant_la_carte(offres, saspay_actif):
    lancer("--appliquer")
    catalogue = {p["code"]: p for p in billing.catalogue_de_paiement()}
    for pays, locale in saspay.MOBILE_MONEY.items():
        assert [d["code"] for d in catalogue[pays]["devises"]] == [locale, "USD"], pays


def test_un_salon_ne_se_voit_proposer_saspay_que_dans_son_pays(
    api_client, salon_a, offres, saspay_actif
):
    """Le serveur refuse SASPAY hors du pays du salon : il ne le propose donc
    pas ailleurs. Un moyen déclaré à la main reste proposé partout."""
    lancer("--appliquer")
    PlatformPaymentMethod.objects.create(
        kind="mobile_money", country="KE", currency="KES", provider_name="M-Pesa",
        account_number="0700000000", account_holder="Plateforme",
    )
    salon_a.tenant.country, salon_a.tenant.currency = "CM", "XAF"
    salon_a.tenant.save(update_fields=["country", "currency"])

    catalogue = {p["code"]: p for p in billing.catalogue_du_salon("CM")}
    assert {d["code"] for d in catalogue["CM"]["devises"]} == {"XAF", "USD"}
    assert set(catalogue) == {"CM", "KE"}
    assert [m.kind for d in catalogue["KE"]["devises"] for m in d["moyens"]] == ["mobile_money"]

    api_client.force_login(salon_a.owner)
    reponse = api_client.get("/api/v1/subscription/offres", HTTP_X_TENANT_ID=str(salon_a.tenant.pk))
    assert reponse.status_code == 200, reponse.content
    pays = {p["code"]: p for p in reponse.json()["pays"]}
    assert set(pays) == {"CM", "KE"}
    assert [d["code"] for d in pays["CM"]["devises"]] == ["XAF", "USD"]
