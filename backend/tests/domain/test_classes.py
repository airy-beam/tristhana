"""Classes, the pure rules (SC-02 spec §3, §7, §8; ADR-0034): the weekly rule as columns
(`rule_dates`, `check_series`, `to_rrule`), wall clock + IANA zone to a UTC instant across DST
(`wall_to_utc`), and read-time expansion (`expand`) with its precedence: staff override >
closure > moon (per policy, Q117) > swap (Q125); kshaya dates as stored; 1:1 for staff only.

Shapes the spec leaves open, assumed here (adjust with the module, in one place: the helpers
`_series`, `_ov`, `_expand`):

- `OverrideStatus(StrEnum)`: CANCELLED = "cancelled", HELD = "held";
- `Reason(StrEnum)`: MOON = "moon", CLOSURE = "closure", CANCELLED = "cancelled";
- `Closure(id, start, end)` (inclusive), `Swap(from_date, to_date)`;
- `check_series(series) -> ClassSeries` takes a whole `ClassSeries`;
- `expand(..., overrides: Mapping[tuple[UUID, date], Override], ...)` keyed by the table's PK.
"""

import itertools
import re
from collections.abc import Iterable, Mapping
from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest

from tristhana.domain.classes import (
    CLOSURE_MAX,
    HELD_ON_MOON,
    HORIZON,
    MAX_CLASSES,
    MAX_FUTURE_CLOSURES,
    MAX_FUTURE_SWAPS,
    MOVE_MAX,
    SWAP_MAX,
    WINDOW_MAX,
    ClassSeries,
    ClassType,
    Closure,
    InvalidClass,
    MoonPolicy,
    Occurrence,
    Override,
    OverrideStatus,
    Reason,
    Swap,
    check_series,
    check_swap,
    expand,
    rule_dates,
    to_rrule,
    wall_to_utc,
)

MYSORE, LED, PRIVATE = ClassType.MYSORE, ClassType.LED, ClassType.PRIVATE
CONFERENCE, PRANAYAMA, CHANTING, WORKSHOP = (
    ClassType.CONFERENCE,
    ClassType.PRANAYAMA,
    ClassType.CHANTING,
    ClassType.WORKSHOP,
)
CLOSED, PRANAYAMA_ONLY, OPEN = MoonPolicy.CLOSED, MoonPolicy.PRANAYAMA, MoonPolicy.OPEN
MON, TUE, WED, THU, FRI, SAT, SUN = range(1, 8)
MON_FRI = frozenset({MON, TUE, WED, THU, FRI})
EVERY_DAY = frozenset(range(1, 8))
ALMATY, BERLIN = "Asia/Almaty", "Europe/Berlin"
ANNA, BORIS, DANA = UUID(int=0xA1), UUID(int=0xA2), UUID(int=0xA3)
_ids = itertools.count(1)

# November 2026: Mon 2, Mon 9, Fri 13 (a moon day in these tests), Sat 14 (the day off).
NOV = {d: date(2026, 11, d) for d in range(1, 31)}
MOON_FRI = NOV[13]


def _series(
    type: ClassType = MYSORE,
    *,
    weekdays: Iterable[int] = MON_FRI,
    start: time = time(6, 0),
    minutes: int = 210,
    starts_on: date = NOV[2],
    ends_on: date | None = None,
    every: int = 1,
    zone: str = ALMATY,
    teacher: UUID | None = ANNA,
    online: bool = False,
    title: str | None = None,
    id: UUID | None = None,
) -> ClassSeries:
    return ClassSeries(
        id=id or UUID(int=next(_ids)),
        type=type,
        title=title,
        online=online,
        zone=zone,
        teacher_id=teacher,
        start=start,
        minutes=minutes,
        weekdays=frozenset(weekdays),
        every=every,
        starts_on=starts_on,
        ends_on=ends_on,
    )


def _ov(
    on: date,
    status: OverrideStatus | None = None,
    *,
    moved_to: date | None = None,
    start: time | None = None,
    minutes: int | None = None,
    teacher: UUID | None = None,
) -> Override:
    return Override(
        on_date=on,
        status=status,
        moved_to=moved_to,
        start=start,
        minutes=minutes,
        teacher_id=teacher,
    )


def _expand(
    series: Iterable[ClassSeries],
    start: date,
    end: date,
    *,
    overrides: Mapping[tuple[UUID, date], Override] | None = None,
    closures: Iterable[Closure] = (),
    swaps: Iterable[Swap] = (),
    moon: Iterable[date] = (),
    policy: MoonPolicy = CLOSED,
    staff_only: bool = True,
) -> list[Occurrence]:
    return expand(
        list(series),
        dict(overrides or {}),
        list(closures),
        list(swaps),
        frozenset(moon),
        policy,
        start,
        end,
        staff_only,
    )


def _closure(start: date, end: date) -> Closure:
    return Closure(UUID(int=next(_ids)), start, end)


