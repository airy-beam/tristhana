"""The teacher view's pure rules (ST-06, spec §3, §6, §8, ADR-0031): two states and no other,
`SHARED` covering every `DayStatus`, output types with nowhere to put a private value, the seven
card days and the quiet note."""

from dataclasses import fields, is_dataclass
from datetime import date, timedelta
from itertools import combinations

import pytest

from tristhana.domain.days import DayStatus
from tristhana.domain.practice import PracticeLength
from tristhana.domain.teacher_view import (
    CARD_DAYS,
    QUIET_DAYS,
    SHARED,
    DayCell,
    SharedDay,
    StudentCard,
    StudentToday,
    card_days,
    is_quiet,
)

TODAY = date(2026, 11, 7)
LONG_AGO = date(2026, 1, 1)
LENGTH = PracticeLength(("primary",), "navasana")
P, R = SharedDay.PRACTICED, SharedDay.REST


def _ago(days: int, today: date = TODAY) -> date:
    return today - timedelta(days=days)


# Two states, and nowhere to put a third


def test_the_limits_are_the_specs() -> None:
    assert (CARD_DAYS, QUIET_DAYS) == (7, 21)


def test_a_shared_day_has_exactly_two_states() -> None:
    assert {s.name: s.value for s in SharedDay} == {"PRACTICED": "practiced", "REST": "rest"}


def test_shared_covers_every_status() -> None:
    assert set(SHARED) == set(DayStatus)


@pytest.mark.parametrize(
    ("status", "shown"),
    [
        (DayStatus.PRACTICED, P),
        (DayStatus.REST, R),
        (DayStatus.MOON, R),
        (DayStatus.LADIES, R),
        (DayStatus.SICK, R),
        (DayStatus.TRAVEL, R),
        (DayStatus.SKIPPED, None),
    ],
)
def test_the_projection_table(status: DayStatus, shown: SharedDay | None) -> None:
    assert SHARED[status] is shown


@pytest.mark.parametrize(
    ("kind", "names"),
    [
        (StudentToday, ["id", "name", "today"]),
        (DayCell, ["date", "shown", "length"]),
        (StudentCard, ["id", "name", "days", "last_asana", "quiet", "next_asanas"]),
    ],
)
def test_output_types_have_exactly_the_agreed_fields(kind: type, names: list[str]) -> None:
    assert is_dataclass(kind)
    assert [f.name for f in fields(kind)] == names


# The seven card days


def test_the_card_has_seven_days_oldest_first_ending_today() -> None:
    days = card_days({}, {}, TODAY)

    assert [d.date for d in days] == [_ago(n) for n in range(6, -1, -1)]
    assert all(d.shown is None and d.length is None for d in days)


def test_a_shown_day_keeps_its_state_and_a_practiced_day_its_length() -> None:
    days = card_days({TODAY: P, _ago(1): R}, {TODAY: LENGTH}, TODAY)

    assert days[-1] == DayCell(TODAY, P, LENGTH)
    assert days[-2] == DayCell(_ago(1), R, None)


def test_later_and_older_dates_are_dropped() -> None:
    later, older = TODAY + timedelta(days=1), _ago(7)

    days = card_days({later: R, older: P}, {later: LENGTH, older: LENGTH}, TODAY)

    assert [d.date for d in days] == [_ago(n) for n in range(6, -1, -1)]
    assert all(d.shown is None for d in days)


@pytest.mark.parametrize("shown", [{}, {TODAY: R}], ids=["blank", "rest"])
def test_a_length_shows_only_on_a_shown_practiced_day(shown: dict[date, SharedDay]) -> None:
    days = card_days(shown, {TODAY: LENGTH}, TODAY)

    assert days[-1].length is None


