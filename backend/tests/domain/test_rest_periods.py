"""Rest periods (WH-01 part 2, ADR-0023): the per-kind day choices, the pause offer, the
overlap and cut rules, ending early, and the derived covered days. Pure rules, fixed dates."""

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

import pytest

from tests import rest_period_cases as cases
from tristhana.domain import rest_periods as rp
from tristhana.domain.days import DateInFuture, DayStatus
from tristhana.domain.rest_days import AutoDay, AutoKind, DayOff, auto_days
from tristhana.domain.rest_periods import (
    UNCHANGED,
    InvalidRestPeriod,
    PauseOffer,
    RestPeriod,
    check_period,
    check_restore,
    covered_days,
    cut_by_log,
    end_from,
    max_days,
    pause_offer,
    place,
)

L, K, T = DayStatus.LADIES, DayStatus.SICK, DayStatus.TRAVEL
P, R, M, N = DayStatus.PRACTICED, DayStatus.REST, DayStatus.MOON, DayStatus.SKIPPED
TODAY = date(2026, 10, 26)  # a Monday
ZONE = "Asia/Almaty"  # UTC+5
NOW = datetime(2026, 10, 26, 6, tzinfo=UTC)  # 11:00 in Almaty, Oct 26


def _d(offset: int) -> date:
    return TODAY + timedelta(days=offset)


def _p(start: int, end: int, kind: DayStatus = L) -> RestPeriod:
    return RestPeriod(_d(start), _d(end), kind)


# The per-kind day choices (owner, §11.2)


def test_pause_days_per_kind() -> None:
    assert rp.PAUSE_DAYS == {
        L: ((2, 3, 5), (4, 6, 7)),
        K: ((3, 4, 5), (2, 6, 7, 10, 14)),
        T: ((3, 4, 5), (2, 6, 7, 10, 14)),
    }
    assert frozenset({L, K, T}) == rp.PAUSABLE


@pytest.mark.parametrize(
    ("kind", "allowed"),
    [(L, {2, 3, 4, 5, 6, 7}), (K, {2, 3, 4, 5, 6, 7, 10, 14}), (T, {2, 3, 4, 5, 6, 7, 10, 14})],
)
def test_allowed_day_counts_are_exactly_both_screens(kind: DayStatus, allowed: set[int]) -> None:
    first, other = rp.PAUSE_DAYS[kind]
    assert set(first) | set(other) == allowed
    assert not set(first) & set(other)


def test_max_days_and_the_db_cap() -> None:
    assert (max_days(L), max_days(K), max_days(T)) == (7, 14, 14)
    assert rp.MAX_PERIOD_DAYS == 14


# check_period: N in the kind's set, kind pausable, start today or yesterday


@pytest.mark.parametrize(
    ("kind", "days", "end"),
    [(L, 2, 1), (L, 7, 6), (K, 14, 13), (T, 10, 9), (K, 2, 1)],
)
def test_check_period_creates_the_inclusive_range(kind: DayStatus, days: int, end: int) -> None:
    assert check_period(TODAY, days, kind, NOW, ZONE) == RestPeriod(TODAY, _d(end), kind)


def test_check_period_from_yesterday() -> None:
    assert check_period(_d(-1), 3, K, NOW, ZONE) == _p(-1, 1, K)


@pytest.mark.parametrize(
    ("kind", "days"),
    [
        (L, 10),  # 🌸 max is 7
        (L, 14),
        (L, 8),
        (K, 8),  # not offered
        (K, 15),  # over the cap
        (T, 1),  # a one-day "period" is just the day itself
        (L, 1),
        (K, 0),
        (T, -3),
    ],
)
def test_check_period_rejects_counts_outside_the_kinds_set(kind: DayStatus, days: int) -> None:
    with pytest.raises(InvalidRestPeriod):
        check_period(TODAY, days, kind, NOW, ZONE)


@pytest.mark.parametrize("kind", [R, M, P, N])
def test_check_period_rejects_kinds_that_do_not_pause(kind: DayStatus) -> None:
    with pytest.raises(InvalidRestPeriod):
        check_period(TODAY, 3, kind, NOW, ZONE)


def test_check_period_never_backfills() -> None:
    with pytest.raises(InvalidRestPeriod):
        check_period(_d(-2), 3, K, NOW, ZONE)


def test_check_period_refuses_a_future_start() -> None:
    with pytest.raises(DateInFuture):
        check_period(_d(1), 3, K, NOW, ZONE)