def _one(occurrences: list[Occurrence], key: date, series: ClassSeries) -> Occurrence:
    [found] = [o for o in occurrences if o.class_id == series.id and o.key == key]
    return found


def _utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=UTC)  # type: ignore[misc]


# The numbers


def test_the_spec_numbers() -> None:
    assert (MAX_CLASSES, MAX_FUTURE_CLOSURES, MAX_FUTURE_SWAPS) == (40, 20, 20)
    assert (WINDOW_MAX, HORIZON) == (31, 365)
    assert (MOVE_MAX, SWAP_MAX, CLOSURE_MAX) == (6, 6, 92)


def test_the_seven_class_types_and_their_stored_values() -> None:
    assert {t.value for t in ClassType} == {
        "mysore",
        "led",
        "private",
        "conference",
        "pranayama",
        "chanting",
        "workshop",
    }


def test_the_moon_policies() -> None:
    assert {p.value for p in MoonPolicy} == {"closed", "pranayama", "open"}


def test_held_on_moon_is_the_owners_q117_table() -> None:
    assert set(HELD_ON_MOON[CLOSED]) == set()
    assert set(HELD_ON_MOON[PRANAYAMA_ONLY]) == {PRANAYAMA, CONFERENCE, CHANTING}
    assert set(HELD_ON_MOON[OPEN]) == set(ClassType)
    assert LED not in HELD_ON_MOON[PRANAYAMA_ONLY]  # Led is asana practice


# rule_dates


@pytest.mark.parametrize(
    ("every", "expected"),
    [
        # From Wed 4 Nov (ISO week of Mon 2 Nov), Mon + Wed; Mon 2 is before starts_on.
        (1, [4, 9, 11, 16, 18, 23, 25, 30]),
        (2, [4, 16, 18, 30]),
        (3, [4, 23, 25]),
        (4, [4, 30]),
    ],
)
def test_every_n_weeks_counts_iso_weeks_from_the_start_week(
    every: int, expected: list[int]
) -> None:
    s = _series(weekdays={MON, WED}, starts_on=NOV[4], every=every)

    assert list(rule_dates(s, NOV[1], NOV[30])) == [NOV[d] for d in expected]


def test_every_two_weeks_keeps_its_phase_in_a_later_window() -> None:
    """The anchor is starts_on's week, not the window's first week."""
    s = _series(weekdays={MON}, starts_on=NOV[2], every=2)

    assert list(rule_dates(s, NOV[10], NOV[30])) == [NOV[16], NOV[30]]


def test_a_week_starts_on_monday_for_the_anchor() -> None:
    """Sun 8 Nov is in the ISO week of Mon 2 Nov: every 2 weeks from it skips Sun 15."""
    s = _series(weekdays={SUN}, starts_on=NOV[8], every=2)

    assert list(rule_dates(s, NOV[1], NOV[30])) == [NOV[8], NOV[22]]


def test_a_one_off_is_its_start_date_only() -> None:
    s = _series(CONFERENCE, weekdays=(), starts_on=NOV[15])

    assert list(rule_dates(s, NOV[1], NOV[30])) == [NOV[15]]
    assert list(rule_dates(s, NOV[16], NOV[30])) == []


def test_the_until_bound_is_inclusive() -> None:
    s = _series(weekdays={MON}, starts_on=NOV[2], ends_on=NOV[16])

    assert list(rule_dates(s, NOV[1], NOV[30])) == [NOV[2], NOV[9], NOV[16]]


def test_the_window_bounds_are_inclusive_and_starts_on_bounds_the_rule() -> None:
    s = _series(weekdays=EVERY_DAY, starts_on=NOV[10])

    assert list(rule_dates(s, NOV[8], NOV[12])) == [NOV[10], NOV[11], NOV[12]]


@pytest.mark.parametrize(("start", "end"), [(NOV[10], NOV[9]), (NOV[20], NOV[1])])
def test_an_empty_window_gives_nothing(start: date, end: date) -> None:
    assert list(rule_dates(_series(weekdays=EVERY_DAY), start, end)) == []


def test_a_window_entirely_before_the_series_gives_nothing() -> None:
    assert list(rule_dates(_series(starts_on=NOV[20]), NOV[1], NOV[19])) == []


# check_series


def test_a_class_ending_exactly_at_midnight_is_fine() -> None:
    s = _series(LED, start=time(22, 0), minutes=120)

    assert check_series(s) == s


