from datetime import date

import pytest

from tristhana.domain.moon import MoonDay, MoonDayKind
from tristhana.moon.rules import classify, dedup, tithi

K = MoonDayKind


@pytest.mark.parametrize(
    ("moon", "sun", "expected"),
    [
        (0.0, 0.0, 1),
        (11.999, 0.0, 1),
        (12.0, 0.0, 2),
        (179.999, 0.0, 15),
        (180.0, 0.0, 16),
        (359.999, 0.0, 30),
        (10.0, 350.0, 2),  # wraps: (10 - 350) mod 360 = 20
        (350.0, 10.0, 29),
    ],
)
def test_tithi(moon: float, sun: float, expected: int) -> None:
    assert tithi(moon, sun) == expected


@pytest.mark.parametrize(
    ("t0", "t1", "expected"),
    [
        (15, 16, K.PURNIMA),
        (15, 15, K.PURNIMA),
        (30, 1, K.AMAVASYA),
        (14, 16, K.KSHAYA_PURNIMA),
        (29, 1, K.KSHAYA_AMAVASYA),  # skip over 30 across the wrap
        (13, 16, K.KSHAYA_PURNIMA),  # skips 14 and 15
        (14, 15, None),
        (29, 30, None),
        (1, 2, None),
        (5, 7, None),  # skips 6 only
    ],
)
def test_classify(t0: int, t1: int, expected: MoonDayKind | None) -> None:
    assert classify(t0, t1) == expected


def _day(iso: str, kind: MoonDayKind = K.PURNIMA) -> MoonDay:
    return MoonDay(date.fromisoformat(iso), kind)


def test_dedup_keeps_first_day_of_a_chain() -> None:
    days = [_day("2026-01-03"), _day("2026-01-04")]

    assert dedup(days) == [_day("2026-01-03")]


def test_dedup_keeps_events_two_days_apart() -> None:
    days = [_day("2026-01-03"), _day("2026-01-05", K.AMAVASYA)]

    assert dedup(days) == days


def test_dedup_compares_with_last_accepted_event_across_phases() -> None:
    # Day 4 is dropped (1 day after 3); day 5 is 2 days after the accepted day 3.
    days = [_day("2026-01-03"), _day("2026-01-04"), _day("2026-01-05", K.AMAVASYA)]

    assert dedup(days) == [_day("2026-01-03"), _day("2026-01-05", K.AMAVASYA)]
