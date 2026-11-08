"""SC-03, the pure parts (spec §3, §7, §8; ADR-0035): the viewer-side time math in
`domain/classes.py` and the two `expand` additions.

- `offset_gap(zone, viewer, day)`: class offset - viewer offset at the viewer's local noon;
- `shifts(zones, viewer, start, end)`: one `Shift(zone, on, minutes)` per change of that gap
  between day d-1 and day d, d ∈ [start, end]; `minutes` > 0 = the class is earlier for the
  viewer, < 0 = later; both sides shifting together gives nothing (Q140);
- `local_date(o, zone)`: the date of `o.starts_at` in `zone` (rows sit under the viewer's date);
- `Occurrence.moon`: the final date is a moon date of its shala's calendar, whatever the policy
  (so "held on the moon day" = `moon and cancelled is None`, expert item 1);
- `expand(…, keep_swapped=True)`: also returns the auto-cancelled occurrence on A with
  `swapped_to = B` (expert item 3); the default output is SC-02's, unchanged.

Zones: Almaty (+5), Kolkata (+5:30), Kathmandu (+5:45), Berlin and London (EU DST, the same
instant), New York (US DST, two weeks earlier in March), Moscow (no DST), Los Angeles and
Kiritimati (+14). EU DST ends Sun 25 Oct 2026 and starts Sun 28 Mar 2027; US DST starts
Sun 14 Mar 2027.
"""

import itertools
from collections.abc import Iterable, Mapping
from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID

import pytest

from tristhana.domain.classes import (
    ClassSeries,
    ClassType,
    Closure,
    MoonPolicy,
    Occurrence,
    Override,
    OverrideStatus,
    Reason,
    Shift,
    Swap,
    expand,
    local_date,
    offset_gap,
    shifts,
)

ALMATY, BERLIN, LONDON, MOSCOW = "Asia/Almaty", "Europe/Berlin", "Europe/London", "Europe/Moscow"
KOLKATA, KATHMANDU, NEW_YORK = "Asia/Kolkata", "Asia/Kathmandu", "America/New_York"
LOS_ANGELES, KIRITIMATI = "America/Los_Angeles", "Pacific/Kiritimati"
MON_FRI = frozenset({1, 2, 3, 4, 5})
EVERY_DAY = frozenset(range(1, 8))
ANNA = UUID(int=0xA1)
NOV = {d: date(2026, 11, d) for d in range(1, 31)}
OCT = {d: date(2026, 10, d) for d in range(1, 32)}
MAR = {d: date(2027, 3, d) for d in range(1, 32)}
_ids = itertools.count(1)


def _series(
    type: ClassType = ClassType.MYSORE,
    *,
    weekdays: Iterable[int] = MON_FRI,
    start: time = time(6, 0),
    minutes: int = 210,
    starts_on: date = NOV[2],
    zone: str = ALMATY,
) -> ClassSeries:
    return ClassSeries(
        id=UUID(int=next(_ids)),
        type=type,
        title=None,
        online=zone != ALMATY,
        zone=zone,
        teacher_id=ANNA,
        start=start,
        minutes=minutes,
        weekdays=frozenset(weekdays),
        every=1,
        starts_on=starts_on,
        ends_on=None,
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
    policy: MoonPolicy = MoonPolicy.CLOSED,
    keep_swapped: bool | None = None,
) -> list[Occurrence]:
    """`keep_swapped` None: the SC-02 call, without the new argument."""
    args = (
        list(series),
        dict(overrides or {}),
        list(closures),
        list(swaps),
        frozenset(moon),
        policy,
        start,
        end,
        True,
    )
    if keep_swapped is None:
        return expand(*args)
    return expand(*args, keep_swapped=keep_swapped)


def _hours(h: int, m: int = 0) -> timedelta:
    return timedelta(hours=h, minutes=m)


# offset_gap: class offset - viewer offset, at the viewer's local noon