@pytest.mark.parametrize(
    "bad",
    [
        _series(LED, start=time(22, 0), minutes=121),  # 24:01
        _series(LED, start=time(23, 59), minutes=15),
        _series(minutes=14),
        _series(minutes=481),
        _series(weekdays={0, MON}),
        _series(weekdays={8}),
        _series(every=0),
        _series(every=5),
        _series(starts_on=NOV[10], ends_on=NOV[9]),  # until < from
        _series(CONFERENCE, weekdays=(), starts_on=NOV[15], ends_on=NOV[20]),  # one-off + until
        _series(title="x" * 49),
    ],
    ids=[
        "past-24:00",
        "23:59+15",
        "14-min",
        "481-min",
        "weekday-0",
        "weekday-8",
        "every-0",
        "every-5",
        "until-before-from",
        "one-off-with-until",
        "title-49",
    ],
)
def test_check_series_rejects(bad: ClassSeries) -> None:
    with pytest.raises(InvalidClass):
        check_series(bad)


@pytest.mark.parametrize("minutes", [15, 480])
def test_check_series_accepts_the_length_bounds(minutes: int) -> None:
    s = _series(start=time(6, 0), minutes=minutes)

    assert check_series(s) == s


def test_check_series_accepts_until_on_the_start_date_and_a_48_char_title() -> None:
    s = _series(starts_on=NOV[9], ends_on=NOV[9], title="x" * 48)

    assert check_series(s) == s


def test_invalid_class_is_a_value_error() -> None:
    assert issubclass(InvalidClass, ValueError)


# to_rrule


def test_to_rrule_every_two_weeks_with_until() -> None:
    s = _series(weekdays={WED, MON}, every=2, ends_on=date(2026, 12, 31), zone=ALMATY)

    rule = to_rrule(s)

    assert rule is not None
    assert re.fullmatch(r"FREQ=WEEKLY;INTERVAL=2;BYDAY=MO,WE;UNTIL=20261231(T\d{6}Z)?", rule)


def test_to_rrule_weekly_without_until_lists_days_monday_first() -> None:
    rule = to_rrule(_series(weekdays={SUN, FRI, MON}, every=1))

    assert rule is not None
    assert re.fullmatch(r"FREQ=WEEKLY(;INTERVAL=1)?;BYDAY=MO,FR,SU", rule)
    assert "UNTIL" not in rule


def test_to_rrule_of_a_one_off_is_none() -> None:
    assert to_rrule(_series(CONFERENCE, weekdays=(), starts_on=NOV[15])) is None


# wall_to_utc and DST (ADR-0005: wall clock stays, the instant moves)


@pytest.mark.parametrize(
    ("zone", "day", "utc"),
    [
        ("Asia/Kolkata", NOV[9], _utc(2026, 11, 9, 0, 30)),  # +5:30 (Goa, Mysuru)
        ("Asia/Kathmandu", NOV[9], _utc(2026, 11, 9, 0, 15)),  # +5:45
        ("Asia/Almaty", NOV[9], _utc(2026, 11, 9, 1, 0)),  # +5
        ("Europe/Moscow", NOV[9], _utc(2026, 11, 9, 3, 0)),  # +3
        ("Europe/Berlin", NOV[9], _utc(2026, 11, 9, 5, 0)),  # +1 in winter
        ("Europe/Berlin", date(2026, 6, 1), _utc(2026, 6, 1, 4, 0)),  # +2 in summer
        ("America/New_York", NOV[9], _utc(2026, 11, 9, 11, 0)),  # -5 after 1 Nov
    ],
)
def test_wall_to_utc_in_each_zone(zone: str, day: date, utc: datetime) -> None:
    assert wall_to_utc(day, time(6, 0), zone) == utc


@pytest.mark.parametrize(
    ("zone", "before", "after", "utc_before", "utc_after"),
    [
        # Berlin and London change on the last Sunday of March (29 Mar 2026).
        ("Europe/Berlin", date(2026, 3, 27), date(2026, 3, 30), time(5, 30), time(4, 30)),
        ("Europe/London", date(2026, 3, 27), date(2026, 3, 30), time(6, 30), time(5, 30)),
        # ... and back on the last Sunday of October (25 Oct 2026).
        ("Europe/Berlin", date(2026, 10, 23), date(2026, 10, 26), time(4, 30), time(5, 30)),
        ("Europe/London", date(2026, 10, 23), date(2026, 10, 26), time(5, 30), time(6, 30)),
        # New York: 8 Mar and 1 Nov 2026.
        ("America/New_York", date(2026, 3, 6), date(2026, 3, 9), time(11, 30), time(10, 30)),
        ("America/New_York", date(2026, 10, 30), date(2026, 11, 2), time(10, 30), time(11, 30)),
    ],
)
def test_a_0630_mysore_keeps_its_wall_clock_across_the_change(
    zone: str, before: date, after: date, utc_before: time, utc_after: time
) -> None:
    s = _series(start=time(6, 30), weekdays=MON_FRI, starts_on=date(2026, 1, 5), zone=zone)

    out = _expand([s], before, after)

    first, last = _one(out, before, s), _one(out, after, s)
    assert (first.start, last.start) == (time(6, 30), time(6, 30))
    assert first.starts_at == datetime.combine(before, utc_before, UTC)
    assert last.starts_at == datetime.combine(after, utc_after, UTC)


