"""Moteur de creneaux, cas reels et cas limites.

Toutes les dates de reference tombent en mars 2026. `now` est toujours passe
explicitement : un test de disponibilite qui depend de l'heure a laquelle on
lance la suite est un test qui finira par echouer sans raison.
"""

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from apps.salons.models import SalonProfile
from apps.scheduling.models import AvailabilityException, Booking
from apps.scheduling.services.availability import available_slots, is_slot_available
from conftest import as_tenant
from tests.factories import (
    BookingFactory,
    BusinessHoursFactory,
    ServiceFactory,
    StaffMemberFactory,
    StaffServiceFactory,
)

MONDAY = date(2026, 3, 2)
SUNDAY = date(2026, 3, 8)
BRAZZAVILLE = ZoneInfo("Africa/Brazzaville")  # UTC+1, sans heure d'ete

# Bien avant les dates testees : le delai minimal ne masque jamais de creneau.
NOW = datetime(2026, 2, 1, 8, 0, tzinfo=UTC)


def local(day: date, hour: int, minute: int = 0, tz: ZoneInfo = BRAZZAVILLE) -> datetime:
    return datetime.combine(day, time(hour, minute), tzinfo=tz)


def slots_for(salon, day: date, *, staff=None, service=None, now=NOW):
    with as_tenant(salon.tenant):
        return available_slots(
            tenant=salon.tenant,
            service=service or salon.service,
            staff_members=[staff or salon.staff],
            date_from=day,
            date_to=day,
            now=now,
        )


def starts_local(slots) -> list[str]:
    return [s.starts_at.astimezone(BRAZZAVILLE).strftime("%H:%M") for s in slots]


@pytest.mark.django_db
def test_open_day_produces_slots_on_the_local_grid(salon_a):
    """9h-18h, prestation de 2h, pas de 15 min : de 9h00 a 16h00."""
    slots = slots_for(salon_a, MONDAY)

    assert starts_local(slots)[:3] == ["09:00", "09:15", "09:30"]
    assert starts_local(slots)[-1] == "16:00"
    # 9h00 -> 16h00 par pas de 15 min.
    assert len(slots) == 29


@pytest.mark.django_db
def test_slots_are_returned_in_utc(salon_a):
    """Le salon est a UTC+1 : 9h locales valent 8h UTC."""
    first = slots_for(salon_a, MONDAY)[0]

    assert first.starts_at == datetime(2026, 3, 2, 8, 0, tzinfo=UTC)
    assert first.ends_at == datetime(2026, 3, 2, 10, 0, tzinfo=UTC)


@pytest.mark.django_db
def test_closed_day_has_no_slots(salon_a):
    """Le salon n'ouvre pas le dimanche (horaires lundi-samedi)."""
    assert slots_for(salon_a, SUNDAY) == []


@pytest.mark.django_db
def test_existing_booking_removes_the_overlapping_slots(salon_a):
    with as_tenant(salon_a.tenant):
        BookingFactory(
            tenant=salon_a.tenant,
            customer=salon_a.customer,
            staff_member=salon_a.staff,
            service=salon_a.service,
            starts_at=local(MONDAY, 10),
            ends_at=local(MONDAY, 12),
        )

    times = starts_local(slots_for(salon_a, MONDAY))

    # Un creneau de 2h ne peut plus commencer entre 8h15 et 12h exclu.
    assert "09:00" not in times  # finirait a 11h, en plein rendez-vous
    assert "08:00" not in times  # hors horaires de toute facon
    assert "12:00" in times  # commence pile a la fin du precedent
    assert "10:00" not in times


@pytest.mark.django_db
def test_cancelled_booking_frees_the_slot_again(salon_a):
    with as_tenant(salon_a.tenant):
        BookingFactory(
            tenant=salon_a.tenant,
            customer=salon_a.customer,
            staff_member=salon_a.staff,
            service=salon_a.service,
            starts_at=local(MONDAY, 10),
            ends_at=local(MONDAY, 12),
            status=Booking.Status.CANCELLED,
        )

    assert "10:00" in starts_local(slots_for(salon_a, MONDAY))


@pytest.mark.django_db
def test_buffer_keeps_distance_around_an_existing_booking(salon_a):
    """Un battement de 30 min interdit d'enchainer immediatement."""
    with as_tenant(salon_a.tenant):
        SalonProfile.objects.filter(tenant=salon_a.tenant).update(buffer_minutes=30)
        BookingFactory(
            tenant=salon_a.tenant,
            customer=salon_a.customer,
            staff_member=salon_a.staff,
            service=salon_a.service,
            starts_at=local(MONDAY, 10),
            ends_at=local(MONDAY, 12),
        )

    times = starts_local(slots_for(salon_a, MONDAY))

    assert "12:00" not in times  # trop pres de la fin du precedent
    assert "12:30" in times


