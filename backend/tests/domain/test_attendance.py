"""SC-05 attendance, the pure part (spec §3, §8; ADR-0039)."""

from datetime import UTC, date, datetime, time
from uuid import uuid4

import pytest

from tristhana.domain.attendance import (
    BACK_DAYS,
    LOG_DAY_TYPES,
    AttendanceState,
    attendable,
    claim_state,
    merge,
    offers_log_day,
    snapshot,
)
from tristhana.domain.classes import (
    ClassSeries,
    ClassType,
    MoonPolicy,
    Occurrence,
    Override,
    OverrideStatus,
    Reason,
    Swap,
    expand,
)

ALMATY = "Asia/Almaty"  # UTC+5, no DST
SHALA = uuid4()


def _series(**kw: object) -> ClassSeries:
    base: dict[str, object] = {
        "id": uuid4(),
        "type": ClassType.MYSORE,
        "title": None,
        "online": False,
        "zone": ALMATY,
        "teacher_id": None,
        "start": time(6, 0),
        "minutes": 210,
        "weekdays": frozenset({1, 2, 3, 4, 5, 6, 7}),
        "every": 1,
        "starts_on": date(2026, 10, 1),
        "ends_on": None,
    }
    base.update(kw)
    return ClassSeries(**base)  # type: ignore[arg-type]


def _one(series: ClassSeries, on: date, **kw: object) -> Occurrence:
    found = expand(
        [series],
        kw.get("overrides", {}),  # type: ignore[arg-type]
        (),
        kw.get("swaps", ()),  # type: ignore[arg-type]
        kw.get("moon", frozenset()),  # type: ignore[arg-type]
        kw.get("policy", MoonPolicy.CLOSED),  # type: ignore[arg-type]
        on,
        on,
        staff_only=True,
        keep_swapped=bool(kw.get("keep", False)),
    )
    assert len(found) == 1, found
    return found[0]


def _at(day: date, hh: int, mm: int = 0, zone: str = ALMATY) -> datetime:
    from zoneinfo import ZoneInfo

    return datetime.combine(day, time(hh, mm), ZoneInfo(zone)).astimezone(UTC)


MON = date(2026, 11, 9)


