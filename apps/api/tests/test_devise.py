"""Changer de devise sans réécrire le passé.

---------------------------------------------------------------------------
Ce qui est réellement en jeu
---------------------------------------------------------------------------

Un salon change de devise deux fois dans sa vie : quand il s'est trompé à
l'inscription, et quand il déménage. Les deux fois, l'opération touche à
tout ce qu'il vend — et, si l'on n'y prend pas garde, à tout ce qu'il a
vendu.

Trois affirmations doivent tenir, et ce fichier ne teste qu'elles :

  1. **Le catalogue suit.** Une pose à 25 000 francs ne vaut pas 25 000
     yuans. Si la devise bascule sans les prix, le salon affiche
     quatre-vingt-cinq fois son tarif.

  2. **L'histoire ne bouge pas.** Un rendez-vous encaissé en francs a
     rapporté des francs. Le recalculer réécrirait le livre de comptes d'un
     salon, ce qu'aucun logiciel n'a le droit de faire — et l'erreur serait
     invisible, puisque les totaux resteraient cohérents entre eux.

  3. **Sans taux, on ne fait rien.** Convertir une grille entière à un taux
     deviné est irrattrapable : le salon facturerait à ce prix pendant des
     mois sans savoir que le taux était faux.

Le taux est toujours fourni par le test. Aucun de ces tests n'appelle
l'API : une suite qui dépend d'un service extérieur échoue le jour où il
tombe, pour une raison qui n'a rien à voir avec le code.
"""

from decimal import Decimal
from unittest.mock import patch

import pytest

from apps.accounts.models import Membership
from apps.catalog.models import Service, ServiceOption
from apps.finance.models import Transaction
from apps.salons.models import SalonProfile, TravelZone
from apps.store.models import Product
from apps.tenants.models import Tenant
from apps.tenants.services.conversion import DeviseRefusee, convertir
from apps.tenants.services.devises import TauxIndisponible
from conftest import as_tenant
from tests.factories import MembershipFactory, UserFactory

PASSWORD = "motdepasse-solide"
ROUTE = "/api/v1/salon-currency"

# 1 XAF = 0,0117 CNY, soit 1 CNY ≈ 85 XAF. L'ordre de grandeur réel, figé :
# un taux inventé rendrait les assertions illisibles.
XAF_VERS_CNY = Decimal("0.0117340572")
CNY_VERS_XAF = Decimal("85.222015233")


def login(client, user):
    assert client.login(email=user.email, password=PASSWORD)
    return client


def en_xaf(salon):
    """Repositionne le salon en francs CFA, catalogue compris."""
    Tenant.objects.filter(pk=salon.tenant.id).update(currency="XAF")
    salon.tenant.refresh_from_db()
    with as_tenant(salon.tenant):
        Service.objects.filter(pk=salon.service.pk).update(
            price_amount=Decimal("25000")
        )
        SalonProfile.objects.get_or_create(tenant=salon.tenant)
    return salon


# ---------------------------------------------------------------------------
# 1. Le catalogue suit
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_catalogue_follows_the_currency(salon_a):
    en_xaf(salon_a)

    with as_tenant(salon_a.tenant):
        option = ServiceOption.objects.create(
            tenant=salon_a.tenant,
            service=salon_a.service,
            name="Mèches XXL",
            price_delta=Decimal("4000"),
        )
        article = Product.objects.create(
            tenant=salon_a.tenant, name="Mèches", price=Decimal("3500"), stock=10
        )
        secteur = TravelZone.objects.create(
            tenant=salon_a.tenant, name="Bacongo", fee_amount=Decimal("2000")
        )

        with patch(
            "apps.tenants.services.conversion.taux", return_value=XAF_VERS_CNY
        ):
            resultat = convertir(salon_a.tenant, "CNY")

        salon_a.service.refresh_from_db()
        option.refresh_from_db()
        article.refresh_from_db()
        secteur.refresh_from_db()

    assert resultat["vers"] == "CNY"
    # 25 000 × 0,01173… = 293,35, arrondi au centime supérieur.
    assert salon_a.service.price_amount == Decimal("293.36")
    assert option.price_delta == Decimal("46.94")
    assert article.price == Decimal("41.07")
    assert secteur.fee_amount == Decimal("23.47")
    assert Tenant.objects.get(pk=salon_a.tenant.id).currency == "CNY"


