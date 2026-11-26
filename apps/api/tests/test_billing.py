"""Abonnements, factures et acomptes.

Aucune passerelle de paiement n'est branchee : ces tests portent donc sur ce
qui est reellement implemente — le suivi de ce qui est du, l'avancement des
periodes, et la constatation des reglements.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.models import Membership
from apps.billing.models import Invoice, Plan, Subscription, SubscriptionEvent
from apps.billing.services import (
    BillingError,
    issue_invoice,
    mark_invoice_paid,
    next_invoice_number,
    run_billing_cycle,
    start_trial,
)
from apps.scheduling.models import Booking
from conftest import as_tenant
from tests.factories import BookingFactory, MembershipFactory, UserFactory

PASSWORD = "motdepasse-solide"

pytestmark = pytest.mark.django_db


@pytest.fixture
def plans(db):
    # L'essai, le mensuel et l'annuel existent deja : la migration 0007 de
    # `billing` les cree, dans la base de test comme ailleurs.
    Plan.objects.get_or_create(code=Plan.Code.TRIAL, defaults={"name": "Essai"})
    plan, _ = Plan.objects.get_or_create(
        code=Plan.Code.MONTHLY,
        defaults={"name": "Mensuel", "reference_price": Decimal("12000")},
    )
    return plan


@pytest.fixture
def subscription(salon_a, plans):
    now = timezone.now()
    with as_tenant(salon_a.tenant):
        return Subscription.objects.create(
            tenant=salon_a.tenant,
            plan=plans,
            status=Subscription.Status.ACTIVE,
            price_amount=Decimal("12000"),
            currency="XAF",
            current_period_start=now - timedelta(days=30),
            current_period_end=now - timedelta(minutes=1),
        )


# ---------------------------------------------------------------------------
# Numerotation
# ---------------------------------------------------------------------------


def test_invoice_numbers_never_collide_across_salons(salon_a, salon_b, plans):
    """Le compteur est global : c'est la plateforme qui vend, pas le salon.

    Le calculer en comptant les lignes echouerait — les politiques RLS
    masquent les factures des autres salons.
    """
    numbers = set()
    for salon in (salon_a, salon_b):
        with as_tenant(salon.tenant):
            sub = Subscription.objects.create(
                tenant=salon.tenant,
                plan=plans,
                price_amount=Decimal("10000"),
                currency=salon.tenant.currency,
                current_period_end=timezone.now(),
            )
            numbers.add(issue_invoice(sub).number)
            numbers.add(issue_invoice(sub).number)

    assert len(numbers) == 4


def test_numbers_are_sequential():
    first = next_invoice_number()
    second = next_invoice_number()

    assert int(second[1:]) == int(first[1:]) + 1


# ---------------------------------------------------------------------------
# Periode d'essai
# ---------------------------------------------------------------------------


def test_a_trial_opens_at_signup(salon_a, plans):
    subscription = start_trial(salon_a.tenant)

    assert subscription.status == Subscription.Status.TRIALING
    assert subscription.price_amount == 0
    assert subscription.currency == salon_a.tenant.currency
    # Deux semaines : la duree decidee avec le produit.
    assert 13 <= (subscription.days_left_in_trial or 0) <= 14


def test_starting_a_trial_twice_returns_the_same_subscription(salon_a, plans):
    first = start_trial(salon_a.tenant)
    second = start_trial(salon_a.tenant)

    assert first.pk == second.pk
    with as_tenant(salon_a.tenant):
        assert Subscription.objects.count() == 1


def test_a_trial_without_configured_plan_is_refused(salon_a):
    Plan.objects.filter(code=Plan.Code.TRIAL).update(active=False)
    with pytest.raises(BillingError):
        start_trial(salon_a.tenant)


# ---------------------------------------------------------------------------
# Emission et reglement
# ---------------------------------------------------------------------------


def test_issuing_an_invoice_advances_the_period(salon_a, subscription):
    with as_tenant(salon_a.tenant):
        previous_end = subscription.current_period_end
        invoice = issue_invoice(subscription)

        assert invoice.amount == Decimal("12000")
        assert invoice.status == Invoice.Status.ISSUED
        assert invoice.due_at > invoice.issued_at

        subscription.refresh_from_db()
        # La periode facturee se ferme, la suivante s'ouvre juste apres.
        assert subscription.current_period_start == previous_end
        assert subscription.current_period_end > previous_end


def test_marking_an_invoice_paid_records_how(salon_a, subscription):
    with as_tenant(salon_a.tenant):
        invoice = issue_invoice(subscription)
        mark_invoice_paid(invoice, method=Invoice.Method.MOBILE_MONEY, reference="MM-42")

        invoice.refresh_from_db()
        assert invoice.status == Invoice.Status.PAID
        assert invoice.paid_at is not None
        assert invoice.payment_method == Invoice.Method.MOBILE_MONEY
        assert invoice.payment_reference == "MM-42"


def test_an_invoice_cannot_be_paid_twice(salon_a, subscription):
    with as_tenant(salon_a.tenant):
        invoice = issue_invoice(subscription)
        mark_invoice_paid(invoice, method=Invoice.Method.CASH)

        with pytest.raises(BillingError):
            mark_invoice_paid(invoice, method=Invoice.Method.CASH)


def test_paying_reactivates_a_suspended_subscription(salon_a, subscription):
    with as_tenant(salon_a.tenant):
        invoice = issue_invoice(subscription)
        subscription.status = Subscription.Status.PAST_DUE
        subscription.save()

        mark_invoice_paid(invoice, method=Invoice.Method.CASH)

        subscription.refresh_from_db()
        assert subscription.status == Subscription.Status.ACTIVE


# ---------------------------------------------------------------------------
# Cycle automatique
# ---------------------------------------------------------------------------


def test_the_cycle_expires_an_elapsed_paid_period_without_billing(salon_a, subscription):
    """Plus de facture emise d'office : une periode payee ne s'ouvre que par
    un paiement approuve. Une periode echue expire, c'est tout."""
    run_billing_cycle()

    with as_tenant(salon_a.tenant):
        subscription.refresh_from_db()
        assert subscription.status == Subscription.Status.EXPIRED
        assert Invoice.objects.count() == 0


