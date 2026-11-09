"""GM-02 badges (spec §3, §9): each rule kind at n-1 / n / n+1, the Mandala run over every rest
kind, Return's gap, early starts, moon rest days (🌸 indistinguishable by construction), the
asana badges from the history, and `validate`."""

from collections.abc import Iterable, Mapping
from datetime import date, time, timedelta
from functools import cache

import pytest

from tests.domain.test_practice import catalog
from tristhana.domain.badges import (
    MAX_BADGES,
    BadgeDef,
    BadgeFacts,
    Earned,
    Group,
    InvalidBadges,
    RuleKind,
    earned,
    validate,
)
from tristhana.domain.days import DayStatus
from tristhana.domain.practice import PracticeContext
from tristhana.domain.progression import EventKind, Marker, Position, ProgressionEvent, Track
from tristhana.domain.rest_days import NEVER_CHOSEN, DayOff

P, R, M, S, T, N = (
    DayStatus.PRACTICED,
    DayStatus.REST,  # 😌 and 🌸 alike: the plain column never says which
    DayStatus.MOON,
    DayStatus.SICK,
    DayStatus.TRAVEL,
    DayStatus.SKIPPED,
)
START = date(2026, 1, 5)  # a Monday
TODAY = date(2026, 11, 9)
JOINED = date(2020, 1, 1)
SUNDAY_OFF = DayOff(frozenset({7}), JOINED)


@cache
def track() -> Track:
    return Track(catalog())


def day(n: int) -> date:
    return START + timedelta(days=n)


def b(key: str, rule: RuleKind, group: Group = Group.PRACTICE, **params: object) -> BadgeDef:
    return BadgeDef(key, group, "*", rule, **params)  # type: ignore[arg-type]


def run_of(statuses: Iterable[DayStatus | None], start: date = START) -> dict[date, DayStatus]:
    """Consecutive dates from `start`; None = unlogged."""
    return {start + timedelta(days=i): s for i, s in enumerate(statuses) if s is not None}


def facts(logged: Mapping[date, DayStatus] | None = None, **rest: object) -> BadgeFacts:
    return BadgeFacts(logged=logged or {}, **rest)  # type: ignore[arg-type]


def shown(
    defs: Iterable[BadgeDef],
    f: BadgeFacts,
    *,
    off: DayOff = NEVER_CHOSEN,
    joined: date = JOINED,
    today: date = TODAY,
) -> dict[str, Earned]:
    return {e.key: e for e in earned(tuple(defs), f, track(), off=off, joined=joined, today=today)}


# --- practices --------------------------------------------------------------------------------


@pytest.mark.parametrize(("logged", "expected"), [(8, None), (9, 8), (10, 8)])
def test_practices_shows_the_nth_practised_date(logged: int, expected: int | None) -> None:
    nava = b("nava", RuleKind.PRACTICES, count=9)
    # A rest day between each practice: the count is of practices, never of days.
    f = facts({day(2 * i): P for i in range(logged)} | {day(2 * i + 1): R for i in range(10)})

    found = shown([nava], f)

    assert found.get("nava") == (
        None if expected is None else Earned(nava, day(2 * expected), at_record_start=False)
    )


def test_a_kept_count_stays_without_a_date_but_108_does_not() -> None:
    shatam = b("shatam", RuleKind.PRACTICES, count=100)
    count_108 = b("count-108", RuleKind.PRACTICES, count=108)
    f = facts({day(0): P}, kept_counts=frozenset({100}))

    found = shown([shatam, count_108], f)

    assert found == {"shatam": Earned(shatam, None, at_record_start=False)}


def test_rest_and_no_practice_never_count_as_practices() -> None:
    ekam = b("ekam", RuleKind.PRACTICES, count=1)

    assert shown([ekam], facts(run_of([R, M, S, T, N]))) == {}
    assert shown([ekam], facts(run_of([R, N, P])))["ekam"].on == day(2)


# --- run (Mandala) ----------------------------------------------------------------------------

MANDALA = b("mandala", RuleKind.RUN, count=40)