@pytest.mark.django_db
def test_a_franc_price_has_no_cents(salon_a):
    """Le franc CFA n'a pas de centimes : l'arrondi suit la devise d'arrivée.

    Sans cela, un catalogue converti vers le CFA se serait rempli de
    « 23 863,47 F », un montant qui ne peut pas être encaissé.
    """
    with as_tenant(salon_a.tenant):
        Service.objects.filter(pk=salon_a.service.pk).update(
            price_amount=Decimal("280.00")
        )
        Tenant.objects.filter(pk=salon_a.tenant.id).update(currency="CNY")
        salon_a.tenant.refresh_from_db()

        with patch(
            "apps.tenants.services.conversion.taux", return_value=CNY_VERS_XAF
        ):
            convertir(salon_a.tenant, "XAF")

        salon_a.service.refresh_from_db()

    assert salon_a.service.price_amount == Decimal("23863.00")


@pytest.mark.django_db
def test_a_free_line_stays_free(salon_a):
    """« Offert » n'a pas de taux de change."""
    en_xaf(salon_a)

    with as_tenant(salon_a.tenant):
        gratuite = TravelZone.objects.create(
            tenant=salon_a.tenant, name="Centre-ville", fee_amount=Decimal("0")
        )

        with patch(
            "apps.tenants.services.conversion.taux", return_value=XAF_VERS_CNY
        ):
            convertir(salon_a.tenant, "CNY")

        gratuite.refresh_from_db()

    assert gratuite.fee_amount == Decimal("0")


# ---------------------------------------------------------------------------
# 2. L'histoire ne bouge pas
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_past_bookings_keep_the_currency_they_were_sold_in(salon_a):
    """Le cœur de la sûreté de cette fonctionnalité.

    Sans la colonne `currency` sur le rendez-vous, les 25 000 francs d'une
    pose de l'an dernier se seraient affichés comme 25 000 yuans — le
    montant intact sous une étiquette fausse, ce qui est la pire des deux
    erreurs : rien dans les totaux ne le signale.
    """
    from tests.test_dashboard_api import make_booking

    en_xaf(salon_a)

    with as_tenant(salon_a.tenant):
        passe = make_booking(salon_a, total_amount=Decimal("25000"))
        assert passe.currency == "XAF", "la devise est figée à la création"

        with patch(
            "apps.tenants.services.conversion.taux", return_value=XAF_VERS_CNY
        ):
            convertir(salon_a.tenant, "CNY")

        passe.refresh_from_db()

    # L'étiquette *et* le montant : c'est leur couple qui dit la vérité. Un
    # montant intact sous une étiquette fausse ment tout autant.
    assert passe.currency == "XAF"
    assert passe.total_amount == Decimal("25000")


@pytest.mark.django_db
def test_the_ledger_keeps_its_own_currency(salon_a):
    """Un livre de comptes ne se réétiquette pas."""
    en_xaf(salon_a)

    with as_tenant(salon_a.tenant):
        ecriture = Transaction.objects.create(
            tenant=salon_a.tenant,
            kind=Transaction.Kind.INCOME,
            category=Transaction.IncomeCategory.SERVICE,
            label="Box braids",
            amount=Decimal("25000"),
            occurred_on="2026-03-01",
        )
        assert ecriture.currency == "XAF"

        with patch(
            "apps.tenants.services.conversion.taux", return_value=XAF_VERS_CNY
        ):
            convertir(salon_a.tenant, "CNY")

        ecriture.refresh_from_db()

    assert ecriture.currency == "XAF"
    assert ecriture.amount == Decimal("25000")


@pytest.mark.django_db
def test_a_new_booking_takes_the_new_currency(salon_a):
    """Après la bascule, ce qui se vend se vend dans la nouvelle devise."""
    from tests.test_dashboard_api import make_booking

    en_xaf(salon_a)

    with as_tenant(salon_a.tenant):
        with patch(
            "apps.tenants.services.conversion.taux", return_value=XAF_VERS_CNY
        ):
            convertir(salon_a.tenant, "CNY")

        neuf = make_booking(salon_a)

    assert neuf.currency == "CNY"