@pytest.mark.parametrize(
    ("zone", "viewer", "day", "gap"),
    [
        (BERLIN, ALMATY, OCT[24], -_hours(3)),  # CEST +2 vs +5
        (BERLIN, ALMATY, OCT[25], -_hours(4)),  # CET +1 vs +5, the change night
        (BERLIN, ALMATY, MAR[27], -_hours(4)),
        (BERLIN, ALMATY, MAR[28], -_hours(3)),
        (BERLIN, NEW_YORK, MAR[13], _hours(6)),
        (BERLIN, NEW_YORK, MAR[14], _hours(5)),  # New York moved first
        (BERLIN, NEW_YORK, MAR[28], _hours(6)),
        (BERLIN, KOLKATA, OCT[24], -_hours(3, 30)),
        (BERLIN, KATHMANDU, OCT[24], -_hours(3, 45)),
        (BERLIN, KATHMANDU, OCT[25], -_hours(4, 45)),
        (KOLKATA, BERLIN, OCT[25], _hours(4, 30)),
        (LONDON, BERLIN, OCT[24], -_hours(1)),
        (LONDON, BERLIN, OCT[25], -_hours(1)),
        (ALMATY, ALMATY, NOV[9], timedelta(0)),
        (KIRITIMATI, LOS_ANGELES, NOV[9], _hours(22)),
    ],
)
def test_offset_gap(zone: str, viewer: str, day: date, gap: timedelta) -> None:
    assert offset_gap(zone, viewer, day) == gap


# shifts (Q140)


def test_an_almaty_viewer_of_a_berlin_class_across_the_october_change() -> None:
    """17:30 Berlin is 20:30 in Almaty until Sat 24 Oct, 21:30 from Sun 25 Oct: 1 h later."""
    assert shifts({BERLIN}, ALMATY, OCT[19], OCT[25]) == (Shift(BERLIN, OCT[25], -60),)


def test_an_almaty_viewer_of_a_berlin_class_across_the_march_change() -> None:
    assert shifts({BERLIN}, ALMATY, MAR[22], MAR[28]) == (Shift(BERLIN, MAR[28], 60),)


def test_a_new_york_viewer_of_a_berlin_class_gets_two_shifts_in_march() -> None:
    """The US moves on 14 Mar (the class is an hour later for New York), the EU on 28 Mar
    (back an hour earlier)."""
    assert shifts({BERLIN}, NEW_YORK, MAR[14], MAR[28]) == (
        Shift(BERLIN, MAR[14], -60),
        Shift(BERLIN, MAR[28], 60),
    )


@pytest.mark.parametrize(
    ("start", "end"), [(OCT[19], OCT[25]), (MAR[22], MAR[28])], ids=["october", "march"]
)
def test_both_sides_shifting_together_shows_nothing(start: date, end: date) -> None:
    assert shifts({LONDON}, BERLIN, start, end) == ()
    assert shifts({BERLIN}, LONDON, start, end) == ()


def test_the_viewers_own_change_shifts_a_class_in_a_zone_without_dst() -> None:
    """A Berlin viewer of a Mysuru class: Berlin leaves summer time, so the 06:00 IST class
    moves from 02:30 to 01:30 for them: an hour earlier."""
    assert shifts({KOLKATA}, BERLIN, OCT[19], OCT[25]) == (Shift(KOLKATA, OCT[25], 60),)


def test_a_shift_on_the_windows_first_day_is_compared_with_the_day_before() -> None:
    assert shifts({BERLIN}, ALMATY, OCT[25], OCT[31]) == (Shift(BERLIN, OCT[25], -60),)


def test_a_change_the_day_before_the_window_is_not_in_it() -> None:
    assert shifts({BERLIN}, ALMATY, OCT[26], NOV[1]) == ()


@pytest.mark.parametrize("viewer", [KOLKATA, KATHMANDU, MOSCOW])
def test_half_and_three_quarter_hour_viewers(viewer: str) -> None:
    assert shifts({BERLIN}, viewer, OCT[19], OCT[25]) == (Shift(BERLIN, OCT[25], -60),)


def test_a_week_without_a_change_and_no_zones_give_nothing() -> None:
    assert shifts({BERLIN, ALMATY}, ALMATY, NOV[9], NOV[15]) == ()
    assert shifts(set[str](), ALMATY, OCT[19], OCT[25]) == ()
    assert shifts({ALMATY}, ALMATY, OCT[19], OCT[25]) == ()


def test_each_class_zone_gets_its_own_line() -> None:
    """A New York viewer, late October: Berlin moves on 25 Oct, New York on 1 Nov; a Kolkata
    class only shifts with New York."""
    found = shifts({BERLIN, KOLKATA}, NEW_YORK, OCT[25], NOV[1])

    assert set(found) == {
        Shift(BERLIN, OCT[25], -60),
        Shift(BERLIN, NOV[1], 60),
        Shift(KOLKATA, NOV[1], 60),
    }
    assert len(found) == 3


# local_date: rows sit under the viewer's date


def _one(series: ClassSeries, day: date) -> Occurrence:
    [o] = _expand([series], day, day)
    return o


def test_a_los_angeles_evening_is_the_next_morning_in_almaty() -> None:
    o = _one(_series(zone=LOS_ANGELES, start=time(20, 0), minutes=60), NOV[9])

    assert local_date(o, LOS_ANGELES) == NOV[9]
    assert local_date(o, ALMATY) == NOV[10]