def test_running_the_cycle_twice_does_not_expire_twice(salon_a, subscription):
    """La tache tourne tous les jours : elle doit etre rejouable."""
    run_billing_cycle()
    run_billing_cycle()

    with as_tenant(salon_a.tenant):
        assert (
            SubscriptionEvent.objects.filter(kind=SubscriptionEvent.Kind.EXPIRED).count() == 1
        )


def test_a_finished_trial_expires_instead_of_becoming_free(salon_a, plans):
    """Autrefois, un essai termine basculait en « actif » a prix nul : aucun
    salon n'a jamais paye. Il expire desormais."""
    subscription = start_trial(salon_a.tenant)
    with as_tenant(salon_a.tenant):
        subscription.trial_ends_at = timezone.now() - timedelta(days=1)
        subscription.current_period_end = timezone.now() - timedelta(days=1)
        subscription.save()

    run_billing_cycle()

    with as_tenant(salon_a.tenant):
        subscription.refresh_from_db()
        assert subscription.status == Subscription.Status.EXPIRED
        assert Invoice.objects.count() == 0


def test_the_cycle_gives_a_trial_to_a_salon_without_subscription(salon_a, plans):
    """Un salon sans abonnement echapperait aux regles d'acces : la tache
    quotidienne lui ouvre un essai."""
    run_billing_cycle()

    with as_tenant(salon_a.tenant):
        subscription = Subscription.objects.get()
        assert subscription.status == Subscription.Status.TRIALING


# ---------------------------------------------------------------------------
# Isolation
# ---------------------------------------------------------------------------


def test_a_salon_only_sees_its_own_invoices(api_client, salon_a, salon_b, plans):
    for salon in (salon_a, salon_b):
        with as_tenant(salon.tenant):
            sub = Subscription.objects.create(
                tenant=salon.tenant,
                plan=plans,
                price_amount=Decimal("10000"),
                currency=salon.tenant.currency,
                current_period_end=timezone.now(),
            )
            issue_invoice(sub)

    assert api_client.login(email=salon_a.owner.email, password=PASSWORD)
    response = api_client.get("/api/v1/invoices/")

    assert response.status_code == 200
    assert len(response.data) == 1