# ---------------------------------------------------------------------------
# 3. Sans taux, on ne fait rien
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_no_rate_means_no_conversion_at_all(salon_a):
    """Ni les prix, ni la devise : rien ne bouge à moitié.

    Un salon dont la devise aurait basculé sans ses prix afficherait
    25 000 yuans pour une pose. La transaction garantit que les deux
    avancent ensemble ou pas du tout.
    """
    en_xaf(salon_a)

    with as_tenant(salon_a.tenant):
        with (
            patch(
                "apps.tenants.services.conversion.taux",
                side_effect=TauxIndisponible("service injoignable"),
            ),
            pytest.raises(TauxIndisponible),
        ):
            convertir(salon_a.tenant, "CNY")

        salon_a.service.refresh_from_db()

    assert salon_a.service.price_amount == Decimal("25000")
    assert Tenant.objects.get(pk=salon_a.tenant.id).currency == "XAF"


@pytest.mark.django_db
def test_switching_to_the_same_currency_is_refused(salon_a):
    en_xaf(salon_a)
    with as_tenant(salon_a.tenant), pytest.raises(DeviseRefusee):
        convertir(salon_a.tenant, "XAF")


# ---------------------------------------------------------------------------
# La route, et qui a le droit
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_preview_shows_what_would_happen(api_client, salon_a):
    """L'aperçu n'écrit rien : c'est ce qui le rend consultable sans risque."""
    en_xaf(salon_a)
    login(api_client, salon_a.owner)

    with patch("apps.tenants.services.conversion.taux", return_value=XAF_VERS_CNY):
        reponse = api_client.get(f"{ROUTE}?vers=CNY")

    assert reponse.status_code == 200, reponse.data
    apercu = reponse.data["preview"]
    assert apercu["de"] == "XAF"
    assert apercu["vers"] == "CNY"
    assert apercu["exemple"]["avant"] == "25000.00"
    assert apercu["exemple"]["apres"] == "293.36"

    with as_tenant(salon_a.tenant):
        salon_a.service.refresh_from_db()
    assert salon_a.service.price_amount == Decimal("25000")
    assert Tenant.objects.get(pk=salon_a.tenant.id).currency == "XAF"


@pytest.mark.django_db
def test_the_country_suggests_a_currency_without_imposing_it(api_client, salon_a):
    """Le détecteur signale, il ne corrige pas.

    Un salon chinois qui facture en francs a peut-être une raison ; décider
    à sa place de convertir tout son catalogue serait une correction plus
    grave que l'erreur.
    """
    en_xaf(salon_a)
    Tenant.objects.filter(pk=salon_a.tenant.id).update(country=Tenant.Country.CHINA)
    login(api_client, salon_a.owner)

    reponse = api_client.get(ROUTE)

    assert reponse.status_code == 200
    assert reponse.data["currency"] == "XAF"
    assert reponse.data["expected"] == "CNY"
    assert reponse.data["mismatch"] is True
    # Rien n'a changé : signaler n'est pas agir.
    assert Tenant.objects.get(pk=salon_a.tenant.id).currency == "XAF"


@pytest.mark.django_db
def test_a_matching_country_raises_no_flag(api_client, salon_a):
    en_xaf(salon_a)
    Tenant.objects.filter(pk=salon_a.tenant.id).update(country=Tenant.Country.CONGO)
    login(api_client, salon_a.owner)

    reponse = api_client.get(ROUTE)

    assert reponse.data["mismatch"] is False


@pytest.mark.django_db
def test_the_receptionist_cannot_convert_the_catalogue(api_client, salon_a):
    """Retarifer tout un salon reste une décision de gérance."""
    en_xaf(salon_a)
    hote = UserFactory()
    MembershipFactory(
        tenant=salon_a.tenant, user=hote, role=Membership.Role.RECEPTIONIST
    )
    login(api_client, hote)

    reponse = api_client.post(ROUTE, {"currency": "CNY"}, format="json")

    assert reponse.status_code == 403
    assert Tenant.objects.get(pk=salon_a.tenant.id).currency == "XAF"


@pytest.mark.django_db
def test_an_unavailable_rate_answers_503(api_client, salon_a):
    """503 et non 400 : la demande est bonne, c'est nous qui ne pouvons pas."""
    en_xaf(salon_a)
    login(api_client, salon_a.owner)

    with patch(
        "apps.tenants.services.conversion.taux",
        side_effect=TauxIndisponible("service injoignable"),
    ):
        reponse = api_client.post(ROUTE, {"currency": "CNY"}, format="json")

    assert reponse.status_code == 503
    assert reponse.data["code"] == "taux_indisponible"
