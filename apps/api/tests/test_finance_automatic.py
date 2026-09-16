"""Ce qui s'enregistre tout seul dans les comptes.

Le risque de cette fonctionnalite n'est pas qu'elle oublie une ligne : c'est
qu'elle en ecrive deux pour le meme argent. Une cliente qui verse 150
d'acompte sur une prestation a 450 doit produire 450 au total, pas 600 - un
salon qui se croit plus riche qu'il ne l'est prend de mauvaises decisions.

La majorite de ces tests verifie donc une soustraction.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.models import Membership
from apps.billing.models import Invoice, Plan, Subscription
from apps.billing.services import mark_invoice_paid
from apps.finance.models import Transaction
from apps.platformledger.models import PlatformEntry
from apps.scheduling.models import Booking
from conftest import as_tenant, salon_host
from tests.factories import MembershipFactory, UserFactory

PASSWORD = "motdepasse-solide"
HOST = {"Host": salon_host("blondrose")}


def login(client, user):
    assert client.login(email=user.email, password=PASSWORD)
    return client


def make_booking(salon, *, total="450", deposit="150"):
    starts_at = timezone.now() + timedelta(days=3)
    with as_tenant(salon.tenant):
        return Booking.objects.create(
            tenant=salon.tenant,
            customer=salon.customer,
            staff_member=salon.staff,
            service=salon.service,
            starts_at=starts_at,
            ends_at=starts_at + timedelta(hours=2),
            status=Booking.Status.CONFIRMED,
            service_name="Box braids",
            total_amount=Decimal(total),
            deposit_amount=Decimal(deposit),
        )


def income_for(salon, booking) -> Decimal:
    with as_tenant(salon.tenant):
        return sum(
            (
                row.amount
                for row in Transaction.objects.filter(
                    booking=booking, kind=Transaction.Kind.INCOME
                )
            ),
            Decimal("0"),
        )


# ---------------------------------------------------------------------------
# Acompte
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_taking_a_deposit_records_the_income_the_same_day(api_client, salon_a):
    """L'acompte appartient au mois du versement, pas a celui de la pose."""
    booking = make_booking(salon_a)
    login(api_client, salon_a.owner)

    response = api_client.post(
        f"/api/v1/bookings/{booking.id}/deposit/",
        {"method": "cash", "amount": "150"},
        format="json",
    )

    assert response.status_code == 200, response.data
    with as_tenant(salon_a.tenant):
        line = Transaction.objects.get(
            booking=booking, source=Transaction.Source.BOOKING_DEPOSIT
        )
    assert line.amount == Decimal("150")
    assert line.kind == Transaction.Kind.INCOME
    assert line.occurred_on == timezone.now().date()


@pytest.mark.django_db
def test_a_partial_deposit_records_what_was_actually_received(api_client, salon_a):
    """Une cliente laisse parfois ce qu'elle a sur elle."""
    booking = make_booking(salon_a, deposit="150")
    login(api_client, salon_a.owner)

    api_client.post(
        f"/api/v1/bookings/{booking.id}/deposit/",
        {"method": "cash", "amount": "80"},
        format="json",
    )

    assert income_for(salon_a, booking) == Decimal("80")


@pytest.mark.django_db
def test_cancelling_a_deposit_removes_its_income(api_client, salon_a):
    """Sinon la correction serait cosmetique : la caisse resterait fausse."""
    booking = make_booking(salon_a)
    login(api_client, salon_a.owner)

    api_client.post(
        f"/api/v1/bookings/{booking.id}/deposit/",
        {"method": "cash", "amount": "150"},
        format="json",
    )
    assert income_for(salon_a, booking) == Decimal("150")

    response = api_client.post(f"/api/v1/bookings/{booking.id}/deposit/cancel/")

    assert response.status_code == 200
    assert income_for(salon_a, booking) == Decimal("0")