def test_only_the_owner_sees_the_subscription(api_client, salon_a, subscription):
    """Le document est explicite : la facturation ne regarde pas l'équipe."""
    receptionniste = UserFactory()
    MembershipFactory(
        tenant=salon_a.tenant,
        user=receptionniste,
        role=Membership.Role.RECEPTIONIST,
    )

    assert api_client.login(email=receptionniste.email, password=PASSWORD)
    refuse = api_client.get("/api/v1/subscription")

    api_client.logout()
    assert api_client.login(email=salon_a.owner.email, password=PASSWORD)
    autorise = api_client.get("/api/v1/subscription")

    assert refuse.status_code == 403
    assert autorise.status_code == 200
    assert autorise.data["plan"]["code"] == "monthly"


# ---------------------------------------------------------------------------
# Acomptes
# ---------------------------------------------------------------------------


def make_booking_with_deposit(salon, deposit="10000"):
    starts_at = timezone.now() + timedelta(days=6)
    with as_tenant(salon.tenant):
        return BookingFactory(
            tenant=salon.tenant,
            customer=salon.customer,
            staff_member=salon.staff,
            service=salon.service,
            starts_at=starts_at,
            ends_at=starts_at + timedelta(minutes=120),
            deposit_amount=Decimal(deposit),
        )


def test_the_salon_records_a_deposit_received_offline(api_client, salon_a):
    booking = make_booking_with_deposit(salon_a)
    assert api_client.login(email=salon_a.owner.email, password=PASSWORD)

    response = api_client.post(
        f"/api/v1/bookings/{booking.id}/deposit/",
        {"method": "mobile_money"},
        format="json",
    )

    assert response.status_code == 200
    with as_tenant(salon_a.tenant):
        booking.refresh_from_db()
        assert booking.deposit_paid is True
        assert booking.deposit_paid_at is not None
        assert booking.deposit_method == "mobile_money"


def test_a_deposit_cannot_be_recorded_twice(api_client, salon_a):
    booking = make_booking_with_deposit(salon_a)
    assert api_client.login(email=salon_a.owner.email, password=PASSWORD)

    body = {"method": "cash"}
    first = api_client.post(f"/api/v1/bookings/{booking.id}/deposit/", body, format="json")
    second = api_client.post(f"/api/v1/bookings/{booking.id}/deposit/", body, format="json")

    assert first.status_code == 200
    assert second.status_code == 400
    assert second.json()["code"] == "already_paid"


def test_a_booking_without_deposit_refuses_the_action(api_client, salon_a):
    booking = make_booking_with_deposit(salon_a, deposit="0")
    assert api_client.login(email=salon_a.owner.email, password=PASSWORD)

    response = api_client.post(
        f"/api/v1/bookings/{booking.id}/deposit/", {"method": "cash"}, format="json"
    )

    assert response.status_code == 400
    assert response.json()["code"] == "no_deposit"


def test_an_unknown_payment_method_is_refused(api_client, salon_a):
    booking = make_booking_with_deposit(salon_a)
    assert api_client.login(email=salon_a.owner.email, password=PASSWORD)

    response = api_client.post(
        f"/api/v1/bookings/{booking.id}/deposit/",
        {"method": "bitcoin"},
        format="json",
    )

    assert response.status_code == 400
    with as_tenant(salon_a.tenant):
        booking.refresh_from_db()
        assert booking.deposit_paid is False


def test_a_deposit_cannot_be_recorded_on_another_salons_booking(
    api_client, salon_a, salon_b
):
    foreign = make_booking_with_deposit(salon_b)
    assert api_client.login(email=salon_a.owner.email, password=PASSWORD)

    response = api_client.post(
        f"/api/v1/bookings/{foreign.id}/deposit/", {"method": "cash"}, format="json"
    )

    assert response.status_code == 404
    with as_tenant(salon_b.tenant):
        foreign.refresh_from_db()
        assert foreign.deposit_paid is False


def test_the_deposit_appears_in_the_agenda(api_client, salon_a):
    booking = make_booking_with_deposit(salon_a)
    assert api_client.login(email=salon_a.owner.email, password=PASSWORD)
    api_client.post(
        f"/api/v1/bookings/{booking.id}/deposit/", {"method": "cash"}, format="json"
    )

    listing = api_client.get("/api/v1/bookings/")
    row = next(r for r in listing.data["results"] if r["id"] == str(booking.id))

    assert row["deposit_paid"] is True
    assert row["deposit_method"] == "cash"
    assert Booking.Status(row["status"])
