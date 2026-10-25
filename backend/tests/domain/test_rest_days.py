"""Auto-rest and the weekly day off (PR-09, ADR-0022)."""

from datetime import UTC, date, datetime, timedelta

import pytest

from tristhana.domain.rest_days import (
    AutoDay,
    AutoKind,
    DayOff,
    InvalidDayOff,
    auto_days,
    change_day_off,
    check_day_off,
    day_off_on,
    joined_on,
)

SAT, SUN = frozenset({6}), frozenset({7})
NONE = frozenset[int]()
MON = date(2026, 10, 19)  # a Monday
JOINED = date(2026, 10, 1)


def _week(start: date = MON) -> tuple[date, date]:
    return start, start + timedelta(days=6)


def test_check_day_off_allows_one_weekday_or_none() -> None:
    assert check_day_off([6]) == SAT
    assert check_day_off([]) == NONE


def test_two_days_off_are_allowed() -> None:
    assert check_day_off([6, 7]) == frozenset({6, 7})


@pytest.mark.parametrize("days", [[5, 6, 7], [0], [8], [6, 6]])
def test_check_day_off_rejects_more_than_two_or_out_of_range(days: list[int]) -> None:
    with pytest.raises(InvalidDayOff):
        check_day_off(days)


def test_day_off_on_uses_the_previous_choice_before_a_change() -> None:
    off = DayOff(SUN, since=MON, before=SAT)
    assert day_off_on(off, MON - timedelta(days=1)) == SAT
    assert day_off_on(off, MON) == SUN
    assert day_off_on(DayOff(), MON) == NONE


def test_first_choice_applies_to_all_history() -> None:
    first = change_day_off(DayOff(), SAT, MON)
    assert first == DayOff(SAT, since=MON)
    assert day_off_on(first, MON - timedelta(days=100)) == SAT


def test_correcting_the_first_choice_the_same_day_stays_retroactive() -> None:
    """A mis-tap ("Yes" to Saturday, then Sunday) must not leave old auto Saturdays."""
    first = change_day_off(DayOff(), SAT, MON)
    fixed = change_day_off(first, SUN, MON)
    assert fixed == DayOff(SUN, since=MON)
    assert day_off_on(fixed, MON - timedelta(days=100)) == SUN


def test_later_change_applies_from_today_and_keeps_the_old_day_before() -> None:
    first = DayOff(SAT, since=MON - timedelta(days=7))
    assert change_day_off(first, SUN, MON) == DayOff(SUN, since=MON, before=SAT)


def test_same_choice_changes_nothing() -> None:
    off = DayOff(SUN, since=MON, before=SAT)
    assert change_day_off(off, SUN, MON + timedelta(days=3)) is off


def test_two_changes_the_same_day_keep_the_first_previous_value() -> None:
    once = change_day_off(DayOff(SAT, since=MON - timedelta(days=7)), SUN, MON)
    assert change_day_off(once, NONE, MON) == DayOff(NONE, since=MON, before=SAT)


def test_a_second_later_change_folds_older_periods() -> None:
    once = change_day_off(DayOff(SAT, since=MON - timedelta(days=7)), SUN, MON)
    later = MON + timedelta(days=10)
    assert change_day_off(once, NONE, later) == DayOff(NONE, since=later, before=SUN)


def test_unlogged_day_off_is_auto_rest() -> None:
    start, end = _week()
    found = auto_days(start, end, end, JOINED, set(), DayOff(SAT), set())
    assert found == {date(2026, 10, 24): AutoDay(AutoKind.DAY_OFF)}


def test_moon_day_wins_over_the_day_off_and_says_so() -> None:
    start, end = _week()
    sat, wed = date(2026, 10, 24), date(2026, 10, 21)
    found = auto_days(start, end, end, JOINED, set(), DayOff(SAT), {sat, wed})
    assert found == {
        wed: AutoDay(AutoKind.MOON),
        sat: AutoDay(AutoKind.MOON, also_day_off=True),
    }


def test_logged_days_always_win() -> None:
    """Q21: practice on a moon day, 🌸 or "No practice" on the day off stay as logged."""
    start, end = _week()
    sat, wed = date(2026, 10, 24), date(2026, 10, 21)
    assert auto_days(start, end, end, JOINED, {sat, wed}, DayOff(SAT), {wed}) == {}


def test_never_chosen_or_no_fixed_day_off_gives_moon_days_only() -> None:
    start, end = _week()
    wed = date(2026, 10, 21)
    for off in (DayOff(), DayOff(NONE)):
        assert auto_days(start, end, end, JOINED, set(), off, {wed}) == {
            wed: AutoDay(AutoKind.MOON)
        }


@pytest.mark.parametrize("weekday", range(1, 8))
def test_each_weekday_can_be_the_day_off(weekday: int) -> None:
    start, end = _week()
    found = auto_days(start, end, end, JOINED, set(), DayOff(frozenset({weekday})), set())
    assert [d.isoweekday() for d in found] == [weekday]


def test_no_auto_days_after_today() -> None:
    start, end = _week()
    today = date(2026, 10, 22)  # Thursday: Saturday is still ahead
    sun = date(2026, 10, 25)
    assert auto_days(start, end, today, JOINED, set(), DayOff(SAT), {sun}) == {}


def test_a_new_account_has_no_auto_days_before_joining() -> None:
    start, end = _week()
    joined = date(2026, 10, 25)  # joined on the Sunday
    sat, sun = date(2026, 10, 24), date(2026, 10, 25)
    found = auto_days(start, end, end, joined, set(), DayOff(frozenset({6, 7})), {sat, sun})
    assert found == {sun: AutoDay(AutoKind.MOON, also_day_off=True)}


def test_history_follows_the_day_off_in_effect_on_each_date() -> None:
    start = date(2026, 10, 12)
    end = start + timedelta(days=13)
    off = DayOff(SUN, since=MON, before=SAT)
    found = auto_days(start, end, end, JOINED, set(), off, set())
    assert sorted(found) == [date(2026, 10, 17), date(2026, 10, 25)]  # old Sat, new Sun


def test_joined_is_the_local_date_of_account_creation() -> None:
    late = datetime(2026, 10, 24, 18, 30, tzinfo=UTC)  # 23:30 in Almaty (UTC+5)
    assert joined_on(late, "Asia/Almaty") == date(2026, 10, 24)
    assert joined_on(late, "Pacific/Kiritimati") == date(2026, 10, 25)
    assert joined_on(late, "Pacific/Honolulu") == date(2026, 10, 24)


def test_weekday_is_the_local_one_across_the_date_line() -> None:
    """The same instant is Saturday in Kiritimati and Friday in Honolulu: the day off
    follows each person's local date."""
    now = datetime(2026, 10, 24, 1, tzinfo=UTC)
    for zone, expected in (("Pacific/Kiritimati", True), ("Pacific/Honolulu", False)):
        today = joined_on(now, zone)
        found = auto_days(today, today, today, JOINED, set(), DayOff(SAT), set())
        assert bool(found) is expected


def test_berlin_dst_sunday_moon_day_is_one_auto_day() -> None:
    sun = date(2026, 10, 25)  # clocks go back in Berlin
    found = auto_days(sun, sun, sun, JOINED, set(), DayOff(SUN), {sun})
    assert found == {sun: AutoDay(AutoKind.MOON, also_day_off=True)}