# ---------------------------------------------------------------------------
# Le point central : jamais deux fois le meme argent
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_deposit_then_the_service_totals_the_price_not_more(api_client, salon_a):
    """Le test qui compte.

    150 d'acompte puis une prestation a 450 doivent faire 450, pas 600.
    """
    booking = make_booking(salon_a, total="450", deposit="150")
    login(api_client, salon_a.owner)

    api_client.post(
        f"/api/v1/bookings/{booking.id}/deposit/",
        {"method": "cash", "amount": "150"},
        format="json",
    )
    api_client.post(
        f"/api/v1/bookings/{booking.id}/status/",
        {"status": Booking.Status.COMPLETED},
        format="json",
    )

    assert income_for(salon_a, booking) == Decimal("450")

    with as_tenant(salon_a.tenant):
        # `list()` force l'evaluation *dans* le contexte : un queryset
        # paresseux parcouru apres la sortie du bloc interroge la base sans
        # tenant, et RLS renvoie vide - a juste titre.
        amounts = list(
            Transaction.objects.filter(booking=booking)
            .order_by("amount")
            .values_list("amount", flat=True)
        )

    # Deux lignes : l'acompte, puis le solde. Le salon doit pouvoir lire les
    # deux versements separement.
    assert amounts == [Decimal("150"), Decimal("300")]


@pytest.mark.django_db
def test_a_service_without_deposit_records_its_full_price(api_client, salon_a):
    booking = make_booking(salon_a, total="450", deposit="0")
    login(api_client, salon_a.owner)

    api_client.post(
        f"/api/v1/bookings/{booking.id}/status/",
        {"status": Booking.Status.COMPLETED},
        format="json",
    )

    assert income_for(salon_a, booking) == Decimal("450")


@pytest.mark.django_db
def test_a_service_paid_entirely_in_advance_adds_no_second_line(api_client, salon_a):
    """Rien a constater : une ligne a zero n'apprendrait rien."""
    booking = make_booking(salon_a, total="450", deposit="450")
    login(api_client, salon_a.owner)

    api_client.post(
        f"/api/v1/bookings/{booking.id}/deposit/",
        {"method": "cash", "amount": "450"},
        format="json",
    )
    api_client.post(
        f"/api/v1/bookings/{booking.id}/status/",
        {"status": Booking.Status.COMPLETED},
        format="json",
    )

    assert income_for(salon_a, booking) == Decimal("450")
    with as_tenant(salon_a.tenant):
        assert Transaction.objects.filter(booking=booking).count() == 1


@pytest.mark.django_db
def test_marking_completed_again_never_doubles_the_income(api_client, salon_a):
    booking = make_booking(salon_a, total="450", deposit="150")
    login(api_client, salon_a.owner)

    api_client.post(
        f"/api/v1/bookings/{booking.id}/deposit/",
        {"method": "cash", "amount": "150"},
        format="json",
    )
    for _ in range(4):
        api_client.post(
            f"/api/v1/bookings/{booking.id}/status/",
            {"status": Booking.Status.COMPLETED},
            format="json",
        )

    assert income_for(salon_a, booking) == Decimal("450")


# ---------------------------------------------------------------------------
# Abonnement : les deux cotes du registre
# ---------------------------------------------------------------------------


def make_invoice(salon, amount="25000"):
    plan, _ = Plan.objects.get_or_create(
        code=Plan.Code.values[0], defaults={"name": "Essentiel"}
    )
    with as_tenant(salon.tenant):
        subscription = Subscription.objects.create(
            tenant=salon.tenant,
            plan=plan,
            status=Subscription.Status.ACTIVE,
            current_period_start=timezone.now() - timedelta(days=30),
            current_period_end=timezone.now(),
        )
        return Invoice.objects.create(
            tenant=salon.tenant,
            subscription=subscription,
            number=f"F-{salon.tenant.slug}-001",
            period_start=timezone.now() - timedelta(days=30),
            period_end=timezone.now(),
            amount=Decimal(amount),
            currency=salon.tenant.currency,
            due_at=timezone.now() + timedelta(days=7),
        )


