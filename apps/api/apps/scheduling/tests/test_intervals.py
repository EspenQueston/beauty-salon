"""Arithmetique d'intervalles : aucun acces base, aucun fixture."""

from datetime import UTC, datetime, timedelta

import pytest

from apps.scheduling.services.intervals import Interval, merge, subtract


def at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 3, 2, hour, minute, tzinfo=UTC)


def iv(start_hour: int, end_hour: int) -> Interval:
    return Interval(at(start_hour), at(end_hour))


def test_interval_rejects_zero_or_negative_duration():
    with pytest.raises(ValueError):
        Interval(at(10), at(10))
    with pytest.raises(ValueError):
        Interval(at(11), at(10))


def test_intervals_that_only_touch_do_not_overlap():
    # 14h-15h puis 15h-16h : deux rendez-vous consecutifs, pas un conflit.
    assert not iv(14, 15).overlaps(iv(15, 16))


def test_merge_joins_touching_and_overlapping_intervals():
    merged = merge([iv(9, 11), iv(10, 12), iv(12, 13), iv(15, 16)])
    assert merged == [Interval(at(9), at(13)), Interval(at(15), at(16))]


def test_merge_of_nothing_is_nothing():
    assert merge([]) == []


def test_subtract_splits_an_interval_in_two():
    assert subtract([iv(9, 18)], [iv(12, 13)]) == [
        Interval(at(9), at(12)),
        Interval(at(13), at(18)),
    ]


def test_subtract_trims_edges():
    assert subtract([iv(9, 18)], [iv(8, 10)]) == [Interval(at(10), at(18))]
    assert subtract([iv(9, 18)], [iv(17, 20)]) == [Interval(at(9), at(17))]


def test_subtract_can_empty_everything():
    assert subtract([iv(9, 18)], [iv(8, 19)]) == []


def test_subtract_ignores_holes_that_do_not_touch():
    assert subtract([iv(9, 12)], [iv(14, 15)]) == [Interval(at(9), at(12))]


def test_expanded_adds_buffer_on_both_sides():
    expanded = iv(14, 15).expanded(timedelta(minutes=15), timedelta(minutes=15))
    assert expanded == Interval(at(13, 45), at(15, 15))