def _mandala_days() -> tuple[dict[date, DayStatus], frozenset[date], frozenset[date], date]:
    """40 practices with every rest kind between them: logged 🌙 / 😌 / 🌸 (REST) / sick /
    travel, an unlogged moon date (auto-🌙), an unlogged Sunday (auto day off) and a date
    covered by a rest period. Returns (logged, moon, covered, 40th practice)."""
    logged: dict[date, DayStatus] = {}
    moon: set[date] = set()
    covered: set[date] = set()
    gaps = {5: M, 10: R, 15: S, 20: T, 25: "moon", 30: "period"}
    current, practices, last = START, 0, START
    while practices < 40:
        gap = gaps.pop(practices, None)
        if isinstance(gap, DayStatus):
            logged[current] = gap
        elif gap == "moon":
            moon.add(current)
        elif gap == "period":
            covered.add(current)
        elif current.isoweekday() == 7:
            pass  # an unlogged Sunday: the day off
        else:
            logged[current] = P
            practices += 1
            last = current
        current += timedelta(days=1)
    return logged, frozenset(moon), frozenset(covered), last


def test_mandala_is_40_practices_with_every_rest_kind_transparent() -> None:
    logged, moon, covered, fortieth = _mandala_days()

    found = shown([MANDALA], facts(logged, moon=moon, covered=covered), off=SUNDAY_OFF)

    assert found["mandala"] == Earned(MANDALA, fortieth, at_record_start=False)


def test_39_practices_are_not_a_mandala() -> None:
    logged, moon, covered, fortieth = _mandala_days()
    del logged[fortieth]

    assert shown([MANDALA], facts(logged, moon=moon, covered=covered), off=SUNDAY_OFF) == {}


def test_no_practice_ends_the_run() -> None:
    f = facts(run_of([P] * 38 + [N] + [P] * 2))  # 41 practices, never 40 in a row

    assert shown([MANDALA], f) == {}


def test_one_unlogged_weekday_ends_the_run_no_seven_day_bridge() -> None:
    f = facts(run_of([P] * 20 + [None] + [P] * 20))  # ST-01 would bridge it

    assert shown([MANDALA], f) == {}


def test_after_a_break_the_run_starts_again() -> None:
    f = facts(run_of([P] * 10 + [N] + [P] * 40))

    assert shown([MANDALA], f)["mandala"].on == day(50)


def test_an_unlogged_today_never_ends_the_run() -> None:
    f = facts(run_of([P] * 40))
    today = day(40)  # unlogged

    assert shown([MANDALA], f, today=today)["mandala"].on == day(39)


def test_an_unlogged_day_off_before_joining_ends_the_run() -> None:
    logged = {d: P for d in (day(i) for i in range(60)) if d.isoweekday() != 7}
    joined = day(30)

    assert shown([MANDALA], facts(logged), off=SUNDAY_OFF, joined=joined) == {}
    # Joined earlier: every Sunday is the day off, so the run holds.
    assert "mandala" in shown([MANDALA], facts(logged), off=SUNDAY_OFF, joined=START)


def test_a_log_wins_over_a_rest_period() -> None:
    f = facts(run_of([P] * 20 + [N] + [P] * 20), covered=frozenset({day(20)}))

    assert shown([MANDALA], f) == {}


# --- context, early start ---------------------------------------------------------------------


@pytest.mark.parametrize(("count", "expected"), [(9, None), (10, 9), (11, 9)])
def test_context_shows_the_nth_led_date(count: int, expected: int | None) -> None:
    led = b("led-by-the-count", RuleKind.CONTEXT, context=PracticeContext.LED, count=10)
    own = b("self-practice", RuleKind.CONTEXT, context=PracticeContext.SELF, count=2)
    f = facts(
        {day(i): P for i in range(30)},
        led=tuple(day(i) for i in range(count)),
        self_=(day(20),),
    )

    found = shown([led, own], f)

    assert found.get("led-by-the-count") == (
        None if expected is None else Earned(led, day(expected), at_record_start=False)
    )
    assert "self-practice" not in found


BEFORE_DAWN = b("before-dawn", RuleKind.EARLY_START, before=time(6), count=10)


def test_early_start_counts_strictly_before_the_threshold() -> None:
    starts = (*((day(i), time(5, 59)) for i in range(9)), (day(9), time(6)))

    logged = {day(i): P for i in range(11)}

    assert shown([BEFORE_DAWN], facts(logged, starts=starts)) == {}

    found = shown([BEFORE_DAWN], facts(logged, starts=(*starts, (day(10), time(5, 30)))))
    assert found["before-dawn"].on == day(10)