@pytest.mark.django_db
def test_leave_removes_the_afternoon(salon_a):
    with as_tenant(salon_a.tenant):
        AvailabilityException.objects.create(
            tenant=salon_a.tenant,
            staff_member=salon_a.staff,
            kind=AvailabilityException.Kind.LEAVE,
            starts_at=local(MONDAY, 13),
            ends_at=local(MONDAY, 19),
        )

    times = starts_local(slots_for(salon_a, MONDAY))

    assert times[-1] == "11:00"  # dernier creneau de 2h finissant a 13h
    assert "13:00" not in times


@pytest.mark.django_db
def test_salon_wide_exception_applies_to_every_staff_member(salon_a):
    """Une fermeture sans prestataire designe vise tout le salon."""
    with as_tenant(salon_a.tenant):
        AvailabilityException.objects.create(
            tenant=salon_a.tenant,
            staff_member=None,
            kind=AvailabilityException.Kind.BLOCKED,
            starts_at=local(MONDAY, 0),
            ends_at=local(MONDAY, 23, 59),
            reason="Ferie",
        )

    assert slots_for(salon_a, MONDAY) == []


@pytest.mark.django_db
def test_extra_opening_creates_slots_on_a_closed_day(salon_a):
    """Ouverture exceptionnelle un dimanche."""
    with as_tenant(salon_a.tenant):
        AvailabilityException.objects.create(
            tenant=salon_a.tenant,
            staff_member=salon_a.staff,
            kind=AvailabilityException.Kind.EXTRA_OPENING,
            starts_at=local(SUNDAY, 10),
            ends_at=local(SUNDAY, 14),
        )

    times = starts_local(slots_for(salon_a, SUNDAY))

    assert times[0] == "10:00"
    assert times[-1] == "12:00"


@pytest.mark.django_db
def test_minimum_lead_time_hides_imminent_slots(salon_a):
    """Reserver dans les deux heures est refuse si le salon l'exige."""
    with as_tenant(salon_a.tenant):
        SalonProfile.objects.filter(tenant=salon_a.tenant).update(min_lead_time_minutes=180)

    # Il est 9h locales le jour meme : les creneaux avant midi disparaissent.
    slots = slots_for(salon_a, MONDAY, now=local(MONDAY, 9))

    assert starts_local(slots)[0] == "12:00"


@pytest.mark.django_db
def test_booking_horizon_is_capped(salon_a):
    with as_tenant(salon_a.tenant):
        SalonProfile.objects.filter(tenant=salon_a.tenant).update(max_advance_days=7)

    # MONDAY est a plus d'un mois de NOW : au-dela de l'horizon autorise.
    assert slots_for(salon_a, MONDAY) == []


@pytest.mark.django_db
def test_staff_without_hours_offers_nothing(salon_a):
    """Un prestataire sans horaires propres herite du salon ; si le salon
    n'en a pas non plus, il ne propose rien."""
    with as_tenant(salon_a.tenant):
        newcomer = StaffMemberFactory(tenant=salon_a.tenant, name="Nouvelle")
        StaffServiceFactory(
            tenant=salon_a.tenant, staff_member=newcomer, service=salon_a.service
        )
        salon_a.tenant.businesshourss.all().delete()

    assert slots_for(salon_a, MONDAY, staff=newcomer) == []


@pytest.mark.django_db
def test_staff_specific_hours_override_salon_hours(salon_a):
    """Une prestataire qui ne travaille que le matin ne propose que le matin,
    meme si le salon est ouvert jusqu'a 18h."""
    with as_tenant(salon_a.tenant):
        part_time = StaffMemberFactory(tenant=salon_a.tenant, name="Mi-temps")
        StaffServiceFactory(
            tenant=salon_a.tenant, staff_member=part_time, service=salon_a.service
        )
        BusinessHoursFactory(
            tenant=salon_a.tenant,
            staff_member=part_time,
            weekday=0,
            starts_at=time(9, 0),
            ends_at=time(13, 0),
        )

    times = starts_local(slots_for(salon_a, MONDAY, staff=part_time))

    assert times[0] == "09:00"
    assert times[-1] == "11:00"  # dernier creneau de 2h finissant a 13h