def test_check_period_without_a_zone_allows_the_latest_date_on_earth() -> None:
    """Provisional zone, as for logging: at 10:00 UTC it is already tomorrow in Kiritimati."""
    now = datetime(2026, 10, 26, 10, tzinfo=UTC)
    assert check_period(_d(1), 3, K, now, None) == _p(1, 3, K)
    with pytest.raises(DateInFuture):
        check_period(_d(2), 3, K, now, None)


@pytest.mark.parametrize(
    ("zone", "today"),
    [("Pacific/Kiritimati", date(2026, 10, 27)), ("Pacific/Honolulu", date(2026, 10, 26))],
)
def test_check_period_follows_the_local_date_across_the_date_line(zone: str, today: date) -> None:
    now = datetime(2026, 10, 26, 12, tzinfo=UTC)  # 02:00 Oct 27 / 02:00 Oct 26
    assert check_period(today, 3, T, now, zone).start == today
    with pytest.raises(DateInFuture):
        check_period(today + timedelta(days=1), 3, T, now, zone)
    with pytest.raises(InvalidRestPeriod):
        check_period(today - timedelta(days=2), 3, T, now, zone)


# check_restore: "keep the pause" re-checks the stored length, no-op once over


def test_check_restore_keeps_a_period_with_days_left() -> None:
    period = _p(-2, 2, K)
    assert check_restore(period, NOW, ZONE) == period


def test_check_restore_on_its_last_day_still_keeps_it() -> None:
    period = _p(-3, 0, L)
    assert check_restore(period, NOW, ZONE) == period


def test_check_restore_is_none_once_the_period_is_over() -> None:
    assert check_restore(_p(-4, -1, L), NOW, ZONE) is None


@pytest.mark.parametrize(
    "period",
    [
        RestPeriod(_d(-3), _d(4), L),  # 8 days of 🌸
        RestPeriod(_d(-3), _d(11), K),  # 15 days
        RestPeriod(_d(0), _d(0), K),  # end = start
        RestPeriod(_d(0), _d(3), R),  # not pausable
    ],
)
def test_check_restore_rejects_forged_periods(period: RestPeriod) -> None:
    with pytest.raises(InvalidRestPeriod):
        check_restore(period, NOW, ZONE)


def test_check_restore_allows_fourteen_days_of_sick() -> None:
    period = RestPeriod(_d(-3), _d(10), K)
    assert check_restore(period, NOW, ZONE) == period


# pause_offer: when "for how many days?" appears (§2 Offer)


def _offer(
    day: date = TODAY,
    status: DayStatus = L,
    prev: DayStatus | None = None,
    covering: RestPeriod | None = None,
    before: RestPeriod | None = None,
    reminders_on: bool = True,
) -> PauseOffer | None:
    return pause_offer(day, TODAY, status, prev, covering, before, reminders_on)


@pytest.mark.parametrize("kind", [L, K, T])
@pytest.mark.parametrize("day", [_d(0), _d(-1)])
def test_offer_for_today_or_yesterday_and_each_kind(day: date, kind: DayStatus) -> None:
    assert _offer(day, kind) == PauseOffer(day, kind, reminders_on=True)


def test_no_offer_when_backfilling() -> None:
    assert _offer(_d(-2)) is None
    assert _offer(_d(-30), K) is None


@pytest.mark.parametrize("status", [P, R, M, N])
def test_no_offer_for_statuses_that_do_not_pause(status: DayStatus) -> None:
    assert _offer(status=status) is None


@pytest.mark.parametrize("on", [True, False])
def test_offer_carries_the_reminders_flag(on: bool) -> None:
    offer = _offer(reminders_on=on)
    assert offer is not None
    assert offer.reminders_on is on


def test_no_offer_for_a_continuation_logged_the_day_before() -> None:
    assert _offer(prev=L) is None
    assert _offer(status=K, prev=K) is None


def test_another_kind_the_day_before_still_offers() -> None:
    assert _offer(status=L, prev=K) == PauseOffer(TODAY, L, True)
    assert _offer(status=T, prev=P) == PauseOffer(TODAY, T, True)


def test_a_pause_that_ran_out_yesterday_asks_again() -> None:
    ran_out = _p(-3, -1, L)
    assert _offer(before=ran_out) == PauseOffer(TODAY, L, True)
    # Even when the day before was also logged as that kind.
    assert _offer(prev=L, before=ran_out) == PauseOffer(TODAY, L, True)