# --- moon_rest --------------------------------------------------------------------------------


def test_moon_rest_counts_every_rest_kind_on_a_moon_date() -> None:
    logged = {day(0): M, day(1): R, day(2): S, day(3): T, day(4): P, day(5): N}
    moon = frozenset(day(i) for i in range(10))  # day(6) covered, day(7..9) unlogged
    seven = b("rest-is-practice", RuleKind.MOON_REST, count=7)
    eight = b("rest-is-practice", RuleKind.MOON_REST, count=8)
    f = facts(logged, moon=moon, covered=frozenset({day(6)}))

    # 🌙 😌/🌸 sick travel + covered + auto-🌙 on day(8..9) = 7; day(7) is before joining.
    assert shown([seven], f, joined=day(8))["rest-is-practice"].on == day(9)
    assert shown([eight], f, joined=day(8)) == {}


def test_moon_rest_never_counts_a_rest_day_off_the_moon() -> None:
    once = b("rest-is-practice", RuleKind.MOON_REST, count=1)

    assert shown([once], facts({day(0): R, day(1): M}, moon=frozenset[date]())) == {}


def test_ladies_and_rest_are_one_plain_status() -> None:
    """🌸 is stored as REST in the plain column, so a sealed 🌸 and a 😌 give one result."""
    once = b("rest-is-practice", RuleKind.MOON_REST, count=1)
    f = facts({day(0): R}, moon=frozenset({day(0)}))

    assert shown([once], f)["rest-is-practice"].on == day(0)


# --- return -----------------------------------------------------------------------------------

RETURN = b("return", RuleKind.RETURN, days=14)


@pytest.mark.parametrize(("empty", "earned_on"), [(13, None), (14, 15), (15, 16)])
def test_return_needs_14_days_with_no_practice(empty: int, earned_on: int | None) -> None:
    # Rest logged in the gap changes nothing: Return reads practised dates only.
    gap = {day(i): R for i in range(1, empty + 1)}
    f = facts({day(0): P, day(empty + 1): P} | gap)

    found = shown([RETURN], f)

    assert (found["return"].on if "return" in found else None) == (
        None if earned_on is None else day(earned_on)
    )


def test_the_first_practice_is_never_a_return() -> None:
    assert shown([RETURN], facts({day(100): P})) == {}


# --- asana badges -----------------------------------------------------------------------------

ASANAS = (
    b("yoga-chikitsa", RuleKind.SERIES_COMPLETE, Group.ASANAS, target=Position("primary")),
    b("nadi-shodhana", RuleKind.SERIES_BEGINS, Group.ASANAS, target=Position("intermediate")),
    b(
        "supta-kurmasana",
        RuleKind.STOP,
        Group.ASANAS,
        target=Position("primary", "supta-kurmasana"),
    ),
    b("kapotasana", RuleKind.STOP, Group.ASANAS, target=Position("intermediate", "kapotasana-b")),
    b(
        "karandavasana",
        RuleKind.STOP,
        Group.ASANAS,
        target=Position("intermediate", "karandavasana"),
    ),
    b("tic-tacs", RuleKind.ITEM, Group.ASANAS, item="viparita-chakrasana"),
)


def ev(
    i: int,
    kind: EventKind,
    on: date,
    after: Position | None = None,
    item: str | None = None,
    by: Marker = Marker.SELF,
) -> ProgressionEvent:
    return ProgressionEvent(i, kind, on, after=after, item=item, by=by)


def test_a_start_past_the_stops_shows_them_from_the_record_start() -> None:
    events = (ev(1, EventKind.START, day(0), Position("intermediate", "kapotasana-b")),)

    found = shown(ASANAS, facts(events=events))

    assert set(found) == {"yoga-chikitsa", "nadi-shodhana", "supta-kurmasana", "kapotasana"}
    assert all(e.at_record_start and e.on == day(0) for e in found.values())


def test_a_jump_across_stops_shows_each_on_the_give_date() -> None:
    events = (
        ev(1, EventKind.START, day(0), Position("primary", "navasana")),
        ev(2, EventKind.GIVEN, day(9), Position("intermediate", "pasasana"), by=Marker.TEACHER),
    )

    found = shown(ASANAS, facts(events=events))

    assert set(found) == {"yoga-chikitsa", "nadi-shodhana", "supta-kurmasana"}
    assert {(e.on, e.at_record_start) for e in found.values()} == {(day(9), False)}