@pytest.mark.parametrize(
    ("zone", "day", "utc"),
    [
        ("Europe/Berlin", date(2026, 3, 29), _utc(2026, 3, 29, 1, 30)),  # = 03:30 CEST
        ("America/New_York", date(2026, 3, 8), _utc(2026, 3, 8, 7, 30)),  # = 03:30 EDT
    ],
)
def test_a_start_in_the_spring_gap_shifts_forward_by_the_gap(
    zone: str, day: date, utc: datetime
) -> None:
    instant = wall_to_utc(day, time(2, 30), zone)

    assert instant == utc
    assert instant.astimezone(ZoneInfo(zone)).time() == time(3, 30)


@pytest.mark.parametrize(
    ("zone", "day", "wall", "utc"),
    [
        ("Europe/Berlin", date(2026, 10, 25), time(2, 30), _utc(2026, 10, 25, 0, 30)),  # CEST
        ("America/New_York", date(2026, 11, 1), time(1, 30), _utc(2026, 11, 1, 5, 30)),  # EDT
    ],
)
def test_an_ambiguous_start_takes_the_first_instant(
    zone: str, day: date, wall: time, utc: datetime
) -> None:
    assert wall_to_utc(day, wall, zone) == utc


def test_wall_to_utc_returns_an_aware_utc_instant() -> None:
    instant = wall_to_utc(NOV[9], time(6, 0), BERLIN)

    assert instant.utcoffset() == timedelta(0)


def test_a_class_created_in_winter_viewed_for_summer() -> None:
    s = _series(start=time(6, 30), starts_on=date(2026, 1, 5), zone=BERLIN)

    [o] = _expand([s], date(2026, 6, 1), date(2026, 6, 1))

    assert (o.start, o.starts_at) == (time(6, 30), _utc(2026, 6, 1, 4, 30))


def test_your_time_for_an_almaty_viewer_of_a_berlin_online_class() -> None:
    """Fri 27 Mar: Berlin +1, Almaty +5 (4 h apart); Mon 30 Mar: Berlin +2 (3 h apart)."""
    s = _series(
        LED, start=time(18, 30), minutes=90, starts_on=date(2026, 3, 2), zone=BERLIN, online=True
    )
    almaty = ZoneInfo(ALMATY)

    out = _expand([s], date(2026, 3, 27), date(2026, 3, 30))

    fri, mon = _one(out, date(2026, 3, 27), s), _one(out, date(2026, 3, 30), s)
    assert fri.starts_at.astimezone(almaty).time() == time(22, 30)
    assert mon.starts_at.astimezone(almaty).time() == time(21, 30)


# expand: the occurrence itself


def test_an_occurrence_carries_the_rule_and_its_window() -> None:
    s = _series(MYSORE, start=time(6, 0), minutes=210, title="Early", teacher=ANNA)

    o = _one(_expand([s], NOV[9], NOV[9]), NOV[9], s)

    assert (o.class_id, o.key, o.on) == (s.id, NOV[9], NOV[9])
    assert (o.start, o.end) == (time(6, 0), time(9, 30))
    assert o.starts_at == _utc(2026, 11, 9, 1, 0)
    assert (o.type, o.title, o.online, o.teacher_id) == (MYSORE, "Early", False, ANNA)
    assert (o.substitute, o.cancelled, o.moved, o.swapped_from) == (False, None, False, None)


def test_a_class_ending_at_midnight_ends_at_midnight() -> None:
    s = _series(LED, start=time(22, 0), minutes=120)

    o = _one(_expand([s], NOV[9], NOV[9]), NOV[9], s)

    assert o.end == time(0, 0)


def test_occurrences_are_sorted_by_the_utc_instant() -> None:
    """By instant, not wall clock: Almaty 07:00 (02:00 UTC) before a Berlin online 05:00
    (04:00 UTC), and Tuesday's Almaty 06:00 (01:00 UTC on Tuesday) last."""
    almaty = _series(LED, weekdays={MON}, start=time(7, 0), minutes=60)
    berlin = _series(LED, weekdays={MON}, start=time(5, 0), minutes=60, zone=BERLIN, online=True)
    tuesday = _series(MYSORE, weekdays={TUE}, start=time(6, 0))

    out = _expand([tuesday, berlin, almaty], NOV[9], NOV[10])

    assert [o.class_id for o in out] == [almaty.id, berlin.id, tuesday.id]
    assert [o.starts_at for o in out] == sorted(o.starts_at for o in out)


def test_only_dates_inside_the_window_are_kept() -> None:
    s = _series(weekdays=EVERY_DAY)

    out = _expand([s], NOV[9], NOV[11])

    assert [o.on for o in out] == [NOV[9], NOV[10], NOV[11]]