def test_a_different_kind_that_ran_out_also_asks() -> None:
    assert _offer(status=L, before=_p(-3, -1, K)) == PauseOffer(TODAY, L, True)


def test_no_offer_on_a_covered_day_that_is_not_the_start() -> None:
    period = _p(-2, 2, L)
    assert _offer(covering=period, before=period) is None
    assert _offer(status=K, covering=period, before=period) is None


def test_a_re_tap_on_the_start_day_may_choose_again() -> None:
    period = _p(0, 4, L)
    assert _offer(covering=period) == PauseOffer(TODAY, L, True)


def test_a_corrected_kind_on_the_start_day_may_choose_again() -> None:
    period = _p(-1, 3, K)
    assert _offer(_d(-1), L, covering=period) == PauseOffer(_d(-1), L, True)


# place: a new period replaces what it overlaps (ends earlier ones, removes later ones)


def test_place_ends_an_earlier_period_the_day_before() -> None:
    earlier = _p(-4, 2, K)
    placement = place(_p(0, 2, L), [earlier])
    assert placement.ended == {_d(-4): _d(-1)}
    assert set(placement.removed) == set()


def test_place_removes_an_earlier_period_left_with_only_its_start() -> None:
    earlier = _p(-1, 3, K)
    placement = place(_p(0, 4, L), [earlier])
    assert set(placement.removed) == {_d(-1)}
    assert placement.ended == {}


def test_place_removes_periods_starting_inside_the_new_range() -> None:
    inside, later = _p(2, 5, T), _p(6, 9, T)
    placement = place(_p(0, 3, K), [inside, later])
    assert set(placement.removed) == {_d(2)}
    assert placement.ended == {}  # `later` starts after the new end: untouched


def test_place_leaves_adjacent_and_older_periods_alone() -> None:
    adjacent, older = _p(-3, -1, L), _p(-20, -15, K)
    placement = place(_p(0, 4, L), [adjacent, older])
    assert set(placement.removed) == set()
    assert placement.ended == {}


def test_place_never_merges_with_an_adjacent_same_kind_period() -> None:
    """A pause that ran out is followed by a new adjacent period, not extended."""
    placement = place(_p(0, 2, L), [_p(-3, -1, L)])
    assert placement.ended == {}


# cut_by_log: only 🧘 Practiced cuts; clearing the start day removes; others change one day


def test_practiced_on_the_start_day_removes_the_period() -> None:
    assert cut_by_log(_p(0, 4), _d(0), P) is None


def test_practiced_in_the_middle_ends_it_the_day_before() -> None:
    assert cut_by_log(_p(-3, 3), _d(0), P) == _p(-3, -1)


def test_practiced_on_the_last_day_ends_it_the_day_before() -> None:
    assert cut_by_log(_p(-3, 0), _d(0), P) == _p(-3, -1)


def test_practiced_on_the_second_day_leaves_nothing_but_the_start() -> None:
    """A period is at least two days; the start day alone is just its logged day."""
    assert cut_by_log(_p(-1, 3), _d(0), P) is None


@pytest.mark.parametrize("status", [N, R, M, L, K, T])
@pytest.mark.parametrize("day", [-3, 0, 3])
def test_no_practice_and_rest_like_statuses_change_only_their_day(
    status: DayStatus, day: int
) -> None:
    assert cut_by_log(_p(-3, 3, K), _d(day), status) is UNCHANGED


def test_clearing_the_start_day_removes_the_period() -> None:
    assert cut_by_log(_p(0, 4), _d(0), None) is None


def test_clearing_a_later_day_shows_the_period_again() -> None:
    assert cut_by_log(_p(-2, 4), _d(1), None) is UNCHANGED


def test_a_log_outside_the_period_changes_nothing() -> None:
    assert cut_by_log(_p(-2, 1), _d(2), P) is UNCHANGED
    assert cut_by_log(_p(-2, 1), _d(-3), P) is UNCHANGED


def test_cut_rules_are_the_same_for_every_kind() -> None:
    for kind in (L, K, T):
        assert cut_by_log(_p(-3, 3, kind), _d(0), P) == _p(-3, -1, kind)


# end_from: "End the pause" / "End early" stops covering today and later


def test_end_on_the_start_day_removes_it() -> None:
    assert end_from(_p(0, 4), TODAY) is None


def test_end_on_the_second_day_removes_it() -> None:
    assert end_from(_p(-1, 4), TODAY) is None