def test_kapotasana_comes_only_at_the_b_stop() -> None:
    before_b = (ev(1, EventKind.START, day(0), Position("intermediate", "laghu-vajrasana")),)
    at_b = (*before_b, ev(2, EventKind.GIVEN, day(3), Position("intermediate", "kapotasana-b")))

    assert "kapotasana" not in shown(ASANAS, facts(events=before_b))
    assert shown(ASANAS, facts(events=at_b))["kapotasana"].on == day(3)


def test_a_change_down_keeps_the_badge_and_stale_keys_are_ignored() -> None:
    events = (
        ev(1, EventKind.START, day(0), Position("primary", "nope")),  # stale
        ev(2, EventKind.CHANGED, day(1), Position("primary", "kurmasana")),
        ev(3, EventKind.GIVEN, day(2), Position("primary", "supta-kurmasana")),
        ev(4, EventKind.CHANGED, day(5), Position("primary", "navasana")),  # an injury
    )

    found = shown(ASANAS, facts({day(3): P}, events=events))  # practised at it before

    assert set(found) == {"supta-kurmasana"}
    assert found["supta-kurmasana"] == Earned(ASANAS[2], day(2), at_record_start=False)


def test_an_item_stays_after_removal() -> None:
    events = (
        ev(1, EventKind.START, day(0), Position("primary", "navasana")),
        ev(2, EventKind.ITEM_GIVEN, day(4), item="viparita-chakrasana"),
        ev(3, EventKind.ITEM_REMOVED, day(6), item="viparita-chakrasana"),
        ev(4, EventKind.ITEM_GIVEN, day(8), item="viparita-chakrasana"),
    )

    assert shown(ASANAS, facts({day(5): P}, events=events))["tic-tacs"].on == day(4)


# Quick corrections (owner, 2026-11-09): a ✏️ Change below the stop on the same day, or before
# any practice was logged after the give, takes the badge back; a real step back keeps it.

SUPTA = Position("primary", "supta-kurmasana")
NAVASANA = Position("primary", "navasana")


def _corrected(change_on: int, logged: dict[date, DayStatus], by: Marker = Marker.SELF):
    events = (
        ev(1, EventKind.START, day(0), NAVASANA),
        ev(2, EventKind.GIVEN, day(2), SUPTA, by=by),
        ev(3, EventKind.CHANGED, day(change_on), NAVASANA),
    )
    return shown(ASANAS, facts({day(0): P, day(1): P} | logged, events=events))


def test_a_same_day_correction_gives_no_badge() -> None:
    assert "supta-kurmasana" not in _corrected(2, {day(2): P})


def test_a_correction_before_any_practice_at_it_gives_no_badge() -> None:
    # Practised on the give's day (before the give) and rested since: still a mis-tap.
    assert "supta-kurmasana" not in _corrected(6, {day(2): P, day(3): R, day(4): N})


def test_a_correction_after_a_practised_day_keeps_the_badge() -> None:
    found = _corrected(6, {day(4): P})

    assert found["supta-kurmasana"].on == day(2)


def test_a_teachers_mark_corrected_by_the_student_follows_the_same_rules() -> None:
    assert "supta-kurmasana" not in _corrected(3, {}, by=Marker.TEACHER)
    assert _corrected(5, {day(3): P}, by=Marker.TEACHER)["supta-kurmasana"].on == day(2)


def test_a_correction_still_past_the_stop_keeps_the_first_date() -> None:
    events = (
        ev(1, EventKind.START, day(0), Position("primary", "garbha-pindasana")),
        ev(2, EventKind.CHANGED, day(0), SUPTA),  # one stop back, same day: still past it
    )

    assert shown(ASANAS, facts(events=events))["supta-kurmasana"] == Earned(
        ASANAS[2], day(0), at_record_start=True
    )


def test_a_later_give_counts_after_a_quick_correction() -> None:
    events = (
        ev(1, EventKind.START, day(0), SUPTA),
        ev(2, EventKind.CHANGED, day(0), NAVASANA),
        ev(3, EventKind.GIVEN, day(9), SUPTA),
    )

    assert shown(ASANAS, facts({day(4): P}, events=events))["supta-kurmasana"] == Earned(
        ASANAS[2], day(9), at_record_start=False
    )