def test_private_classes_are_for_staff_only() -> None:
    one_to_one = _series(PRIVATE, weekdays={MON}, start=time(12, 0), minutes=60)
    mysore = _series(MYSORE, weekdays={MON})

    for_staff = _expand([one_to_one, mysore], NOV[9], NOV[9], staff_only=True)
    for_students = _expand([one_to_one, mysore], NOV[9], NOV[9], staff_only=False)

    assert {o.class_id for o in for_staff} == {one_to_one.id, mysore.id}
    assert {o.class_id for o in for_students} == {mysore.id}


def test_the_weekly_day_off_never_cancels_a_class_by_itself() -> None:
    """`expand` takes no day off: a Saturday conference is held (the form only warns)."""
    s = _series(CONFERENCE, weekdays=(), starts_on=NOV[14], start=time(10, 0), minutes=90)

    [o] = _expand([s], NOV[14], NOV[14])

    assert o.cancelled is None


# expand: moon days per policy (Q117)


@pytest.mark.parametrize(
    ("policy", "type"),
    list(itertools.product(MoonPolicy, ClassType)),
    ids=lambda v: str(v),
)
def test_each_policy_by_each_type_on_a_moon_date(policy: MoonPolicy, type: ClassType) -> None:
    s = _series(type, weekdays={FRI}, start=time(7, 0), minutes=60)
    held = (
        type
        in {
            CLOSED: set[ClassType](),
            PRANAYAMA_ONLY: {PRANAYAMA, CONFERENCE, CHANTING},
            OPEN: set(ClassType),
        }[policy]
    )

    o = _one(_expand([s], MOON_FRI, MOON_FRI, moon={MOON_FRI}, policy=policy), MOON_FRI, s)

    assert o.cancelled is (None if held else Reason.MOON)
    assert o.on == MOON_FRI


def test_led_is_cancelled_on_a_moon_day_under_both_closed_and_pranayama() -> None:
    s = _series(LED, weekdays={FRI}, start=time(7, 0), minutes=90)

    for policy in (CLOSED, PRANAYAMA_ONLY):
        [o] = _expand([s], MOON_FRI, MOON_FRI, moon={MOON_FRI}, policy=policy)
        assert o.cancelled is Reason.MOON


def test_a_kshaya_moon_date_cancels_exactly_the_stored_date() -> None:
    """The stored date is already the observed one: no recomputation, no shift to the next
    sunrise. Thu 12 is the stored moon date; Fri 13 runs as usual."""
    s = _series(weekdays=EVERY_DAY)

    out = _expand([s], NOV[11], NOV[13], moon={NOV[12]})

    assert {o.on: o.cancelled for o in out} == {
        NOV[11]: None,
        NOV[12]: Reason.MOON,
        NOV[13]: None,
    }


def test_moon_dates_compare_with_the_classs_local_date() -> None:
    """A class at 23:30 in New York is already the next day in UTC: the moon date is checked
    against the local date (as MD-02 applies a followed calendar)."""
    s = _series(LED, weekdays={FRI}, start=time(23, 0), minutes=60, zone="America/New_York")

    [o] = _expand([s], MOON_FRI, MOON_FRI, moon={MOON_FRI})

    assert o.on == MOON_FRI
    assert o.starts_at.date() == NOV[14]
    assert o.cancelled is Reason.MOON


def test_a_moon_date_on_the_day_off_cancels_nothing_extra() -> None:
    """A Sunday moon day that is also the shala's day off: the Sunday conference is held
    under `pranayama`, cancelled for the moon (only) under `closed`; Monday is untouched."""
    sunday = _series(CONFERENCE, weekdays={SUN}, start=time(10, 0), minutes=90)
    monday = _series(MYSORE, weekdays={MON})

    for policy, reason in ((PRANAYAMA_ONLY, None), (CLOSED, Reason.MOON)):
        out = _expand([sunday, monday], NOV[15], NOV[16], moon={NOV[15]}, policy=policy)
        assert _one(out, NOV[15], sunday).cancelled is reason
        assert _one(out, NOV[16], monday).cancelled is None


# expand: closures


def test_a_closure_covers_both_ends() -> None:
    s = _series(weekdays=EVERY_DAY)

    out = _expand([s], NOV[9], NOV[13], closures=[_closure(NOV[10], NOV[12])])

    assert {o.on: o.cancelled for o in out} == {
        NOV[9]: None,
        NOV[10]: Reason.CLOSURE,
        NOV[11]: Reason.CLOSURE,
        NOV[12]: Reason.CLOSURE,
        NOV[13]: None,
    }


def test_a_closure_wins_over_the_moon() -> None:
    s = _series(weekdays={FRI})

    [o] = _expand([s], MOON_FRI, MOON_FRI, moon={MOON_FRI}, closures=[_closure(NOV[13], NOV[13])])

    assert o.cancelled is Reason.CLOSURE