def test_end_in_the_middle_keeps_the_past_days() -> None:
    assert end_from(_p(-2, 4, T), TODAY) == _p(-2, -1, T)


def test_end_after_it_ran_out_changes_nothing() -> None:
    assert end_from(_p(-5, -2, K), TODAY) == _p(-5, -2, K)


# covered_days: logged > period > moon > day off; only up to today


def test_covered_days_are_unlogged_days_up_to_today() -> None:
    covered = covered_days([_p(-2, 3, L)], _d(-7), _d(7), TODAY, {_d(-2)})
    assert covered == {_d(-1): L, _d(0): L}  # the origin is logged; no future days


def test_covered_days_are_clipped_to_the_window() -> None:
    covered = covered_days([_p(-4, 0, K)], _d(-1), _d(0), TODAY, set())
    assert covered == {_d(-1): K, _d(0): K}


def test_a_logged_day_inside_wins() -> None:
    covered = covered_days([_p(-3, 0, T)], _d(-3), _d(0), TODAY, {_d(-3), _d(-1)})
    assert covered == {_d(-2): T, _d(0): T}


def test_several_periods_keep_their_own_kind() -> None:
    covered = covered_days([_p(-6, -5, K), _p(-2, -1, L)], _d(-7), _d(0), TODAY, set())
    assert covered == {_d(-6): K, _d(-5): K, _d(-2): L, _d(-1): L}


def test_a_period_wins_over_a_moon_day_and_the_day_off() -> None:
    """Calendar days: a moon day or the day off inside a period is one of its N days."""
    period = _p(-3, 0, L)  # Fri .. Mon
    sat, sun = _d(-2), _d(-1)
    covered = covered_days([period], _d(-6), _d(0), TODAY, set())
    found = auto_days(
        _d(-6),
        _d(0),
        TODAY,
        date(2026, 1, 1),
        set(),
        DayOff(frozenset({6})),
        {sun},
        covered=covered.keys(),
    )
    assert (covered[sat], covered[sun]) == (L, L)
    assert found == {}  # the only Saturday and moon day in the window are covered


def test_auto_days_outside_a_period_are_untouched() -> None:
    covered = covered_days([_p(-1, 0, K)], _d(-9), _d(0), TODAY, set())
    found = auto_days(
        _d(-9),
        _d(0),
        TODAY,
        date(2026, 1, 1),
        set(),
        DayOff(frozenset({6})),
        {_d(-5)},
        covered=covered.keys(),
    )
    assert found == {
        _d(-9): AutoDay(AutoKind.DAY_OFF),  # Sat Oct 17
        _d(-5): AutoDay(AutoKind.MOON),
        _d(-2): AutoDay(AutoKind.DAY_OFF),  # Sat Oct 24
    }


def test_a_pause_across_the_berlin_dst_change_counts_calendar_days() -> None:
    """Oct 25, 2026: clocks go back in Berlin; a 3-day pause still covers 3 dates."""
    now = datetime(2026, 10, 24, 8, tzinfo=UTC)
    period = check_period(date(2026, 10, 24), 3, T, now, "Europe/Berlin")
    assert period == RestPeriod(date(2026, 10, 24), date(2026, 10, 26), T)
    covered = covered_days([period], period.start, period.end, date(2026, 10, 26), set())
    assert sorted(covered) == [date(2026, 10, 24), date(2026, 10, 25), date(2026, 10, 26)]


# Parity with the SQL (the same table runs against Postgres in test_db_rest_periods.py)


def _after_place(existing: tuple[RestPeriod, ...], new: RestPeriod) -> list[RestPeriod]:
    placement = place(new, existing)
    kept = {q.start: q for q in existing if q.start not in placement.removed}
    for start, end in placement.ended.items():
        kept[start] = replace(kept[start], end=end)
    kept[new.start] = new
    return sorted(kept.values(), key=lambda q: q.start)


@pytest.mark.parametrize("case", cases.PLACE_CASES, ids=lambda c: c.id)
def test_place_parity_table(case: cases.PlaceCase) -> None:
    assert _after_place(case.existing, case.new) == list(case.expected)


@pytest.mark.parametrize("case", cases.CUT_CASES, ids=lambda c: c.id)
def test_cut_parity_table(case: cases.CutCase) -> None:
    result = cut_by_log(case.period, cases.d(case.day), case.status)
    after = [case.period] if result is UNCHANGED else [] if result is None else [result]
    assert after == list(case.expected)