def test_kiritimati_and_los_angeles_are_almost_a_day_apart() -> None:
    """06:00 on Tue 10 Nov at +14 is 08:00 on Mon 9 Nov in Los Angeles; 20:00 on Mon 9 Nov in
    Los Angeles is 18:00 on Tue 10 Nov at +14."""
    early = _one(_series(zone=KIRITIMATI, start=time(6, 0), minutes=60), NOV[10])
    late = _one(_series(zone=LOS_ANGELES, start=time(20, 0), minutes=60), NOV[9])

    assert local_date(early, LOS_ANGELES) == NOV[9]
    assert local_date(late, KIRITIMATI) == NOV[10]


@pytest.mark.parametrize(
    ("viewer", "expected"),
    [(ALMATY, NOV[9]), (KOLKATA, NOV[9]), (KATHMANDU, NOV[10])],
)
def test_a_berlin_class_near_midnight_for_half_and_three_quarter_hour_viewers(
    viewer: str, expected: date
) -> None:
    """19:15 Berlin (UTC+1) = 18:15 UTC: 23:15 in Almaty, 23:45 in Kolkata, but 00:00 the next
    day in Kathmandu."""
    o = _one(_series(zone=BERLIN, start=time(19, 15), minutes=60), NOV[9])

    assert o.starts_at == datetime(2026, 11, 9, 18, 15, tzinfo=UTC)
    assert local_date(o, viewer) == expected


# expand: `moon` on every occurrence whose final date is a moon date (expert items 1, 4)

MOON_FRI = NOV[13]


def _ov(on: date, status: OverrideStatus | None = None, **kw: object) -> Override:
    return Override(on_date=on, status=status, **kw)  # type: ignore[arg-type]


def test_a_class_held_under_open_carries_moon() -> None:
    s = _series()

    out = _expand([s], NOV[12], MOON_FRI, moon={MOON_FRI}, policy=MoonPolicy.OPEN)

    assert [(o.on, o.cancelled, o.moon) for o in out] == [
        (NOV[12], None, False),
        (MOON_FRI, None, True),
    ]


def test_pranayama_held_under_the_pranayama_policy_carries_moon() -> None:
    mysore = _series()
    pranayama = _series(ClassType.PRANAYAMA, weekdays={5}, start=time(7, 0), minutes=60)

    out = _expand(
        [mysore, pranayama], MOON_FRI, MOON_FRI, moon={MOON_FRI}, policy=MoonPolicy.PRANAYAMA
    )

    found = {o.type: (o.cancelled, o.moon) for o in out}
    assert found == {
        ClassType.MYSORE: (Reason.MOON, True),
        ClassType.PRANAYAMA: (None, True),
    }


def test_hold_anyway_on_a_moon_day_carries_moon() -> None:
    s = _series()
    held = {(s.id, MOON_FRI): _ov(MOON_FRI, OverrideStatus.HELD)}

    [o] = _expand([s], MOON_FRI, MOON_FRI, overrides=held, moon={MOON_FRI})

    assert (o.cancelled, o.held, o.moon) == (None, True, True)


def test_moon_is_false_off_moon_days_and_on_a_closure() -> None:
    s = _series()
    closure = Closure(UUID(int=0xC1), NOV[10], NOV[10])

    out = _expand([s], NOV[9], NOV[12], moon={MOON_FRI}, closures=[closure])

    assert [(o.on, o.cancelled, o.moon) for o in out] == [
        (NOV[9], None, False),
        (NOV[10], Reason.CLOSURE, False),
        (NOV[11], None, False),
        (NOV[12], None, False),
    ]


def test_moon_follows_the_final_date_of_a_move() -> None:
    """Off a moon date: no 🌙. Onto one: cancelled there, with 🌙."""
    off, onto = _series(), _series(start=time(18, 0), minutes=60)
    moves = {
        (off.id, MOON_FRI): _ov(MOON_FRI, moved_to=NOV[12]),
        (onto.id, NOV[12]): _ov(NOV[12], moved_to=MOON_FRI),
    }

    out = _expand([off, onto], NOV[12], MOON_FRI, overrides=moves, moon={MOON_FRI})

    moved_off = next(o for o in out if o.class_id == off.id and o.key == MOON_FRI)
    moved_onto = next(o for o in out if o.class_id == onto.id and o.key == NOV[12])
    assert (moved_off.on, moved_off.cancelled, moved_off.moon) == (NOV[12], None, False)
    assert (moved_onto.on, moved_onto.cancelled, moved_onto.moon) == (MOON_FRI, Reason.MOON, True)