@pytest.mark.django_db
def test_service_longer_than_the_open_window_has_no_slot(salon_a):
    """Une prestation de 10h ne rentre pas dans une journee de 9h."""
    with as_tenant(salon_a.tenant):
        marathon = ServiceFactory(
            tenant=salon_a.tenant,
            category=salon_a.category,
            name="Perruque sur mesure",
            duration_minutes=600,
        )
        StaffServiceFactory(
            tenant=salon_a.tenant, staff_member=salon_a.staff, service=marathon
        )

    assert slots_for(salon_a, MONDAY, service=marathon) == []


@pytest.mark.django_db
def test_long_service_fits_when_the_day_is_long_enough(salon_a):
    """Une prestation de 5h - tresses longues - tient dans la journee."""
    with as_tenant(salon_a.tenant):
        braids = ServiceFactory(
            tenant=salon_a.tenant,
            category=salon_a.category,
            name="Tresses longues",
            duration_minutes=300,
        )
        StaffServiceFactory(
            tenant=salon_a.tenant, staff_member=salon_a.staff, service=braids
        )

    times = starts_local(slots_for(salon_a, MONDAY, service=braids))

    assert times[0] == "09:00"
    assert times[-1] == "13:00"


@pytest.mark.django_db
def test_multiple_staff_members_produce_slots_for_each(salon_a):
    with as_tenant(salon_a.tenant):
        second = StaffMemberFactory(tenant=salon_a.tenant, name="Grace")
        StaffServiceFactory(
            tenant=salon_a.tenant, staff_member=second, service=salon_a.service
        )

        slots = available_slots(
            tenant=salon_a.tenant,
            service=salon_a.service,
            staff_members=[salon_a.staff, second],
            date_from=MONDAY,
            date_to=MONDAY,
            now=NOW,
        )

    offered = {slot.staff_member_id for slot in slots}
    assert offered == {str(salon_a.staff.id), str(second.id)}
    # Les creneaux sont tries par heure, pas groupes par prestataire.
    assert slots == sorted(slots, key=lambda s: (s.starts_at, s.staff_member_id))


@pytest.mark.django_db
def test_is_slot_available_agrees_with_the_slot_list(salon_a):
    slots = slots_for(salon_a, MONDAY)

    with as_tenant(salon_a.tenant):
        assert is_slot_available(
            tenant=salon_a.tenant,
            service=salon_a.service,
            staff_member=salon_a.staff,
            starts_at=slots[0].starts_at,
            now=NOW,
        )
        # 8h locales : le salon est ferme.
        assert not is_slot_available(
            tenant=salon_a.tenant,
            service=salon_a.service,
            staff_member=salon_a.staff,
            starts_at=local(MONDAY, 8),
            now=NOW,
        )


@pytest.mark.django_db
def test_daylight_saving_shift_is_handled(salon_a):
    """Un salon parisien le jour du passage a l'heure d'ete.

    Le 29 mars 2026, 2h devient 3h. La journee ne dure que 23h : un decalage
    fixe donnerait des creneaux faux d'une heure toute la journee.
    """
    paris = ZoneInfo("Europe/Paris")
    with as_tenant(salon_a.tenant):
        salon_a.tenant.timezone = "Europe/Paris"
        salon_a.tenant.save()
        AvailabilityException.objects.create(
            tenant=salon_a.tenant,
            staff_member=salon_a.staff,
            kind=AvailabilityException.Kind.EXTRA_OPENING,
            starts_at=local(date(2026, 3, 29), 9, tz=paris),
            ends_at=local(date(2026, 3, 29), 18, tz=paris),
        )

    slots = slots_for(salon_a, date(2026, 3, 29))

    # 9h locales apres le changement = 07:00 UTC (UTC+2), pas 08:00.
    assert slots[0].starts_at == datetime(2026, 3, 29, 7, 0, tzinfo=UTC)
    assert slots[0].starts_at.astimezone(paris).hour == 9


@pytest.mark.django_db
def test_a_booking_that_crosses_midnight_blocks_the_next_morning(salon_a):
    """Une prestation tardive qui deborde sur le lendemain doit bloquer les
    premiers creneaux du jour suivant."""
    tuesday = MONDAY + timedelta(days=1)
    with as_tenant(salon_a.tenant):
        BookingFactory(
            tenant=salon_a.tenant,
            customer=salon_a.customer,
            staff_member=salon_a.staff,
            service=salon_a.service,
            starts_at=local(MONDAY, 22),
            ends_at=local(tuesday, 10),
        )

    times = starts_local(slots_for(salon_a, tuesday))

    assert "09:00" not in times
    assert "10:00" in times
