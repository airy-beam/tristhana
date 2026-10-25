"""The weekly day off and auto-rest (PR-09, ADR-0022).

Auto-rest is derived, never stored: an unlogged day from the join date to today shows as a
moon day of the followed calendar, else as the weekly day off in effect on that date. A log
always wins (Q21): practising on a moon day or logging 🌸 on the day off stay as logged.
A moon day on the day off is one rest day, never shifted (ashtanga-expert).
"""

from collections.abc import Iterable, Set
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from enum import StrEnum

from tristhana.domain.days import local_today

type Weekdays = frozenset[int]  # ISO: Monday = 1

WEEKDAYS: Weekdays = frozenset(range(1, 8))
MAX_DAYS_OFF = 2  # owner, 2026-10-25: e.g. Mysore Mon-Fri shalas


class InvalidDayOff(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class DayOff:
    days: Weekdays | None = None  # None = never chosen; empty = no fixed day off
    since: date | None = None  # the local date of the last choice
    before: Weekdays | None = None  # in effect before `since`; None: `days` applies to all


NEVER_CHOSEN = DayOff()


class AutoKind(StrEnum):
    MOON = "moon"
    DAY_OFF = "day_off"


@dataclass(frozen=True, slots=True)
class AutoDay:
    kind: AutoKind
    also_day_off: bool = False  # a moon day that is also the weekly day off


def check_day_off(days: Iterable[int]) -> Weekdays:
    listed = list(days)
    chosen = frozenset(listed)
    if len(chosen) != len(listed) or len(chosen) > MAX_DAYS_OFF or not chosen <= WEEKDAYS:
        raise InvalidDayOff(str(listed[:8]))
    return chosen


def day_off_on(off: DayOff, day: date) -> Weekdays:
    """The day off in effect on `day` (none when never chosen)."""
    earlier = off.since is not None and off.before is not None and day < off.since
    days = off.before if earlier else off.days
    return days or frozenset()


def change_day_off(off: DayOff, new: Weekdays, today: date) -> DayOff:
    """The first choice applies to all history, and so does a correction the same day (a
    mis-tap); a later change applies from `today`, and earlier dates keep the value before
    it. Only one earlier value is kept: after two later changes the oldest weeks show the
    middle one (accepted: it only colours unlogged days)."""
    if off.days is None:
        return DayOff(new, today)
    if new == off.days:
        return off
    if off.since == today:
        return replace(off, days=new)
    return DayOff(new, today, off.days)


def joined_on(created_at: datetime, zone: str) -> date:
    return local_today(created_at, zone)


def auto_days(
    start: date,
    end: date,
    today: date,
    joined: date,
    logged: Set[date],
    off: DayOff,
    moon: Set[date],
) -> dict[date, AutoDay]:
    """Auto-rest for the unlogged dates of [start, end] between `joined` and `today`."""
    found: dict[date, AutoDay] = {}
    day, last = max(start, joined), min(end, today)
    while day <= last:
        if day not in logged:
            is_day_off = day.isoweekday() in day_off_on(off, day)
            if day in moon:
                found[day] = AutoDay(AutoKind.MOON, also_day_off=is_day_off)
            elif is_day_off:
                found[day] = AutoDay(AutoKind.DAY_OFF)
        day += timedelta(days=1)
    return found