def test_a_closure_cancels_even_the_classes_an_open_policy_holds() -> None:
    s = _series(PRANAYAMA, weekdays={FRI}, start=time(7, 0), minutes=60)

    [o] = _expand([s], NOV[13], NOV[13], closures=[_closure(NOV[13], NOV[13])], policy=OPEN)

    assert o.cancelled is Reason.CLOSURE


# expand: overrides (staff override > closure > moon)


def test_a_cancel_override() -> None:
    s = _series(weekdays={MON})

    [o] = _expand(
        [s], NOV[9], NOV[9], overrides={(s.id, NOV[9]): _ov(NOV[9], OverrideStatus.CANCELLED)}
    )

    assert (o.cancelled, o.on, o.key) == (Reason.CANCELLED, NOV[9], NOV[9])


def test_held_beats_the_moon() -> None:
    s = _series(weekdays={FRI})

    [o] = _expand(
        [s],
        MOON_FRI,
        MOON_FRI,
        moon={MOON_FRI},
        overrides={(s.id, MOON_FRI): _ov(MOON_FRI, OverrideStatus.HELD)},
    )

    assert o.cancelled is None


def test_held_beats_a_closure() -> None:
    s = _series(weekdays={MON})

    [o] = _expand(
        [s],
        NOV[9],
        NOV[9],
        closures=[_closure(NOV[8], NOV[10])],
        overrides={(s.id, NOV[9]): _ov(NOV[9], OverrideStatus.HELD)},
    )

    assert o.cancelled is None


def test_a_move_changes_the_date_and_time_and_keeps_the_rule_key() -> None:
    s = _series(weekdays={MON}, start=time(6, 0), minutes=210)
    moved = _ov(NOV[9], moved_to=NOV[11], start=time(7, 0), minutes=90)

    out = _expand([s], NOV[9], NOV[15], overrides={(s.id, NOV[9]): moved})

    o = _one(out, NOV[9], s)
    assert (o.on, o.start, o.end, o.moved) == (NOV[11], time(7, 0), time(8, 30), True)
    assert o.starts_at == _utc(2026, 11, 11, 2, 0)
    assert o.cancelled is None


def test_a_time_only_change_is_not_a_date_move_but_is_moved() -> None:
    s = _series(weekdays={MON}, start=time(6, 0), minutes=210)

    o = _one(
        _expand([s], NOV[9], NOV[9], overrides={(s.id, NOV[9]): _ov(NOV[9], start=time(6, 30))}),
        NOV[9],
        s,
    )

    assert (o.on, o.start, o.end, o.moved) == (NOV[9], time(6, 30), time(10, 0), True)


def test_a_move_into_the_window_from_before_it() -> None:
    """The ±7 read margin: a rule date 6 days before the window, moved into it, shows."""
    s = _series(weekdays={TUE})
    moved = _ov(NOV[3], moved_to=NOV[9])

    out = _expand([s], NOV[9], NOV[9], overrides={(s.id, NOV[3]): moved})

    assert [(o.key, o.on) for o in out] == [(NOV[3], NOV[9])]


def test_a_move_into_the_window_from_after_it() -> None:
    s = _series(weekdays={SUN})
    moved = _ov(NOV[22], moved_to=NOV[16])

    out = _expand([s], NOV[9], NOV[16], overrides={(s.id, NOV[22]): moved})

    assert [(o.key, o.on) for o in out] == [(NOV[15], NOV[15]), (NOV[22], NOV[16])]


def test_a_move_out_of_the_window_drops_it() -> None:
    s = _series(weekdays={SUN})
    moved = _ov(NOV[15], moved_to=NOV[17])

    assert _expand([s], NOV[9], NOV[16], overrides={(s.id, NOV[15]): moved}) == []


def test_a_move_onto_a_moon_date_is_cancelled_there() -> None:
    """The checks run on the resulting date."""
    s = _series(weekdays={THU})
    moved = _ov(NOV[12], moved_to=MOON_FRI)

    [o] = _expand([s], NOV[12], NOV[13], moon={MOON_FRI}, overrides={(s.id, NOV[12]): moved})

    assert (o.on, o.cancelled) == (MOON_FRI, Reason.MOON)


def test_a_move_off_a_moon_date_is_held() -> None:
    s = _series(weekdays={FRI})
    moved = _ov(MOON_FRI, moved_to=NOV[12])

    [o] = _expand([s], NOV[12], NOV[13], moon={MOON_FRI}, overrides={(s.id, MOON_FRI): moved})

    assert (o.on, o.cancelled) == (NOV[12], None)


def test_a_substitute_teacher() -> None:
    s = _series(weekdays={MON}, teacher=ANNA)

    [o] = _expand([s], NOV[9], NOV[9], overrides={(s.id, NOV[9]): _ov(NOV[9], teacher=DANA)})

    assert (o.teacher_id, o.substitute, o.moved) == (DANA, True, False)


