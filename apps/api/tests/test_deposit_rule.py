"""La regle de calcul de l'acompte.

Elle touche a l'argent des deux cotes : trop bas, le salon n'est pas protege ;
trop haut, la cliente avance de l'argent qu'elle ne doit pas. La plupart de
ces tests verifient donc une borne, pas un montant.
"""

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from apps.salons.models import SalonProfile
from apps.scheduling.models import Booking
from apps.scheduling.services.deposit import compute_deposit
from conftest import as_tenant, salon_host

BRAZZAVILLE = ZoneInfo("Africa/Brazzaville")
HOST = {"Host": salon_host("blondrose")}


def euros(value: str) -> Decimal:
    return Decimal(value)


# ---------------------------------------------------------------------------
# La regle elle-meme
# ---------------------------------------------------------------------------


def test_without_a_rate_the_fixed_amount_still_applies():
    """Les salons qui n'ont rien reglé gardent leur comportement."""
    assert compute_deposit(
        service_amount=euros("450"), requires_deposit=True, minimum=euros("150"), rate=0
    ) == euros("150")


def test_nothing_asked_stays_nothing_asked():
    """Un taux ne doit pas faire apparaitre une demande que personne n'a
    formulee sur une prestation sans acompte."""
    assert compute_deposit(
        service_amount=euros("450"), requires_deposit=False, rate=30
    ) == euros("0")


def test_the_rate_applies_to_the_service_and_its_options():
    """Le temps se reserve a un pourcentage : un creneau libere se revend."""
    assert compute_deposit(
        service_amount=euros("450"),
        options_amount=euros("80"),
        requires_deposit=True, minimum=euros("150"),
        rate=30,
    ) == euros("159")  # 30 % de 530


def test_the_fixed_amount_is_a_floor_never_a_ceiling():
    """« Au moins 100, quoi qu'il arrive » doit rester possible."""
    assert compute_deposit(
        service_amount=euros("100"), requires_deposit=True, minimum=euros("80"), rate=10
    ) == euros("80")  # 10 % = 10, le plancher l'emporte


def test_supplies_are_paid_in_full():
    """Le salon a deja achete les meches ; elles ne se revendent pas
    toujours."""
    assert compute_deposit(
        service_amount=euros("450"),
        items_amount=euros("240"),
        requires_deposit=True, minimum=euros("150"),
        rate=30,
    ) == euros("390")  # 30 % × 450 = 135, sous le plancher 150 → 150 + 240


def test_a_salon_can_choose_not_to_charge_supplies_upfront():
    assert compute_deposit(
        service_amount=euros("450"),
        items_amount=euros("240"),
        requires_deposit=True, minimum=euros("150"),
        rate=30,
        covers_items=False,
    ) == euros("150")


def test_travel_never_enters_the_deposit():
    """Le trajet n'a pas eu lieu : le facturer d'avance se retournerait
    contre le salon au premier litige."""
    assert compute_deposit(
        service_amount=euros("450"),
        travel_amount=euros("75"),
        requires_deposit=True, minimum=euros("150"),
        rate=30,
    ) == euros("150")


# ---------------------------------------------------------------------------
# Ce qui protege la cliente
# ---------------------------------------------------------------------------


def test_the_deposit_never_exceeds_what_is_owed():
    """Un acompte superieur au total serait une avance, pas un acompte."""
    due = compute_deposit(
        service_amount=euros("100"),
        items_amount=euros("50"),
        requires_deposit=True, minimum=euros("500"),
        rate=100,
    )
    assert due == euros("150")


def test_even_at_one_hundred_percent_travel_stays_out():
    """A 100 %, l'acompte couvre tout sauf le trajet - qui n'a pas eu lieu."""
    due = compute_deposit(
        service_amount=euros("450"),
        options_amount=euros("80"),
        items_amount=euros("240"),
        travel_amount=euros("75"),
        requires_deposit=True, minimum=euros("1"),
        rate=100,
    )
    assert due == euros("770")  # 450 + 80 + 240, sans les 75 de trajet


