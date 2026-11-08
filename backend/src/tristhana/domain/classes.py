"""Shala classes (SC-02, ADR-0034): a weekly rule stored as columns, expanded at read time.

A series is wall clock + an IANA zone + a weekly rule (weekdays, every 1-4 ISO weeks, from/until)
or a single date. Occurrences are derived here, never stored; the UTC instant comes from the
zone on each date, so 06:30 stays 06:30 across a DST change. Precedence per occurrence: a staff
override > a closure > the moon day (per the shala's policy, Q117) > a swap day (Q125). Moon
dates are the stored observed dates (kshaya included): nothing is recomputed here.
"""

from collections.abc import Iterator, Mapping, Sequence, Set
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, time, timedelta
from enum import StrEnum
from uuid import UUID
from zoneinfo import ZoneInfo

from tristhana.domain.rest_days import WEEKDAYS, Weekdays

# Q127: soft caps and the schedule horizon (days).
MAX_CLASSES = 40  # live series per shala
MAX_FUTURE_CLOSURES = 20
MAX_FUTURE_SWAPS = 20
WINDOW_MAX = 31  # days per schedule read
HORIZON = 365  # days ahead of the shala's today
MOVE_MAX = 6  # days an occurrence can move
SWAP_MAX = 6  # days between a swap's two dates
CLOSURE_MAX = 92  # days in one closure, both ends included
TITLE_MAX = 48
MINUTES_MIN, MINUTES_MAX = 15, 480
EVERY_MAX = 4
_MARGIN = timedelta(days=13)  # rule dates read around the window: a move (±6) then a swap (±6)
_DAY_MINUTES = 24 * 60
_BYDAY = ("MO", "TU", "WE", "TH", "FR", "SA", "SU")


class ClassType(StrEnum):
    MYSORE = "mysore"
    LED = "led"
    PRIVATE = "private"  # 1:1, staff only (Q121)
    CONFERENCE = "conference"
    PRANAYAMA = "pranayama"
    CHANTING = "chanting"
    WORKSHOP = "workshop"


class MoonPolicy(StrEnum):
    CLOSED = "closed"
    PRANAYAMA = "pranayama"
    OPEN = "open"


# Q117 (owner): Led is asana practice, so it stops on moon days too. Under OPEN nothing is
# cancelled automatically; the day still carries 🌙.
HELD_ON_MOON: Mapping[MoonPolicy, frozenset[ClassType]] = {
    MoonPolicy.CLOSED: frozenset(),
    MoonPolicy.PRANAYAMA: frozenset(
        {ClassType.PRANAYAMA, ClassType.CONFERENCE, ClassType.CHANTING}
    ),
    MoonPolicy.OPEN: frozenset(ClassType),
}


class OverrideStatus(StrEnum):
    CANCELLED = "cancelled"
    HELD = "held"  # kept despite the moon or a closure (Q126)


class Reason(StrEnum):
    MOON = "moon"
    CLOSURE = "closure"
    CANCELLED = "cancelled"  # by staff


_AUTO = frozenset({Reason.MOON, Reason.CLOSURE})


