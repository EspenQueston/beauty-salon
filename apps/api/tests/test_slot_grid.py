"""Ou tombent les creneaux proposes, et pourquoi.

La grille etait calee sur l'horloge depuis minuit. Un salon ouvrant a 9 h 30
avec un pas d'une heure ne voyait jamais 9 h 30 proposee : le premier creneau
tombait a 10 h. Trente minutes invendables par jour, six jours sur sept,
alors que l'heure figurait comme ouverte sur son propre mini-site.

Elle est desormais ancree au debut de chaque plage. Ces tests verifient les
deux proprietes a la fois : l'ouverture est proposee, **et** on ne propose
toujours pas d'heures batardes apres un rendez-vous.
"""

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from apps.scheduling.models import BusinessHours
from apps.scheduling.services.availability import available_slots
from conftest import as_tenant

BRAZZAVILLE = ZoneInfo("Africa/Brazzaville")


def next_monday() -> date:
    today = datetime.now(BRAZZAVILLE).date()
    return today + timedelta(days=(0 - today.weekday()) % 7 or 7)


def set_hours(salon, ranges, weekday=0):
    """Remplace la grille du salon par les plages donnees."""
    with as_tenant(salon.tenant):
        BusinessHours.objects.filter(staff_member__isnull=True).delete()
        for start, end in ranges:
            BusinessHours.objects.create(
                tenant=salon.tenant,
                weekday=weekday,
                starts_at=time.fromisoformat(start),
                ends_at=time.fromisoformat(end),
            )


def set_rules(salon, *, granularity=60, duration=120, buffer=0):
    from apps.salons.models import SalonProfile

    with as_tenant(salon.tenant):
        SalonProfile.objects.filter(tenant=salon.tenant).update(
            slot_granularity_minutes=granularity,
            buffer_minutes=buffer,
            min_lead_time_minutes=0,
        )
        salon.service.duration_minutes = duration
        salon.service.requires_deposit = False
        salon.service.save()


def slots_on(salon, day, **kwargs):
    with as_tenant(salon.tenant):
        found = available_slots(
            tenant=salon.tenant,
            service=salon.service,
            staff_members=[salon.staff],
            date_from=day,
            date_to=day,
            **kwargs,
        )
    return sorted(
        {slot.starts_at.astimezone(BRAZZAVILLE).strftime("%H:%M") for slot in found}
    )


# ---------------------------------------------------------------------------
# L'ouverture est proposee
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_an_opening_on_the_half_hour_is_offered(salon_a):
    """Le defaut corrige : 9 h 30 n'apparaissait jamais."""
    set_rules(salon_a, granularity=60, duration=120)
    set_hours(salon_a, [("09:30", "13:00")])

    assert slots_on(salon_a, next_monday()) == ["09:30", "10:30"]


@pytest.mark.django_db
def test_an_opening_on_the_hour_is_unchanged(salon_a):
    """Les salons qui ouvraient deja sur l'heure ne voient aucune
    difference."""
    set_rules(salon_a, granularity=60, duration=120)
    set_hours(salon_a, [("09:00", "13:00")])

    assert slots_on(salon_a, next_monday()) == ["09:00", "10:00", "11:00"]


@pytest.mark.django_db
def test_each_block_carries_its_own_grid(salon_a):
    """Une matinee a 9 h 30 et un apres-midi a 14 h gardent chacun son
    rythme : la grille de l'un ne decale pas l'autre."""
    set_rules(salon_a, granularity=60, duration=120)
    set_hours(salon_a, [("09:30", "13:00"), ("14:00", "18:00")])

    assert slots_on(salon_a, next_monday()) == [
        "09:30",
        "10:30",
        "14:00",
        "15:00",
        "16:00",
    ]


