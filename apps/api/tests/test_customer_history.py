"""Compteurs et historique d'une fiche cliente.

Ces chiffres decident de gestes reels : relancer une habituee, demander un
acompte a quelqu'un qui a deja fait faux bond. Ils doivent compter ce qu'ils
disent compter, et rien d'autre.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.models import Membership
from apps.scheduling.models import Booking
from conftest import as_tenant
from tests.factories import MembershipFactory, UserFactory

PASSWORD = "motdepasse-solide"


def login(client, user):
    assert client.login(email=user.email, password=PASSWORD)
    return client


def make_booking(salon, status, days_ago=1, service_name="Box braids"):
    starts_at = timezone.now() - timedelta(days=days_ago)
    with as_tenant(salon.tenant):
        return Booking.objects.create(
            tenant=salon.tenant,
            customer=salon.customer,
            staff_member=salon.staff,
            service=salon.service,
            starts_at=starts_at,
            ends_at=starts_at + timedelta(hours=1),
            status=status,
            service_name=service_name,
            total_amount=Decimal("450"),
        )


@pytest.mark.django_db
def test_the_counters_separate_honoured_missed_and_cancelled(api_client, salon_a):
    make_booking(salon_a, Booking.Status.COMPLETED, days_ago=30)
    make_booking(salon_a, Booking.Status.COMPLETED, days_ago=20)
    make_booking(salon_a, Booking.Status.NO_SHOW, days_ago=10)
    make_booking(salon_a, Booking.Status.CANCELLED, days_ago=5)

    login(api_client, salon_a.owner)
    response = api_client.get("/api/v1/customers/")

    assert response.status_code == 200
    row = next(
        item for item in response.data["results"] if item["id"] == str(salon_a.customer.id)
    )
    assert row["visit_count"] == 2, "seuls les rendez-vous honores comptent comme visites"
    assert row["no_show_count"] == 1
    assert row["cancelled_count"] == 1
    # Le total les englobe tous : c'est le nombre de fois qu'on a eu affaire
    # a cette cliente, pas le nombre de fois qu'elle est venue.
    assert row["booking_count"] >= 4


@pytest.mark.django_db
def test_the_recurring_filter_keeps_only_those_who_came_back(api_client, salon_a):
    """Une cliente venue une fois n'est pas une habituee."""
    from apps.customers.models import Customer

    with as_tenant(salon_a.tenant):
        one_off = Customer.objects.create(
            tenant=salon_a.tenant, full_name="Passage Unique", phone="+242000000001"
        )
    make_booking(salon_a, Booking.Status.COMPLETED, days_ago=30)
    make_booking(salon_a, Booking.Status.COMPLETED, days_ago=20)

    starts_at = timezone.now() - timedelta(days=15)
    with as_tenant(salon_a.tenant):
        Booking.objects.create(
            tenant=salon_a.tenant,
            customer=one_off,
            staff_member=salon_a.staff,
            service=salon_a.service,
            starts_at=starts_at,
            ends_at=starts_at + timedelta(hours=1),
            status=Booking.Status.COMPLETED,
            service_name="Box braids",
            total_amount=Decimal("450"),
        )

    login(api_client, salon_a.owner)
    response = api_client.get("/api/v1/customers/?recurring=true")

    assert response.status_code == 200
    names = {row["full_name"] for row in response.data["results"]}
    assert salon_a.customer.full_name in names
    assert "Passage Unique" not in names


@pytest.mark.django_db
def test_the_history_returns_the_most_recent_first(api_client, salon_a):
    make_booking(salon_a, Booking.Status.COMPLETED, days_ago=40, service_name="Ancienne")
    make_booking(salon_a, Booking.Status.COMPLETED, days_ago=2, service_name="Recente")

    login(api_client, salon_a.owner)
    response = api_client.get(f"/api/v1/customers/{salon_a.customer.id}/history/")

    assert response.status_code == 200
    assert response.data[0]["service_name"] == "Recente"
    assert response.data[0]["staff_member_name"] == salon_a.staff.name


@pytest.mark.django_db
def test_the_history_of_another_salons_customer_is_not_reachable(
    api_client, salon_a, salon_b
):
    """Le risque le plus grave du produit : voir les clientes d'un autre salon."""
    login(api_client, salon_a.owner)

    response = api_client.get(f"/api/v1/customers/{salon_b.customer.id}/history/")

    assert response.status_code == 404


@pytest.mark.django_db
def test_a_stylist_may_read_the_history_but_not_the_private_notes(api_client, salon_a):
    """Le prestataire a besoin de savoir ce qu'il a deja fait sur ce cheveu.
    Il n'a pas a lire les notes sensibles pour autant."""
    make_booking(salon_a, Booking.Status.COMPLETED, days_ago=3)

    stylist = UserFactory()
    MembershipFactory(
        tenant=salon_a.tenant, user=stylist, role=Membership.Role.STAFF
    )
    login(api_client, stylist)

    history = api_client.get(f"/api/v1/customers/{salon_a.customer.id}/history/")
    listing = api_client.get("/api/v1/customers/")

    assert history.status_code == 200
    assert len(history.data) >= 1
    assert all("private_notes" not in row for row in listing.data["results"])