class InvalidClass(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ClassSeries:
    id: UUID
    type: ClassType
    title: str | None
    online: bool
    zone: str  # IANA; the shala's, or another listed city's for an online class (Q124)
    teacher_id: UUID | None
    start: time
    minutes: int
    weekdays: Weekdays  # empty = a single date on starts_on
    every: int  # weeks
    starts_on: date
    ends_on: date | None


@dataclass(frozen=True, slots=True)
class Override:
    on_date: date  # the rule's date
    status: OverrideStatus | None
    moved_to: date | None = None
    start: time | None = None
    minutes: int | None = None
    teacher_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class Closure:
    id: UUID
    start: date
    end: date  # inclusive

    def covers(self, day: date) -> bool:
        return self.start <= day <= self.end


@dataclass(frozen=True, slots=True)
class Swap:
    from_date: date
    to_date: date


@dataclass(frozen=True, slots=True)
class Occurrence:
    class_id: UUID
    key: date  # the rule's date: the override and (SC-05) attendance key
    on: date  # where it takes place, local to the class zone
    start: time
    end: time
    starts_at: datetime  # UTC
    type: ClassType
    title: str | None
    online: bool
    teacher_id: UUID | None
    substitute: bool
    cancelled: Reason | None
    moved: bool
    swapped_from: date | None
    planned: time | None = None  # the rule's start, for "moved from …"
    swap_reason: Reason | None = None  # why it left `swapped_from` (moon or closure)
    planned_teacher: UUID | None = None  # the rule's teacher, for "covered by …"
    held: bool = False  # staff chose "hold anyway" (Q126): a later change must keep it
    moon: bool = False  # `on` is a moon date of the shala's calendar, whatever the policy (SC-03)
    swapped_to: date | None = None  # kept original on A of a swap: where it went (SC-03)


def check_series(series: ClassSeries) -> ClassSeries:
    s = series
    if not MINUTES_MIN <= s.minutes <= MINUTES_MAX:
        raise InvalidClass("length")
    if s.start.hour * 60 + s.start.minute + s.minutes > _DAY_MINUTES:
        raise InvalidClass("past midnight")
    if not s.weekdays <= WEEKDAYS:
        raise InvalidClass("weekdays")
    if not 1 <= s.every <= EVERY_MAX:
        raise InvalidClass("every")
    if s.ends_on is not None and (s.ends_on < s.starts_on or not s.weekdays):
        raise InvalidClass("until")
    if s.title is not None and not 1 <= len(s.title) <= TITLE_MAX:
        raise InvalidClass("title")
    return s


def rule_dates(series: ClassSeries, start: date, end: date) -> Iterator[date]:
    """The rule's dates in [start, end]; `every` counts ISO weeks from starts_on's week."""
    s = series
    first = max(start, s.starts_on)
    last = end if s.ends_on is None else min(end, s.ends_on)
    if not s.weekdays:
        if first <= s.starts_on <= last:
            yield s.starts_on
        return
    anchor = s.starts_on - timedelta(days=s.starts_on.weekday())
    day = first
    while day <= last:
        if day.isoweekday() in s.weekdays and ((day - anchor).days // 7) % s.every == 0:
            yield day
        day += timedelta(days=1)


def wall_to_utc(day: date, at: time, zone: str) -> datetime:
    """fold=0: a time in the spring gap shifts forward by the gap; an ambiguous one is the first."""
    return datetime.combine(day, at, ZoneInfo(zone)).astimezone(UTC)


def to_rrule(series: ClassSeries) -> str | None:
    s = series
    if not s.weekdays:
        return None
    days = ",".join(_BYDAY[d - 1] for d in sorted(s.weekdays))
    rule = f"FREQ=WEEKLY;INTERVAL={s.every};BYDAY={days}"
    if s.ends_on is not None:
        rule += f";UNTIL={s.ends_on:%Y%m%d}"
    return rule


def check_swap(
    a: date,
    b: date,
    today: date,
    days_off: Weekdays,
    moon: Set[date],
    closures: Sequence[Closure],
    types_on: Mapping[date, Set[ClassType]],
) -> None:
    """Q125: `types_on[a]` are the types that would move from A (the caller applies the policy)."""
    if not 0 < abs((b - a).days) <= SWAP_MAX:
        raise InvalidClass("swap distance")
    if not today <= b <= today + timedelta(days=HORIZON):
        raise InvalidClass("swap date")
    if b in moon or any(c.covers(b) for c in closures):
        raise InvalidClass("swap target")
    if b.isoweekday() not in days_off and types_on.get(a, set()) & types_on.get(b, set()):
        raise InvalidClass("swap target busy")


def expand(
    series: Sequence[ClassSeries],
    overrides: Mapping[tuple[UUID, date], Override],
    closures: Sequence[Closure],
    swaps: Sequence[Swap],
    moon: Set[date],
    policy: MoonPolicy,
    start: date,
    end: date,
    staff_only: bool,
    keep_swapped: bool = False,
) -> list[Occurrence]:
    """`staff_only`: whether the viewer may see 1:1 classes (staff do, Q121). `keep_swapped`
    (SC-03): also return the auto-cancelled original on a swap's A, naming B in `swapped_to`."""
    swap_to = {s.from_date: s.to_date for s in swaps}
    held = HELD_ON_MOON[policy]

    def auto_reason(s: ClassSeries, day: date) -> Reason | None:
        if any(c.covers(day) for c in closures):
            return Reason.CLOSURE
        if day in moon and s.type not in held:
            return Reason.MOON
        return None

    out: list[Occurrence] = []
    for s in series:
        if s.type is ClassType.PRIVATE and not staff_only:
            continue
        for key in rule_dates(s, start - _MARGIN, end + _MARGIN):
            ov = overrides.get((s.id, key))
            on, at, minutes, teacher = key, s.start, s.minutes, s.teacher_id
            moved = False
            status = None
            if ov is not None:
                status = ov.status
                if ov.moved_to is not None and ov.moved_to != key:
                    on, moved = ov.moved_to, True
                if ov.start is not None and ov.start != s.start:
                    at, moved = ov.start, True
                if ov.minutes is not None and ov.minutes != s.minutes:
                    minutes, moved = ov.minutes, True
                if ov.teacher_id is not None:
                    teacher = ov.teacher_id
            if status is OverrideStatus.CANCELLED:
                cancelled: Reason | None = Reason.CANCELLED
            elif status is OverrideStatus.HELD:
                cancelled = None
            else:
                cancelled = auto_reason(s, on)
            target = swap_to.get(on) if cancelled in _AUTO else None
            keep_a = target is not None and keep_swapped and start <= on <= end
            if not keep_a and not start <= (on if target is None else target) <= end:
                continue  # only the window's dates are built (the margin is wide)
            base = Occurrence(
                class_id=s.id,
                key=key,
                on=on,
                start=at,
                end=(datetime.combine(on, at) + timedelta(minutes=minutes)).time(),
                starts_at=wall_to_utc(on, at, s.zone),
                type=s.type,
                title=s.title,
                online=s.online,
                teacher_id=teacher,
                substitute=teacher != s.teacher_id,
                cancelled=cancelled,
                moved=moved,
                swapped_from=None,
                planned=s.start,
                planned_teacher=s.teacher_id,
                held=status is OverrideStatus.HELD,
                moon=on in moon,
            )
            if target is None:
                out.append(base)
                continue
            if keep_a:
                out.append(replace(base, swapped_to=target))
            if start <= target <= end:
                out.append(
                    replace(
                        base,
                        on=target,
                        starts_at=wall_to_utc(target, at, s.zone),
                        # a safety net: B was checked at creation
                        cancelled=auto_reason(s, target),
                        swapped_from=on,
                        swap_reason=cancelled,
                        moon=target in moon,
                    )
                )
    out.sort(key=lambda o: (o.starts_at, str(o.class_id)))
    return out


@dataclass(frozen=True, slots=True)
class Shift:
    """A change of (class offset - viewer offset) on `on` (SC-03, Q140). `minutes` > 0: the
    class comes earlier for the viewer; < 0: later."""

    zone: str
    on: date
    minutes: int


def offset_gap(zone: str, viewer: str, day: date) -> timedelta:
    """Class offset - viewer offset at the viewer's local noon of `day`."""
    noon = datetime.combine(day, time(12), ZoneInfo(viewer))
    here = noon.utcoffset() or timedelta(0)
    there = noon.astimezone(ZoneInfo(zone)).utcoffset() or timedelta(0)
    return there - here


def shifts(zones: Set[str], viewer: str, start: date, end: date) -> tuple[Shift, ...]:
    """Day d against d - 1 for d in [start, end]; both sides moving together gives nothing."""
    out: list[Shift] = []
    for zone in sorted(zones):
        before = offset_gap(zone, viewer, start - timedelta(days=1))
        day = start
        while day <= end:
            gap = offset_gap(zone, viewer, day)
            if gap != before:
                out.append(Shift(zone, day, int((gap - before).total_seconds()) // 60))
            before, day = gap, day + timedelta(days=1)
    out.sort(key=lambda s: (s.on, s.zone))
    return tuple(out)


def local_date(o: Occurrence, zone: str) -> date:
    """The date of `o.starts_at` in `zone` (rows sit under the viewer's date)."""
    return o.starts_at.astimezone(ZoneInfo(zone)).date()