@pytest.mark.django_db
def test_a_quarter_past_opening_works_too(salon_a):
    set_rules(salon_a, granularity=30, duration=60)
    set_hours(salon_a, [("08:15", "10:45")])

    assert slots_on(salon_a, next_monday()) == ["08:15", "08:45", "09:15", "09:45"]


# ---------------------------------------------------------------------------
# Ce que l'ancrage ne casse pas
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_booking_ending_at_an_odd_time_never_produces_an_odd_slot(salon_a):
    """La raison d'etre de l'alignement.

    Un rendez-vous qui finit a 10 h 07 ouvre un intervalle libre a 10 h 07.
    Le creneau suivant doit tomber sur la grille de la plage - 11 h - et
    jamais a 10 h 07.
    """
    from apps.scheduling.models import Booking

    set_rules(salon_a, granularity=60, duration=60)
    set_hours(salon_a, [("09:00", "14:00")])

    day = next_monday()
    start = datetime.combine(day, time(9, 0), tzinfo=BRAZZAVILLE)

    with as_tenant(salon_a.tenant):
        Booking.objects.create(
            tenant=salon_a.tenant,
            customer=salon_a.customer,
            staff_member=salon_a.staff,
            service=salon_a.service,
            starts_at=start,
            ends_at=start + timedelta(minutes=67),  # finit a 10 h 07
            status=Booking.Status.CONFIRMED,
            service_name="Pose",
            total_amount=Decimal("100"),
        )

    offered = slots_on(salon_a, day)

    assert "10:07" not in offered
    assert offered == ["11:00", "12:00", "13:00"]


@pytest.mark.django_db
def test_the_grid_stays_anchored_to_the_block_not_to_the_gap(salon_a):
    """Meme apres un trou, les heures restent celles de la plage.

    Sans ancre de plage, l'intervalle libre d'apres rendez-vous aurait
    fabrique sa propre grille et les heures auraient derive d'un jour a
    l'autre.
    """
    from apps.scheduling.models import Booking

    set_rules(salon_a, granularity=60, duration=60)
    set_hours(salon_a, [("09:30", "15:30")])

    day = next_monday()
    start = datetime.combine(day, time(10, 30), tzinfo=BRAZZAVILLE)

    with as_tenant(salon_a.tenant):
        Booking.objects.create(
            tenant=salon_a.tenant,
            customer=salon_a.customer,
            staff_member=salon_a.staff,
            service=salon_a.service,
            starts_at=start,
            ends_at=start + timedelta(minutes=45),  # finit a 11 h 15
            status=Booking.Status.CONFIRMED,
            service_name="Pose",
            total_amount=Decimal("100"),
        )

    offered = slots_on(salon_a, day)

    # Tout reste sur la demie, l'ancre de la plage.
    assert all(hour.endswith(":30") for hour in offered), offered
    assert "09:30" in offered
    assert "11:30" in offered


@pytest.mark.django_db
def test_a_service_longer_than_every_block_is_never_offered(salon_a):
    """Le cas qui a motive l'alerte du panneau : une pose de 4 h dans une
    matinee de 3 h 30."""
    set_rules(salon_a, granularity=60, duration=240)
    set_hours(salon_a, [("09:30", "13:00")])

    assert slots_on(salon_a, next_monday()) == []


@pytest.mark.django_db
def test_a_block_exactly_as_long_as_the_service_gives_one_slot(salon_a):
    set_rules(salon_a, granularity=60, duration=240)
    set_hours(salon_a, [("09:00", "13:00")])

    assert slots_on(salon_a, next_monday()) == ["09:00"]


@pytest.mark.django_db
def test_options_still_shorten_the_list(salon_a):
    """L'ancrage ne doit pas defaire ce que les options ont apporte."""
    set_rules(salon_a, granularity=60, duration=120)
    set_hours(salon_a, [("09:30", "13:00")])

    assert slots_on(salon_a, next_monday()) == ["09:30", "10:30"]
    assert slots_on(salon_a, next_monday(), extra_minutes=60) == ["09:30"]
