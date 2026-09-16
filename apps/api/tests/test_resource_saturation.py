"""Saturation d'une ressource comptee.

`saturated()` est la fonction ou une implementation naive se trompe : elle
doit distinguer « deux rendez-vous se chevauchent » de « deux rendez-vous
existent », et rester exacte quand trois se recouvrent partiellement.

Fonctions pures : ces tests ne montent aucun salon.
"""

from datetime import UTC, datetime, timedelta

import pytest

from apps.scheduling.services.intervals import Interval, saturated

H = datetime(2026, 9, 14, 9, 0, tzinfo=UTC)


def at(hours: float, length: float) -> Interval:
    start = H + timedelta(hours=hours)
    return Interval(start, start + timedelta(hours=length))


def as_hours(intervals) -> list[tuple[float, float]]:
    return [
        (
            (item.start - H).total_seconds() / 3600,
            (item.end - H).total_seconds() / 3600,
        )
        for item in intervals
    ]


def test_one_booking_does_not_saturate_two_basins():
    """Le piege principal : un lavage en cours ne bloque pas le second bac."""
    assert saturated([at(0, 2)], capacity=2) == []


def test_two_overlapping_bookings_saturate_two_basins():
    blocked = saturated([at(0, 2), at(1, 2)], capacity=2)

    # Seule la partie commune est bloquee, pas l'union des deux.
    assert as_hours(blocked) == [(1.0, 2.0)]


def test_two_bookings_that_only_touch_do_not_saturate():
    """9h-11h puis 11h-13h ne se chevauchent pas : intervalles semi-ouverts."""
    assert saturated([at(0, 2), at(2, 2)], capacity=2) == []


def test_three_partial_overlaps_are_measured_exactly():
    """Le cas ou une comparaison deux a deux se trompe.

    A 9h-12h, B 10h-13h, C 11h-14h. Avec trois exemplaires, seule la tranche
    ou les trois coexistent - 11h a 12h - est saturee.
    """
    blocked = saturated([at(0, 3), at(1, 3), at(2, 3)], capacity=3)

    assert as_hours(blocked) == [(2.0, 3.0)]


def test_the_same_three_saturate_a_pair_over_a_wider_stretch():
    blocked = saturated([at(0, 3), at(1, 3), at(2, 3)], capacity=2)

    # 10h-11h : A+B. 11h-12h : A+B+C. 12h-13h : B+C. A 13h, B se termine et
    # il ne reste que C : un exemplaire redevient libre.
    assert as_hours(blocked) == [(1.0, 4.0)]


def test_a_single_unit_is_blocked_by_any_booking():
    blocked = saturated([at(0, 2), at(4, 1)], capacity=1)

    assert as_hours(blocked) == [(0.0, 2.0), (4.0, 5.0)]


def test_a_resource_with_no_unit_blocks_everything_it_touches():
    blocked = saturated([at(0, 2)], capacity=0)

    assert as_hours(blocked) == [(0.0, 2.0)]


def test_nothing_booked_blocks_nothing():
    assert saturated([], capacity=2) == []


@pytest.mark.parametrize("capacity", [1, 2, 3, 5])
def test_saturation_never_exceeds_the_bookings_span(capacity):
    """Garde-fou : on ne peut pas bloquer un moment ou rien n'est reserve."""
    bookings = [at(0, 2), at(1, 1), at(3, 2)]
    blocked = saturated(bookings, capacity=capacity)

    for item in blocked:
        assert any(item.start < b.end and b.start < item.end for b in bookings)