def test_an_override_on_a_date_the_rule_no_longer_produces_is_ignored() -> None:
    s = _series(weekdays={MON})
    stale = {
        (s.id, NOV[10]): _ov(NOV[10], OverrideStatus.CANCELLED),
        (s.id, NOV[11]): _ov(NOV[11], moved_to=NOV[12]),
    }

    out = _expand([s], NOV[9], NOV[15], overrides=stale)

    assert [(o.key, o.on, o.cancelled) for o in out] == [(NOV[9], NOV[9], None)]


def test_an_override_of_another_class_is_ignored() -> None:
    a, b = _series(weekdays={MON}), _series(weekdays={MON}, start=time(18, 0), minutes=90)

    out = _expand(
        [a, b], NOV[9], NOV[9], overrides={(b.id, NOV[9]): _ov(NOV[9], OverrideStatus.CANCELLED)}
    )

    assert _one(out, NOV[9], a).cancelled is None
    assert _one(out, NOV[9], b).cancelled is Reason.CANCELLED


# expand: swap days (Q125)


def _friday_and_saturday() -> tuple[ClassSeries, ClassSeries]:
    mysore = _series(MYSORE, weekdays=MON_FRI, start=time(6, 0), minutes=210)
    pranayama = _series(PRANAYAMA, weekdays={FRI}, start=time(7, 0), minutes=60)
    return mysore, pranayama


def test_a_swap_moves_the_moon_cancelled_mysore_to_the_day_off() -> None:
    mysore, pranayama = _friday_and_saturday()

    out = _expand(
        [mysore, pranayama],
        MOON_FRI,
        NOV[14],
        moon={MOON_FRI},
        policy=PRANAYAMA_ONLY,
        swaps=[Swap(MOON_FRI, NOV[14])],
    )

    moved = _one(out, MOON_FRI, mysore)
    assert (moved.on, moved.start, moved.end) == (NOV[14], time(6, 0), time(9, 30))
    assert (moved.cancelled, moved.swapped_from) == (None, MOON_FRI)
    assert moved.starts_at == _utc(2026, 11, 14, 1, 0)
    held = _one(out, MOON_FRI, pranayama)
    assert (held.on, held.cancelled, held.swapped_from) == (MOON_FRI, None, None)


def test_a_swapped_occurrence_shows_in_a_window_of_only_the_target_day() -> None:
    mysore, _ = _friday_and_saturday()

    out = _expand([mysore], NOV[14], NOV[14], moon={MOON_FRI}, swaps=[Swap(MOON_FRI, NOV[14])])

    assert [(o.key, o.on, o.swapped_from) for o in out] == [(MOON_FRI, NOV[14], MOON_FRI)]


def test_a_swap_moves_closure_cancelled_occurrences_too() -> None:
    s = _series(weekdays={WED})

    [o] = _expand(
        [s], NOV[11], NOV[14], closures=[_closure(NOV[11], NOV[11])], swaps=[Swap(NOV[11], NOV[14])]
    )

    assert (o.key, o.on, o.cancelled, o.swapped_from) == (NOV[11], NOV[14], None, NOV[11])


@pytest.mark.parametrize("status", [OverrideStatus.CANCELLED, OverrideStatus.HELD])
def test_a_class_cancelled_by_hand_or_held_on_a_does_not_move(status: OverrideStatus) -> None:
    mysore, _ = _friday_and_saturday()

    [o] = _expand(
        [mysore],
        MOON_FRI,
        NOV[14],
        moon={MOON_FRI},
        swaps=[Swap(MOON_FRI, NOV[14])],
        overrides={(mysore.id, MOON_FRI): _ov(MOON_FRI, status)},
    )

    assert (o.on, o.swapped_from) == (MOON_FRI, None)
    assert o.cancelled is (Reason.CANCELLED if status is OverrideStatus.CANCELLED else None)


def test_under_open_nothing_moves() -> None:
    mysore, _ = _friday_and_saturday()

    [o] = _expand(
        [mysore], MOON_FRI, NOV[14], moon={MOON_FRI}, policy=OPEN, swaps=[Swap(MOON_FRI, NOV[14])]
    )

    assert (o.on, o.cancelled, o.swapped_from) == (MOON_FRI, None, None)


def test_a_closure_added_after_the_swap_cancels_it_on_b() -> None:
    mysore, _ = _friday_and_saturday()

    [o] = _expand(
        [mysore],
        MOON_FRI,
        NOV[14],
        moon={MOON_FRI},
        swaps=[Swap(MOON_FRI, NOV[14])],
        closures=[_closure(NOV[14], NOV[20])],
    )

    assert (o.on, o.cancelled, o.swapped_from) == (NOV[14], Reason.CLOSURE, MOON_FRI)


