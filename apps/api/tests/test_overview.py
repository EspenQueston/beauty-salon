"""L'accueil du tableau de bord : ce que chaque chiffre promet.

Un tableau de bord se lit sans reflechir. C'est precisement ce qui le rend
dangereux : un chiffre faux n'y est pas verifie, il est cru. Ces tests
fixent donc ce que chaque nombre compte - et surtout ce qu'il ne compte pas.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.finance.models import Transaction
from apps.reviews.models import Review
from apps.scheduling.models import Booking
from conftest import as_tenant
from tests.factories import BookingFactory

PASSWORD = "motdepasse-solide"


def login(client, user):
    assert client.login(email=user.email, password=PASSWORD)
    return client


def read(api_client, salon):
    return api_client.get(
        "/api/v1/overview", headers={"X-Tenant-Id": str(salon.tenant.id)}
    )


def booking_at(salon, when, **overrides):
    with as_tenant(salon.tenant):
        return BookingFactory(
            tenant=salon.tenant,
            customer=salon.customer,
            staff_member=salon.staff,
            service=salon.service,
            starts_at=when,
            ends_at=when + timedelta(minutes=120),
            total_amount=Decimal("200"),
            **overrides,
        )


@pytest.mark.django_db
def test_the_overview_needs_a_session(api_client, salon_a):
    """Ces chiffres sont ceux d'un salon : ils ne se lisent pas sans compte."""
    assert read(api_client, salon_a).status_code in (401, 403)


@pytest.mark.django_db
def test_today_counts_only_today_and_never_the_cancelled(api_client, salon_a):
    """Un salon dont tout le monde s'est décommandé n'a pas une journée pleine."""
    login(api_client, salon_a.owner)
    now = timezone.now()

    booking_at(salon_a, now + timedelta(hours=2), status=Booking.Status.CONFIRMED)
    booking_at(salon_a, now + timedelta(hours=5), status=Booking.Status.CANCELLED)
    booking_at(salon_a, now + timedelta(days=3), status=Booking.Status.CONFIRMED)

    response = read(api_client, salon_a)

    assert response.status_code == 200, response.data
    assert response.data["today"]["count"] == 1
    assert response.data["today"]["revenue"] == "200.00"


@pytest.mark.django_db
def test_the_next_appointment_is_the_soonest_still_to_come(api_client, salon_a):
    login(api_client, salon_a.owner)
    now = timezone.now()

    booking_at(
        salon_a,
        now + timedelta(hours=6),
        status=Booking.Status.CONFIRMED,
        service_name="Twists",
    )
    booking_at(
        salon_a,
        now + timedelta(hours=2),
        status=Booking.Status.CONFIRMED,
        service_name="Box braids",
    )

    suivant = read(api_client, salon_a).data["today"]["next"]

    assert suivant["service_name"] == "Box braids"


@pytest.mark.django_db
def test_what_awaits_a_gesture_is_counted_apart(api_client, salon_a):
    """Ce ne sont pas des statistiques, ce sont des tâches.

    Chacune coûte quelque chose tant qu'elle n'est pas faite : une demande
    non acceptée bloque un créneau sans engagement, un créneau passé sans
    rien de noté fausse les statistiques d'absence.
    """
    login(api_client, salon_a.owner)
    now = timezone.now()

    booking_at(salon_a, now + timedelta(days=1), status=Booking.Status.REQUESTED)
    booking_at(salon_a, now - timedelta(days=1), status=Booking.Status.CONFIRMED)
    # Déjà traité : ni l'un ni l'autre.
    booking_at(salon_a, now - timedelta(days=2), status=Booking.Status.COMPLETED)

    attente = read(api_client, salon_a).data["attention"]

    assert attente["requests"] == 1
    # Seul le créneau d'hier resté « confirmé » attend une décision : celui
    # de demain n'est pas passé, et l'honoré est déjà tranché.
    assert attente["overdue"] == 1


@pytest.mark.django_db
def test_growth_is_absent_rather_than_infinite(api_client, salon_a):
    """Une croissance depuis zéro n'est pas un pourcentage.

    Afficher « +100 % » pour un premier mois d'activité est une invention ;
    afficher « — » dit la vérité, qui est qu'il n'y a rien à comparer.
    """
    login(api_client, salon_a.owner)
    today = timezone.now().date()

    with as_tenant(salon_a.tenant):
        Transaction.objects.create(
            tenant=salon_a.tenant,
            kind=Transaction.Kind.INCOME,
            amount=Decimal("500"),
            occurred_on=today.replace(day=1),
            label="Prestation",
        )

    mois = read(api_client, salon_a).data["month"]

    assert mois["income"] == "500.00"
    assert mois["growth"] is None