def test_a_swapped_occurrence_on_b_is_not_a_moon_row() -> None:
    s = _series()

    out = _expand([s], NOV[14], NOV[14], moon={MOON_FRI}, swaps=[Swap(MOON_FRI, NOV[14])])

    assert [(o.on, o.swapped_from, o.moon) for o in out] == [(NOV[14], MOON_FRI, False)]


# expand(keep_swapped=True): the cancelled original on A names B (expert item 3)


_SWAP_SERIES = _series(weekdays=MON_FRI)  # one id, so calls compare equal


def _swap_week(**kw: object) -> list[Occurrence]:
    return _expand(
        [_SWAP_SERIES],
        NOV[9],
        NOV[15],
        moon={MOON_FRI},
        swaps=[Swap(MOON_FRI, NOV[14])],
        **kw,  # type: ignore[arg-type]
    )


def test_keep_swapped_returns_the_cancelled_original_with_its_target() -> None:
    out = _swap_week(keep_swapped=True)

    on_a = [o for o in out if o.on == MOON_FRI]
    on_b = [o for o in out if o.on == NOV[14]]
    [a] = on_a
    [b] = on_b
    assert (a.key, a.cancelled, a.swapped_to, a.swapped_from, a.moon) == (
        MOON_FRI,
        Reason.MOON,
        NOV[14],
        None,
        True,
    )
    assert (b.key, b.cancelled, b.swapped_from, b.swapped_to) == (MOON_FRI, None, MOON_FRI, None)
    assert a.starts_at == datetime(2026, 11, 13, 1, 0, tzinfo=UTC)  # still A's own instant


def test_keep_swapped_keeps_a_closure_cancelled_original_too() -> None:
    s = _series(weekdays={3})
    closure = Closure(UUID(int=0xC2), NOV[11], NOV[11])

    out = _expand(
        [s], NOV[11], NOV[14], closures=[closure], swaps=[Swap(NOV[11], NOV[14])], keep_swapped=True
    )

    assert [(o.on, o.cancelled, o.swapped_to) for o in out] == [
        (NOV[11], Reason.CLOSURE, NOV[14]),
        (NOV[14], None, None),
    ]


def test_keep_swapped_shows_the_original_in_a_window_of_only_a() -> None:
    s = _series()

    kept = _expand(
        [s], MOON_FRI, MOON_FRI, moon={MOON_FRI}, swaps=[Swap(MOON_FRI, NOV[14])], keep_swapped=True
    )
    plain = _expand([s], MOON_FRI, MOON_FRI, moon={MOON_FRI}, swaps=[Swap(MOON_FRI, NOV[14])])

    assert [(o.on, o.swapped_to) for o in kept] == [(MOON_FRI, NOV[14])]
    assert plain == []


def test_a_class_cancelled_by_hand_on_a_has_no_swap_target() -> None:
    s = _series()
    cancelled = {(s.id, MOON_FRI): _ov(MOON_FRI, OverrideStatus.CANCELLED)}

    out = _expand(
        [s],
        MOON_FRI,
        NOV[14],
        overrides=cancelled,
        moon={MOON_FRI},
        swaps=[Swap(MOON_FRI, NOV[14])],
        keep_swapped=True,
    )

    assert [(o.on, o.cancelled, o.swapped_to) for o in out] == [(MOON_FRI, Reason.CANCELLED, None)]


def test_the_default_output_is_sc02s_unchanged() -> None:
    """Regression: without the argument, and with False, the original on A is not returned
    and no occurrence names a target."""
    default = _swap_week()
    explicit = _swap_week(keep_swapped=False)

    assert default == explicit
    assert [o.on for o in default] == [NOV[9], NOV[10], NOV[11], NOV[12], NOV[14]]
    assert all(o.swapped_to is None for o in default)
    assert [o for o in _swap_week(keep_swapped=True) if o not in default] == [
        next(o for o in _swap_week(keep_swapped=True) if o.on == MOON_FRI)
    ]


def test_new_occurrence_fields_default_for_sc02_callers() -> None:
    """`moon` and `swapped_to` have defaults, so SC-02's constructors keep working."""
    o = Occurrence(
        class_id=UUID(int=1),
        key=NOV[9],
        on=NOV[9],
        start=time(6, 0),
        end=time(9, 30),
        starts_at=datetime(2026, 11, 9, 1, 0, tzinfo=UTC),
        type=ClassType.MYSORE,
        title=None,
        online=False,
        teacher_id=None,
        substitute=False,
        cancelled=None,
        moved=False,
        swapped_from=None,
    )

    assert (o.moon, o.swapped_to) == (False, None)