def test_an_item_removed_quickly_gives_no_badge() -> None:
    events = (
        ev(1, EventKind.START, day(0), NAVASANA),
        ev(2, EventKind.ITEM_GIVEN, day(4), item="viparita-chakrasana"),
        ev(3, EventKind.ITEM_REMOVED, day(4), item="viparita-chakrasana"),
    )

    assert "tic-tacs" not in shown(ASANAS, facts({day(4): P}, events=events))


def test_led_self_and_early_count_only_on_practised_days() -> None:
    """A stale practice row on a day now logged as rest never counts."""
    led = b("led", RuleKind.CONTEXT, context=PracticeContext.LED, count=2)
    own = b("own", RuleKind.CONTEXT, context=PracticeContext.SELF, count=1)
    dawn = b("dawn", RuleKind.EARLY_START, before=time(6), count=2)
    f = facts(
        {day(0): P, day(1): R, day(2): P},
        led=(day(0), day(1)),
        self_=(day(1),),
        starts=((day(0), time(5)), (day(1), time(5))),
    )

    assert shown([led, own, dawn], f) == {}


def test_output_follows_the_definitions_order() -> None:
    defs = (b("nava", RuleKind.PRACTICES, count=2), b("ekam", RuleKind.PRACTICES, count=1))
    found = earned(defs, facts({day(0): P, day(1): P}), track(), off=NEVER_CHOSEN,
                   joined=JOINED, today=TODAY)  # fmt: skip

    assert [e.key for e in found] == ["nava", "ekam"]


def test_nothing_logged_shows_nothing() -> None:
    from tristhana.domain.badges import RuleKind as K

    defs = [
        b("a", K.PRACTICES, count=1),
        b("b", K.RUN, count=1),
        b("c", K.MOON_REST, count=1),
        b("d", K.RETURN, days=1),
    ]
    assert shown(defs, facts(moon=frozenset({TODAY - timedelta(days=1)}))) == {}


# --- validate ---------------------------------------------------------------------------------


def test_valid_definitions_pass() -> None:
    validate(
        (
            b("ekam", RuleKind.PRACTICES, count=1),
            b("mandala", RuleKind.RUN, count=40),
            BEFORE_DAWN,
            b("led", RuleKind.CONTEXT, context=PracticeContext.LED, count=10),
            b("rest", RuleKind.MOON_REST, count=10),
            RETURN,
            *ASANAS,
        ),
        track(),
    )


@pytest.mark.parametrize(
    "bad",
    [
        (b("x", RuleKind.PRACTICES),),  # no count
        (b("x", RuleKind.PRACTICES, count=0),),
        (b("x", RuleKind.PRACTICES, count=1, days=3),),  # a parameter it doesn't use
        (b("x", RuleKind.RETURN),),
        (b("x", RuleKind.EARLY_START, count=10),),  # no `before`
        (b("x", RuleKind.CONTEXT, count=10),),
        (b("x", RuleKind.CONTEXT, context=PracticeContext.MYSORE, count=10),),
        (b("x", RuleKind.SERIES_COMPLETE, Group.ASANAS, target=Position("nope")),),
        (b("x", RuleKind.SERIES_BEGINS, Group.ASANAS, target=Position("advanced-c")),),
        (b("x", RuleKind.STOP, Group.ASANAS, target=Position("intermediate", "kapotasana-a")),),
        (b("x", RuleKind.STOP, Group.ASANAS, target=Position("intermediate")),),
        (b("x", RuleKind.ITEM, Group.ASANAS, item="karandavasana"),),
        (b("x", RuleKind.ITEM, Group.ASANAS),),
        (b("x", RuleKind.PRACTICES, count=1), b("x", RuleKind.PRACTICES, count=2)),
        (b("Bad Key", RuleKind.PRACTICES, count=1),),
        tuple(b(f"k{i}", RuleKind.PRACTICES, count=i + 1) for i in range(MAX_BADGES + 1)),
    ],
)
def test_validate_rejects(bad: tuple[BadgeDef, ...]) -> None:
    with pytest.raises(InvalidBadges):
        validate(bad, track())