def test_a_swap_backwards_into_the_window() -> None:
    """A Monday moon day swapped to the Sunday before: the read margin covers A after the
    window end."""
    s = _series(weekdays={MON})

    out = _expand([s], NOV[15], NOV[15], moon={NOV[16]}, swaps=[Swap(NOV[16], NOV[15])])

    assert [(o.key, o.on, o.swapped_from) for o in out] == [(NOV[16], NOV[15], NOV[16])]


# check_swap (Q125): validation at creation


TODAY = NOV[7]
SAT_OFF = frozenset({SAT})


def _check(
    a: date,
    b: date,
    *,
    today: date = TODAY,
    days_off: frozenset[int] = SAT_OFF,
    moon: Iterable[date] = (MOON_FRI,),
    closures: Iterable[Closure] = (),
    types_on: Mapping[date, set[ClassType]] | None = None,
) -> None:
    check_swap(
        a,
        b,
        today,
        days_off,
        frozenset(moon),
        list(closures),
        types_on if types_on is not None else {MOON_FRI: {MYSORE, PRANAYAMA}},
    )


def test_a_moon_friday_to_the_saturday_day_off_is_fine() -> None:
    _check(MOON_FRI, NOV[14])


@pytest.mark.parametrize("delta", [-6, 6])
def test_six_days_either_way_is_fine(delta: int) -> None:
    b = MOON_FRI + timedelta(days=delta)

    _check(MOON_FRI, b, types_on={MOON_FRI: {MYSORE}})


@pytest.mark.parametrize("delta", [0, 7, -7])
def test_zero_or_seven_days_is_invalid(delta: int) -> None:
    with pytest.raises(InvalidClass):
        _check(MOON_FRI, MOON_FRI + timedelta(days=delta), types_on={MOON_FRI: {MYSORE}})


def test_b_on_a_moon_day_is_invalid() -> None:
    with pytest.raises(InvalidClass):
        _check(MOON_FRI, NOV[14], moon={MOON_FRI, NOV[14]})


@pytest.mark.parametrize(("start", "end"), [(NOV[14], NOV[14]), (NOV[12], NOV[20])])
def test_b_inside_a_closure_is_invalid(start: date, end: date) -> None:
    with pytest.raises(InvalidClass):
        _check(MOON_FRI, NOV[14], closures=[_closure(start, end)])


def test_b_neither_day_off_nor_free_of_the_moving_type_is_invalid() -> None:
    """Thu 12 already has a Mysore class: moving Friday's Mysore onto it doubles it."""
    with pytest.raises(InvalidClass):
        _check(MOON_FRI, NOV[12], types_on={MOON_FRI: {MYSORE}, NOV[12]: {MYSORE}})


def test_b_with_only_other_types_is_fine() -> None:
    _check(MOON_FRI, NOV[12], types_on={MOON_FRI: {MYSORE}, NOV[12]: {CONFERENCE}})


def test_b_on_the_day_off_is_fine_even_with_the_same_type() -> None:
    _check(MOON_FRI, NOV[14], types_on={MOON_FRI: {MYSORE}, NOV[14]: {MYSORE}})


@pytest.mark.parametrize("b", [NOV[15], NOV[22]], ids=["sunday-before", "sunday-after"])
def test_a_monday_moon_day_with_a_sunday_day_off(b: date) -> None:
    _check(
        NOV[16],
        b,
        days_off=frozenset({SUN}),
        moon={NOV[16]},
        types_on={NOV[16]: {MYSORE}, NOV[15]: {MYSORE}, NOV[22]: {MYSORE}},
    )


def test_b_in_the_past_is_invalid() -> None:
    with pytest.raises(InvalidClass):
        _check(NOV[9], NOV[6], moon={NOV[9]}, types_on={NOV[9]: {MYSORE}})


def test_b_beyond_the_horizon_is_invalid() -> None:
    a = TODAY + timedelta(days=HORIZON - 1)
    with pytest.raises(InvalidClass):
        _check(a, a + timedelta(days=2), moon={a}, types_on={a: {MYSORE}})


def test_b_on_the_horizon_is_fine() -> None:
    a = TODAY + timedelta(days=HORIZON - 1)
    b = TODAY + timedelta(days=HORIZON)

    _check(a, b, days_off=frozenset({b.isoweekday()}), moon={a}, types_on={a: {MYSORE}})


def test_a_swapped_occurrence_keeps_why_it_left() -> None:
    """A closure on a moon day: the class left for the closure (closure > moon)."""
    mysore, _ = _friday_and_saturday()

    [o] = _expand(
        [mysore],
        MOON_FRI,
        NOV[14],
        moon={MOON_FRI},
        closures=[_closure(MOON_FRI, MOON_FRI)],
        swaps=[Swap(MOON_FRI, NOV[14])],
    )

    assert (o.on, o.swap_reason) == (NOV[14], Reason.CLOSURE)