@pytest.mark.django_db
def test_paying_the_subscription_charges_the_salon_and_credits_the_platform(salon_a):
    """Le meme versement, vu des deux cotes du registre.

    C'est une depense pour le salon et une recette pour la plateforme. Les
    deux lignes sont ecrites par le meme evenement, donc elles ne peuvent
    pas diverger.
    """
    invoice = make_invoice(salon_a, amount="25000")

    with as_tenant(salon_a.tenant):
        mark_invoice_paid(invoice, method="transfer", reference="VIR-42")

        charged = Transaction.objects.get(invoice=invoice)

    assert charged.kind == Transaction.Kind.EXPENSE
    assert charged.amount == Decimal("25000")
    assert charged.source == Transaction.Source.SUBSCRIPTION

    earned = PlatformEntry.objects.get(invoice=invoice)
    assert earned.kind == PlatformEntry.Kind.INCOME
    assert earned.amount == Decimal("25000")
    assert earned.tenant_id == salon_a.tenant.id


@pytest.mark.django_db
def test_the_salon_sees_the_subscription_among_its_expenses(api_client, salon_a):
    invoice = make_invoice(salon_a, amount="25000")
    with as_tenant(salon_a.tenant):
        mark_invoice_paid(invoice, method="transfer")

    login(api_client, salon_a.owner)
    response = api_client.get("/api/v1/transactions/summary/")

    assert Decimal(response.data["totals"]["expense"]) >= Decimal("25000")


@pytest.mark.django_db
def test_an_invoice_is_never_counted_twice_on_either_side(salon_a):
    invoice = make_invoice(salon_a, amount="25000")

    with as_tenant(salon_a.tenant):
        mark_invoice_paid(invoice, method="transfer")
        # Un second marquage leve une erreur metier ; les services de
        # comptabilite, eux, doivent rester idempotents si on les rappelle.
        from apps.finance.services import record_subscription_expense

        record_subscription_expense(invoice)
        record_subscription_expense(invoice)
        assert Transaction.objects.filter(invoice=invoice).count() == 1

    from apps.platformledger.services import record_subscription_income

    record_subscription_income(invoice)
    assert PlatformEntry.objects.filter(invoice=invoice).count() == 1


@pytest.mark.django_db
def test_the_platform_ledger_is_not_reachable_by_a_salon(api_client, salon_a):
    """Les comptes de la plateforme ne sont pas une ressource de l'API salon."""
    make_invoice(salon_a)
    login(api_client, salon_a.owner)

    for route in ("/api/v1/platform-entries/", "/api/v1/platformledger/"):
        assert api_client.get(route).status_code == 404


@pytest.mark.django_db
def test_automatic_lines_are_flagged_as_such(api_client, salon_a):
    """Une ligne que le salon n'a pas saisie doit se signaler.

    Sans cela, il cherche qui l'a ecrite — ou pire, la supprime en croyant a
    une erreur.
    """
    booking = make_booking(salon_a)
    login(api_client, salon_a.owner)
    api_client.post(
        f"/api/v1/bookings/{booking.id}/deposit/",
        {"method": "cash", "amount": "150"},
        format="json",
    )

    response = api_client.get("/api/v1/transactions/")
    row = next(
        item for item in response.data["results"] if item["source"] != "manual"
    )

    assert row["from_booking"] is True
    assert row["source_label"] == "Acompte encaissé"


@pytest.mark.django_db
def test_the_team_still_cannot_read_the_accounts_after_automation(api_client, salon_a):
    member = UserFactory()
    MembershipFactory(
        tenant=salon_a.tenant, user=member, role=Membership.Role.RECEPTIONIST
    )
    login(api_client, member)

    assert api_client.get("/api/v1/transactions/").status_code == 403
