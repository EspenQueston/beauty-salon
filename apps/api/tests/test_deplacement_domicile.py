"""Le deplacement a domicile, de bout en bout.

---------------------------------------------------------------------------
Les deux pannes que ce fichier garde
---------------------------------------------------------------------------

**Un reglage qui n'en commandait pas un autre.** Le salon declarait
« a domicile », posait ses quartiers et leurs forfaits, et son parcours de
reservation n'offrait jamais le deplacement. La cause vivait ailleurs :
chaque prestation porte son propre lieu, et il valait « au salon » par
defaut. Deux ecrans parlaient du meme sujet sans se parler, et le symptome -
« mes zones ne servent a rien » - ne designait pas sa cause.

**Une recette qu'on ne pouvait pas lire.** Le forfait entrait bien dans le
total du rendez-vous, donc dans le chiffre d'affaires - mais fondu dans la
ligne « Prestation ». Le salon voyait la depense de trajet d'un cote et rien
en face de l'autre : il en concluait que le domicile lui coutait de
l'argent. Le forfait a desormais sa categorie, et les deux lignes se font
face.

Ce qui est verifie ici n'est pas que les champs s'enregistrent - ce serait
tester Django - mais ce qui doit rester vrai apres : le catalogue suit le
salon, le total inclut le forfait, et la comptabilite le distingue sans
jamais le compter deux fois.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.models import Membership
from apps.catalog.models import Service
from apps.finance.models import Transaction
from apps.salons.models import SalonProfile, ServiceMode, TravelZone
from apps.scheduling.models import Booking
from conftest import as_tenant
from tests.factories import MembershipFactory, UserFactory

PASSWORD = "motdepasse-solide"
PROFIL = "/api/v1/salon-profile"


def login(client, user):
    assert client.login(email=user.email, password=PASSWORD)
    return client


def profil(salon) -> SalonProfile:
    with as_tenant(salon.tenant):
        fiche, _ = SalonProfile.objects.get_or_create(tenant=salon.tenant)
        return fiche


def zone(salon, nom="Tianhe", frais="50") -> TravelZone:
    with as_tenant(salon.tenant):
        return TravelZone.objects.create(
            tenant=salon.tenant, name=nom, fee_amount=Decimal(frais), active=True
        )


# ---------------------------------------------------------------------------
# Le catalogue suit le salon
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_opening_home_visits_opens_the_catalogue_too(api_client, salon_a):
    """Le geste attendu : un seul reglage, et le domicile est reservable.

    Sans cet alignement, la gerante devait rouvrir chacune de ses
    prestations pour changer un champ dont rien ne lui signale l'existence.
    """
    login(api_client, salon_a.owner)

    reponse = api_client.patch(PROFIL, {"service_mode": "hybrid"}, format="json")

    assert reponse.status_code == 200, reponse.data
    assert reponse.data["prestations_alignees"] == 1
    with as_tenant(salon_a.tenant):
        assert Service.objects.get(pk=salon_a.service.pk).location_mode == "hybrid"


@pytest.mark.django_db
def test_a_service_set_apart_keeps_its_own_place(api_client, salon_a):
    """Ce qui a ete decide ne se defait pas tout seul.

    Une prestation deja reglee sur « a domicile » n'est pas une valeur par
    defaut oubliee : c'est un choix, et l'alignement ne le recouvre pas.
    """
    with as_tenant(salon_a.tenant):
        autre = Service.objects.create(
            tenant=salon_a.tenant,
            category=salon_a.category,
            name="Retouche express",
            duration_minutes=30,
            price_amount=Decimal("5000"),
            location_mode=ServiceMode.HOME,
        )

    login(api_client, salon_a.owner)
    api_client.patch(PROFIL, {"service_mode": "hybrid"}, format="json")

    with as_tenant(salon_a.tenant):
        assert Service.objects.get(pk=autre.pk).location_mode == ServiceMode.HOME


@pytest.mark.django_db
def test_closing_home_visits_does_not_close_the_catalogue(api_client, salon_a):
    """Le sens inverse n'existe pas.

    Retirer des prestations de la vente est une decision commerciale, pas la
    consequence mecanique d'un changement d'adresse. Le salon les ferme
    lui-meme s'il le veut.
    """
    fiche = profil(salon_a)
    with as_tenant(salon_a.tenant):
        fiche.service_mode = ServiceMode.HYBRID
        fiche.save(update_fields=["service_mode"])
        Service.objects.filter(pk=salon_a.service.pk).update(
            location_mode=ServiceMode.HYBRID
        )

    login(api_client, salon_a.owner)
    reponse = api_client.patch(PROFIL, {"service_mode": "salon"}, format="json")

    assert reponse.status_code == 200
    assert "prestations_alignees" not in reponse.data
    with as_tenant(salon_a.tenant):
        assert (
            Service.objects.get(pk=salon_a.service.pk).location_mode
            == ServiceMode.HYBRID
        )


@pytest.mark.django_db
def test_a_new_service_starts_where_the_salon_works(api_client, salon_a):
    """La valeur de depart vient du salon, pas d'une constante.

    Sans cela, chaque prestation creee apres le reglage repartait sur « au
    salon » et rouvrait le trou qu'on vient de boucher.
    """
    fiche = profil(salon_a)
    with as_tenant(salon_a.tenant):
        fiche.service_mode = ServiceMode.HYBRID
        fiche.save(update_fields=["service_mode"])

    login(api_client, salon_a.owner)
    reponse = api_client.post(
        "/api/v1/services/",
        {
            "category": str(salon_a.category.id),
            "name": "Pose gel",
            "duration_minutes": 60,
            "price_amount": "12000",
        },
        format="json",
    )

    assert reponse.status_code == 201, reponse.data
    assert reponse.data["location_mode"] == ServiceMode.HYBRID


@pytest.mark.django_db
def test_the_receptionist_cannot_move_the_whole_catalogue(api_client, salon_a):
    """Un effet de bord aussi large reste une decision de gerance."""
    hote = UserFactory()
    MembershipFactory(
        tenant=salon_a.tenant, user=hote, role=Membership.Role.RECEPTIONIST
    )
    login(api_client, hote)

    reponse = api_client.patch(PROFIL, {"service_mode": "hybrid"}, format="json")

    assert reponse.status_code == 403
    with as_tenant(salon_a.tenant):
        assert Service.objects.get(pk=salon_a.service.pk).location_mode == "salon"


# ---------------------------------------------------------------------------
# Le forfait est une recette, et elle se distingue
# ---------------------------------------------------------------------------


def rendez_vous_a_domicile(salon, frais="50") -> Booking:
    """Un rendez-vous honore, chez la cliente, avec son forfait."""
    zone_du_salon = zone(salon, frais=frais)
    debut = timezone.now() - timedelta(days=1)

    with as_tenant(salon.tenant):
        return Booking.objects.create(
            tenant=salon.tenant,
            customer=salon.customer,
            staff_member=salon.staff,
            service=salon.service,
            starts_at=debut,
            ends_at=debut + timedelta(minutes=60),
            status=Booking.Status.COMPLETED,
            service_name=salon.service.name,
            total_amount=salon.service.price_amount + Decimal(frais),
            travel_zone_name=zone_du_salon.name,
            travel_fee_amount=Decimal(frais),
            location_mode=ServiceMode.HOME,
        )


@pytest.mark.django_db
def test_the_travel_fee_gets_its_own_income_line(salon_a):
    """Une ligne a part, sinon le graphique ne dit plus rien.

    Se deplacer n'est pas coiffer : c'est du carburant et du temps de
    trajet, et la depense correspondante existe deja de l'autre cote du
    livre. Fondu dans la prestation, le forfait rendait la comparaison
    impossible.
    """
    from apps.finance.services import record_booking_income

    reservation = rendez_vous_a_domicile(salon_a, frais="50")

    with as_tenant(salon_a.tenant):
        record_booking_income(reservation)

        trajet = Transaction.objects.get(
            booking=reservation, source=Transaction.Source.BOOKING_TRAVEL
        )
        assert trajet.category == Transaction.IncomeCategory.TRAVEL
        assert trajet.amount == Decimal("50")
        assert "Tianhe" in trajet.label


@pytest.mark.django_db
def test_the_travel_fee_is_never_counted_twice(salon_a):
    """Le solde se calcule sur ce qui reste.

    C'est le vrai risque de cette decoupe : une ligne de trajet **en plus**
    du total ferait apparaitre des recettes qui n'existent pas.
    """
    from apps.finance.services import record_booking_income

    reservation = rendez_vous_a_domicile(salon_a, frais="50")

    with as_tenant(salon_a.tenant):
        record_booking_income(reservation)

        total = sum(
            ligne.amount
            for ligne in Transaction.objects.filter(
                booking=reservation, kind=Transaction.Kind.INCOME
            )
        )
        assert total == reservation.total_amount


@pytest.mark.django_db
def test_recording_twice_changes_nothing(salon_a):
    """Constater deux fois le meme rendez-vous ne double pas la recette."""
    from apps.finance.services import record_booking_income

    reservation = rendez_vous_a_domicile(salon_a, frais="50")

    with as_tenant(salon_a.tenant):
        record_booking_income(reservation)
        record_booking_income(reservation)

        lignes = Transaction.objects.filter(booking=reservation)
        assert lignes.filter(source=Transaction.Source.BOOKING_TRAVEL).count() == 1
        assert sum(ligne.amount for ligne in lignes) == reservation.total_amount


@pytest.mark.django_db
def test_a_free_zone_writes_no_line(salon_a):
    """Zero n'est pas une recette.

    Une zone desservie gratuitement est un choix commercial. Une ligne a
    zero encombrerait les mouvements sans rien apprendre.
    """
    from apps.finance.services import record_booking_income

    reservation = rendez_vous_a_domicile(salon_a, frais="0")

    with as_tenant(salon_a.tenant):
        record_booking_income(reservation)

        assert not Transaction.objects.filter(
            booking=reservation, source=Transaction.Source.BOOKING_TRAVEL
        ).exists()


@pytest.mark.django_db
def test_a_salon_visit_writes_no_travel_line(salon_a):
    """Rien a facturer quand personne ne s'est deplace."""
    from apps.finance.services import record_booking_income

    debut = timezone.now() - timedelta(days=1)
    with as_tenant(salon_a.tenant):
        reservation = Booking.objects.create(
            tenant=salon_a.tenant,
            customer=salon_a.customer,
            staff_member=salon_a.staff,
            service=salon_a.service,
            starts_at=debut,
            ends_at=debut + timedelta(minutes=60),
            status=Booking.Status.COMPLETED,
            service_name=salon_a.service.name,
            total_amount=salon_a.service.price_amount,
        )
        record_booking_income(reservation)

        assert not Transaction.objects.filter(
            booking=reservation, source=Transaction.Source.BOOKING_TRAVEL
        ).exists()


@pytest.mark.django_db
def test_the_travel_income_shows_up_in_the_breakdown(salon_a):
    """C'est la raison d'etre de la decoupe : la voir dans « d'ou vient
    l'argent »."""
    from apps.finance.services import by_category, record_booking_income

    reservation = rendez_vous_a_domicile(salon_a, frais="50")

    with as_tenant(salon_a.tenant):
        record_booking_income(reservation)

        postes = {
            ligne["category"]: ligne["total"]
            for ligne in by_category(
                Transaction.objects.all(), Transaction.Kind.INCOME
            )
        }

    # `by_category` serialise ses totaux en chaine pour le JSON du tableau
    # de bord : on compare donc apres conversion, pas la representation.
    assert Decimal(postes[Transaction.IncomeCategory.TRAVEL]) == Decimal("50")
    assert Transaction.IncomeCategory.SERVICE in postes