@pytest.mark.django_db
def test_the_average_basket_is_absent_when_nothing_was_booked(api_client, salon_a):
    """Zéro rendez-vous ne vaut pas un panier de zéro."""
    login(api_client, salon_a.owner)

    compteurs = read(api_client, salon_a).data["counters"]

    assert compteurs["bookings"] == 0
    assert compteurs["average_basket"] is None


@pytest.mark.django_db
def test_the_ranking_ignores_what_was_booked_then_dropped(api_client, salon_a):
    """Une prestation qu'on annule n'est pas une prestation qui marche.

    La faire remonter dans le classement mettrait en avant exactement ce
    qui déçoit — et le salon en commanderait davantage de fournitures.
    """
    login(api_client, salon_a.owner)
    now = timezone.now()

    for _ in range(3):
        booking_at(
            salon_a,
            now - timedelta(days=2),
            status=Booking.Status.CANCELLED,
            service_name="Défrisage",
        )
    booking_at(
        salon_a,
        now - timedelta(days=1),
        status=Booking.Status.COMPLETED,
        service_name="Box braids",
    )

    classement = read(api_client, salon_a).data["top_services"]

    assert [row["name"] for row in classement] == ["Box braids"]


@pytest.mark.django_db
def test_every_rating_appears_even_the_empty_ones(api_client, salon_a):
    """Une barre absente se lit comme une absence de donnée.

    Ne pas afficher la note 1 parce que personne ne l'a mise laisserait
    croire qu'on la cache. Elle figure, à zéro.
    """
    login(api_client, salon_a.owner)
    booking = booking_at(
        salon_a, timezone.now() - timedelta(days=2), status=Booking.Status.COMPLETED
    )

    with as_tenant(salon_a.tenant):
        Review.objects.create(
            tenant=salon_a.tenant,
            booking=booking,
            customer=salon_a.customer,
            rating=5,
            author_name="Awa",
            status=Review.Status.PUBLISHED,
        )

    notes = read(api_client, salon_a).data["ratings"]

    assert [row["rating"] for row in notes] == [5, 4, 3, 2, 1]
    assert [row["count"] for row in notes] == [1, 0, 0, 0, 0]
    assert read(api_client, salon_a).data["counters"]["rating"] == 5.0


@pytest.mark.django_db
def test_the_feed_is_ordered_by_what_happened_last(api_client, salon_a):
    login(api_client, salon_a.owner)
    now = timezone.now()

    booking_at(salon_a, now + timedelta(days=1), status=Booking.Status.CONFIRMED)
    booking_at(salon_a, now + timedelta(days=2), status=Booking.Status.CONFIRMED)

    fil = read(api_client, salon_a).data["feed"]

    assert fil, "le fil d'activité est vide"
    dates = [entry["at"] for entry in fil]
    assert dates == sorted(dates, reverse=True)


@pytest.mark.django_db
def test_the_overview_never_leaks_another_salon(api_client, salon_a, salon_b):
    """La garantie d'isolation, vue depuis les chiffres agrégés.

    Une somme est le pire endroit où une fuite passe inaperçue : elle ne
    montre aucun nom, juste un total un peu trop gros que personne ne
    vérifie.
    """
    login(api_client, salon_a.owner)
    now = timezone.now()

    booking_at(salon_a, now + timedelta(hours=2), status=Booking.Status.CONFIRMED)
    booking_at(salon_b, now + timedelta(hours=3), status=Booking.Status.CONFIRMED)

    response = read(api_client, salon_a)

    assert response.data["today"]["count"] == 1
    assert response.data["today"]["revenue"] == "200.00"


@pytest.mark.django_db
def test_occupancy_is_absent_when_no_hours_are_declared(api_client, salon_a):
    """Diviser par zéro donnerait un taux, pas une absence de réponse."""
    from apps.scheduling.models import BusinessHours

    login(api_client, salon_a.owner)
    with as_tenant(salon_a.tenant):
        BusinessHours.objects.all().delete()

    assert read(api_client, salon_a).data["occupancy"] is None


@pytest.mark.django_db
def test_occupancy_reflects_the_hours_actually_filled(api_client, salon_a):
    """Le chiffre qui manquait : « est-ce que je travaille assez ».

    Le nombre de rendez-vous n'y répond pas — dix poses d'une heure et deux
    poses de quatre heures ne remplissent pas la même semaine.
    """
    login(api_client, salon_a.owner)
    now = timezone.now()

    booking_at(salon_a, now - timedelta(days=1), status=Booking.Status.CONFIRMED)

    taux = read(api_client, salon_a).data["occupancy"]

    assert taux is not None
    assert 0 < taux <= 100