class TestAttendable:
    def test_a_mysore_window_counts_from_its_opening(self) -> None:
        o = _one(_series(), MON)
        assert not attendable(o, ALMATY, _at(MON, 5, 59))
        assert attendable(o, ALMATY, _at(MON, 6, 0))
        assert attendable(o, ALMATY, _at(MON, 23, 59))

    def test_a_led_class_at_its_start_minute(self) -> None:
        o = _one(_series(type=ClassType.LED, start=time(8, 0), minutes=90), MON)
        assert attendable(o, ALMATY, _at(MON, 8, 0))

    def test_today_minus_6_is_in_and_minus_7_is_out(self) -> None:
        now = _at(MON, 12)
        assert attendable(_one(_series(), date(2026, 11, 3)), ALMATY, now)
        assert not attendable(_one(_series(), date(2026, 11, 2)), ALMATY, now)
        assert BACK_DAYS == 6

    def test_the_window_uses_the_class_zone_today(self) -> None:
        # Los Angeles shala, seen at Almaty midnight (still the previous day in LA).
        la = "America/Los_Angeles"
        s = _series(zone=la)
        now = _at(date(2026, 11, 10), 0, 30)  # 9 Nov 11:30 in LA
        assert attendable(_one(s, date(2026, 11, 3)), la, now)  # LA today - 6
        assert not attendable(_one(s, date(2026, 11, 2)), la, now)

    @pytest.mark.parametrize("why", ["moon", "closure", "staff"])
    def test_a_cancelled_occurrence_is_out(self, why: str) -> None:
        s = _series()
        if why == "moon":
            o = _one(s, MON, moon=frozenset({MON}))
            assert o.cancelled is Reason.MOON
        elif why == "staff":
            ov = {(s.id, MON): Override(MON, OverrideStatus.CANCELLED)}
            o = _one(s, MON, overrides=ov)
        else:
            from tristhana.domain.classes import Closure

            o = expand([s], {}, (Closure(uuid4(), MON, MON),), (), frozenset(),
                       MoonPolicy.CLOSED, MON, MON, staff_only=True)[0]  # fmt: skip
        assert o.cancelled is not None
        assert not attendable(o, ALMATY, _at(MON, 12))

    def test_a_pranayama_class_held_on_a_moon_day_is_in(self) -> None:
        s = _series(type=ClassType.PRANAYAMA, minutes=60)
        o = _one(s, MON, moon=frozenset({MON}), policy=MoonPolicy.PRANAYAMA)
        assert o.cancelled is None
        assert o.moon
        assert attendable(o, ALMATY, _at(MON, 12))

    def test_an_open_policy_mysore_on_a_moon_day_is_in(self) -> None:
        o = _one(_series(), MON, moon=frozenset({MON}), policy=MoonPolicy.OPEN)
        assert attendable(o, ALMATY, _at(MON, 12))

    def test_a_hold_anyway_class_on_a_moon_day_is_in(self) -> None:
        s = _series()
        ov = {(s.id, MON): Override(MON, OverrideStatus.HELD)}
        o = _one(s, MON, moon=frozenset({MON}), overrides=ov)
        assert o.held
        assert attendable(o, ALMATY, _at(MON, 12))

    def test_a_moved_occurrence_keeps_its_key(self) -> None:
        s = _series(weekdays=frozenset({1}))
        ov = {(s.id, MON): Override(MON, None, moved_to=date(2026, 11, 10))}
        o = _one(s, date(2026, 11, 10), overrides=ov)
        assert o.key == MON
        assert o.on == date(2026, 11, 10)
        assert attendable(o, ALMATY, _at(date(2026, 11, 10), 12))
        assert not attendable(o, ALMATY, _at(MON, 12))  # it hasn't started yet

    def test_a_swap_b_is_in_and_the_kept_original_a_is_out(self) -> None:
        s = _series(weekdays=frozenset({1}))
        b = date(2026, 11, 10)
        swaps = (Swap(MON, b),)
        moved = _one(s, b, moon=frozenset({MON}), swaps=swaps)
        assert moved.key == MON
        assert moved.swapped_from == MON
        assert attendable(moved, ALMATY, _at(b, 12))
        kept = _one(s, MON, moon=frozenset({MON}), swaps=swaps, keep=True)
        assert kept.swapped_to == b
        assert not attendable(kept, ALMATY, _at(b, 12))

    def test_a_spring_gap_start_is_shifted(self) -> None:
        berlin = "Europe/Berlin"
        day = date(2027, 3, 28)  # 02:00 → 03:00
        o = _one(_series(zone=berlin, start=time(2, 30), minutes=60), day)
        assert o.starts_at == datetime(2027, 3, 28, 1, 30, tzinfo=UTC)
        assert attendable(o, berlin, datetime(2027, 3, 28, 1, 30, tzinfo=UTC))


class TestSnapshot:
    def test_it_keeps_the_instant_and_the_iana_zone_across_dst(self) -> None:
        berlin = "Europe/Berlin"
        day = date(2026, 10, 25)  # the autumn change
        s = _series(zone=berlin, start=time(7, 0), minutes=90, type=ClassType.LED)
        o = _one(s, day)
        snap = snapshot(o, SHALA, berlin)
        assert snap.shala_id == SHALA
        assert snap.class_id == s.id
        assert snap.key == day
        assert snap.on == day
        assert snap.zone == berlin
        assert snap.type is ClassType.LED
        assert snap.starts_at == datetime(2026, 10, 25, 6, 0, tzinfo=UTC)  # 07:00 CET
        from zoneinfo import ZoneInfo

        assert snap.starts_at.astimezone(ZoneInfo(berlin)).time() == time(7, 0)


class TestStates:
    def test_a_staff_claim_is_confirmed(self) -> None:
        assert claim_state(may_take=True) is AttendanceState.CONFIRMED
        assert claim_state(may_take=False) is AttendanceState.CLAIMED

    def test_merge_never_downgrades(self) -> None:
        c, k = AttendanceState.CONFIRMED, AttendanceState.CLAIMED
        assert merge(None, k) is k
        assert merge(k, c) is c
        assert merge(c, k) is c
        assert merge(c, c) is c


class TestLogDay:
    """Q196 (ashtanga-expert): Conference and Chanting are not asana practice."""

    @pytest.mark.parametrize("t", list(ClassType))
    def test_which_types_offer_log_this_day(self, t: ClassType) -> None:
        expected = t not in {ClassType.CONFERENCE, ClassType.CHANTING}
        assert offers_log_day(t) is expected
        assert (t in LOG_DAY_TYPES) is expected