@pytest.mark.parametrize(
    ("today", "first"),
    [
        (date(2026, 3, 3), date(2026, 2, 25)),
        (date(2028, 3, 2), date(2028, 2, 25)),  # a leap year
        (date(2027, 1, 2), date(2026, 12, 27)),
    ],
    ids=["month-end", "leap-year", "year-end"],
)
def test_the_days_cross_month_and_year_ends(today: date, first: date) -> None:
    days = card_days({first: R}, {}, today)

    assert days[0] == DayCell(first, R, None)
    assert days[-1].date == today
    assert len(days) == CARD_DAYS


def test_the_days_are_always_seven_in_a_row_ending_today() -> None:
    """Every date of a leap-year cycle: no month or year end is special."""
    for offset in range(4 * 366):
        today = date(2027, 1, 1) + timedelta(days=offset)

        dates = [d.date for d in card_days({}, {}, today)]

        assert dates == [today - timedelta(days=n) for n in range(6, -1, -1)]


# The quiet note


def test_20_days_since_the_link_is_not_quiet_and_21_is() -> None:
    assert is_quiet((), TODAY, _ago(20), True) is False
    assert is_quiet((), TODAY, _ago(21), True) is True


def test_a_shown_day_20_days_ago_keeps_it_away_and_21_does_not() -> None:
    assert is_quiet((_ago(20),), TODAY, LONG_AGO, True) is False
    assert is_quiet((_ago(21),), TODAY, LONG_AGO, True) is True


def test_a_shown_day_today_keeps_it_away() -> None:
    assert is_quiet((TODAY,), TODAY, LONG_AGO, True) is False


def test_a_link_date_after_today_is_not_quiet() -> None:
    """Moving west: `linked_on` can pass the newly computed today (spec §6)."""
    assert is_quiet((), TODAY, TODAY + timedelta(days=1), True) is False


def test_a_stored_date_after_today_is_not_a_shown_day_yet() -> None:
    """Moving west again: such a day waits until its date arrives, so it counts for nothing."""
    assert is_quiet((TODAY + timedelta(days=1),), TODAY, LONG_AGO, True) is True


def test_only_rest_keeps_it_away_as_practice_does() -> None:
    """It takes dates alone: a rest day is a shown day, whatever kind it was."""
    rest_only = {_ago(n): R for n in (3, 4, 5)}

    assert is_quiet(rest_only.keys(), TODAY, LONG_AGO, True) is False


def test_not_agreed_hides_the_note_in_a_case_that_is_otherwise_true() -> None:
    assert is_quiet((), TODAY, LONG_AGO, True) is True
    assert is_quiet((), TODAY, LONG_AGO, False) is False


# Every link age around the limit, with every set of shown days drawn from the ages that matter.
LINK_AGES = range(-3, 45)
SHOWN_AGES = (-1, 0, 1, 19, 20, 21, 22, 40)
SHOWN_SETS = [c for n in range(len(SHOWN_AGES) + 1) for c in combinations(SHOWN_AGES, n)]


def test_without_agreement_there_is_never_a_note() -> None:
    for link_age in LINK_AGES:
        for ages in SHOWN_SETS:
            shown = {_ago(a) for a in ages}

            assert is_quiet(shown, TODAY, _ago(link_age), False) is False


def test_the_note_is_the_three_conditions_and_nothing_else() -> None:
    for link_age in LINK_AGES:
        for ages in SHOWN_SETS:
            shown = {_ago(a) for a in ages}

            expected = link_age >= QUIET_DAYS and not any(0 <= a < QUIET_DAYS for a in ages)

            assert is_quiet(shown, TODAY, _ago(link_age), True) is expected, (link_age, ages)


def test_days_outside_the_window_never_matter_and_one_inside_always_does() -> None:
    old = {_ago(a) for a in range(QUIET_DAYS, 200)}

    assert is_quiet(old, TODAY, LONG_AGO, True) is True
    for inside in range(QUIET_DAYS):
        assert is_quiet(old | {_ago(inside)}, TODAY, LONG_AGO, True) is False