@pytest.mark.parametrize("currency", ["XAF", "XOF", "CDF"])
def test_currencies_without_cents_are_rounded_down(currency):
    """Un acompte a 137,40 XAF ne se paie pas : la piece n'existe pas.

    Et l'arrondi va vers le bas : vers le haut ferait payer plus que la
    regle annoncee.
    """
    due = compute_deposit(
        service_amount=euros("458"),
        requires_deposit=True, minimum=euros("1"),
        rate=30,
        currency=currency,
    )
    assert due == euros("137")  # 137,40 tronque


def test_currencies_with_cents_keep_them():
    due = compute_deposit(
        service_amount=euros("458"),
        requires_deposit=True, minimum=euros("1"),
        rate=30,
        currency="CNY",
    )
    assert due == euros("137.40")


# ---------------------------------------------------------------------------
# Bout en bout, depuis une vraie reservation
# ---------------------------------------------------------------------------


def next_monday_at(hour: int) -> datetime:
    today = datetime.now(BRAZZAVILLE).date()
    ahead = (0 - today.weekday()) % 7 or 7
    day: date = today + timedelta(days=ahead + 7)
    return datetime.combine(day, time(hour, 0), tzinfo=BRAZZAVILLE)


@pytest.mark.django_db
def test_the_deposit_follows_the_basket_end_to_end(api_client, salon_a):
    """Le defaut d'origine : 150 sur 450 puis 150 sur 690.

    Avec la regle, l'acompte suit ce qui est reellement engage.
    """
    from apps.catalog.models import ServiceOption

    with as_tenant(salon_a.tenant):
        salon_a.service.price_amount = Decimal("450")
        salon_a.service.requires_deposit = True
        salon_a.service.save()
        SalonProfile.objects.filter(tenant=salon_a.tenant).update(
            deposit_rate=30, deposit_minimum=Decimal("150")
        )

        option = ServiceOption.objects.create(
            tenant=salon_a.tenant,
            service=salon_a.service,
            name="Longueur XL",
            price_delta=Decimal("80"),
        )

    response = api_client.post(
        "/api/v1/public/bookings",
        {
            "service": str(salon_a.service.id),
            "starts_at": next_monday_at(10).isoformat(),
            "full_name": "Awa Diallo",
            "phone": "+242066112233",
            "accepts_policy": True,
            "options": [str(option.id)],
        },
        format="json",
        headers=HOST,
    )

    assert response.status_code == 201, response.data
    with as_tenant(salon_a.tenant):
        booking = Booking.objects.get(id=response.data["id"])

    # 30 % de (450 + 80) = 159, au-dessus du plancher de 150.
    assert booking.total_amount == Decimal("530")
    assert booking.deposit_amount == Decimal("159")


@pytest.mark.django_db
def test_a_salon_without_a_rate_falls_back_to_its_minimum(api_client, salon_a):
    """Sans pourcentage, c.est le plancher du salon qui s.applique.

    Autrefois chaque prestation portait son propre montant ; il vit desormais
    sur la fiche du salon, a un seul endroit. Le comportement observable est
    le meme : un salon qui n.a pas regle de taux continue de reclamer une
    somme fixe."""
    with as_tenant(salon_a.tenant):
        salon_a.service.requires_deposit = True
        salon_a.service.save()
        SalonProfile.objects.filter(tenant=salon_a.tenant).update(
            deposit_rate=0, deposit_minimum=Decimal("150")
        )

    response = api_client.post(
        "/api/v1/public/bookings",
        {
            "service": str(salon_a.service.id),
            "starts_at": next_monday_at(10).isoformat(),
            "full_name": "Awa Diallo",
            "phone": "+242066112233",
            "accepts_policy": True,
        },
        format="json",
        headers=HOST,
    )

    with as_tenant(salon_a.tenant):
        booking = Booking.objects.get(id=response.data["id"])

    assert booking.deposit_amount == Decimal("150")


@pytest.mark.django_db
def test_a_rate_above_one_hundred_is_refused(api_client, salon_a):
    from tests.test_finance_automatic import login

    login(api_client, salon_a.owner)
    response = api_client.patch(
        "/api/v1/salon-profile", {"deposit_rate": 150}, format="json"
    )

    assert response.status_code == 400
