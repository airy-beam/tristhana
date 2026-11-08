"""Shala classes (SC-02, ADR-0034): both adapters use these.

A schedule is one window read, expanded in the domain in the class zone (the shala's city, or
another listed city for an online class, Q124). Its bounds use the shala's local today; writes
bound dates by the caller's today (one statement each, and a day apart at most). No use case
here reads a log: a class is never a log entry.
"""

import datetime as _dt
from dataclasses import dataclass, replace
from datetime import date, timedelta
from enum import StrEnum
from uuid import UUID

from tristhana.application.policies import (
    NotAllowed,
    NotFound,
    Principal,
    can_manage_schedule,
    can_view_private_classes,
)
from tristhana.application.ports.classes import (
    ClassCaps,
    ClassDraft,
    MyWindows,
    ScheduleRepository,
    ScheduleWindow,
    StoredClass,
)
from tristhana.application.ports.i18n import Translator
from tristhana.application.ports.shalas import CapReached, Guarded, ShalaRepository
from tristhana.application.ports.storage import Clock
from tristhana.application.rest_days import DayOffSaved, SetDayOff
from tristhana.application.settings import caller_today
from tristhana.domain.accounts import moon_follow_of
from tristhana.domain.classes import (
    CLOSURE_MAX,
    HORIZON,
    MAX_CLASSES,
    MAX_FUTURE_CLOSURES,
    MAX_FUTURE_SWAPS,
    MINUTES_MAX,
    MINUTES_MIN,
    MOVE_MAX,
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
    Shift,
    Swap,
    check_series,
    check_swap,
    expand,
    local_date,
    shifts,
)
from tristhana.domain.days import local_today
from tristhana.domain.locale import Locale
from tristhana.domain.moon import Cities, UnknownLocation
from tristhana.domain.rest_days import Weekdays

DAY_MINUTES = 24 * 60
CAPS = ClassCaps(classes=MAX_CLASSES, closures=MAX_FUTURE_CLOSURES, swaps=MAX_FUTURE_SWAPS)
BACK = timedelta(days=7)  # how far back a schedule may start
MY_DAYS = 7  # "My schedule": a page is a week at most (Q139)
_READ = timedelta(days=2)  # offsets span -12..+14: a class on my date is within 2 of its own
_DAY = timedelta(days=1)
AHEAD = timedelta(days=1)  # how far the caller's date may run ahead of the shala's


_CONTEXT = {ClassType.MYSORE: "mysore", ClassType.LED: "led", ClassType.PRIVATE: "private"}


def type_name(t: Translator, locale: Locale, type: ClassType) -> str:
    """Mysore, Led and 1:1 reuse the practice context words; the rest have their own."""
    context = _CONTEXT.get(type)
    if context is not None:
        return t.t(locale, f"context-{context}")
    return t.t(locale, "class-type", type=type.value)


class BadWindow(ValueError):
    """`days` outside 1-31, or `from` outside [today - 7, today + 365] (the shala's today)."""


@dataclass(frozen=True, slots=True)
class ScheduleDay:
    date: _dt.date
    moon: bool  # 🌙 shows under every policy
    day_off: bool
    swap_from: _dt.date | None  # this day holds the moon-day classes of that date


@dataclass(frozen=True, slots=True)
class Schedule:
    shala_id: UUID
    name: str
    zone: str  # the shala's IANA zone (the header label)
    city: str
    moon_policy: MoonPolicy
    days_off: Weekdays | None
    today: date  # the shala's
    days: tuple[ScheduleDay, ...]
    occurrences: tuple[Occurrence, ...]
    staff: dict[UUID, str | None]  # teacher names by id
    manage: bool  # `can_manage_schedule`
    closures: tuple[Closure, ...] = ()  # those touching the window, for the Mini App's list


def _unwrap[T](guarded: Guarded[T]) -> T | None:
    if guarded.me is None:
        raise NotFound
    if not guarded.done:
        raise NotAllowed
    return guarded.value


def _zone(cities: Cities, slug: str) -> str:
    found = cities.find(slug)
    if found is None:
        raise UnknownLocation(slug)
    return found.location.tz


def _series(window: ScheduleWindow, cities: Cities | None) -> list[ClassSeries]:
    """`cities` None: every class in UTC, enough for which dates hold which types."""
    return [
        ClassSeries(
            id=c.id,
            type=c.type,
            title=c.title,
            online=c.online,
            zone="UTC" if cities is None else _zone(cities, c.city or window.city),
            teacher_id=c.teacher_id,
            start=c.start,
            minutes=c.minutes,
            weekdays=frozenset(c.weekdays),
            every=c.every,
            starts_on=c.starts_on,
            ends_on=c.ends_on,
        )
        for c in window.classes
    ]


def _expand(
    window: ScheduleWindow,
    cities: Cities | None,
    start: date,
    end: date,
    keep_swapped: bool = False,
) -> list[Occurrence]:
    return expand(
        _series(window, cities),
        window.overrides,
        window.closures,
        window.swaps,
        window.moon,
        window.moon_policy,
        start,
        end,
        can_view_private_classes(window.me),
        keep_swapped=keep_swapped,
    )


def _checked(draft: ClassDraft, cities: Cities) -> ClassDraft:
    """Raises `InvalidClass`, `UnknownLocation`."""
    if draft.city is not None:
        if not draft.online:
            raise InvalidClass("an offline class runs in the shala's zone")
        _zone(cities, draft.city)
    title = (draft.title or "").strip() or None
    draft = replace(draft, title=title, weekdays=frozenset(draft.weekdays))
    check_series(
        ClassSeries(
            id=UUID(int=0),
            type=draft.type,
            title=draft.title,
            online=draft.online,
            zone="UTC",
            teacher_id=draft.teacher_id,
            start=draft.start,
            minutes=draft.minutes,
            weekdays=draft.weekdays,
            every=draft.every,
            starts_on=draft.starts_on,
            ends_on=draft.ends_on,
        )
    )
    return draft


def _within(day: date, today: date) -> None:
    """[yesterday, today + 365] by the caller's date: staff a date ahead of the shala (Europe
    for a Hawaii shala) can still change the shala's today (review fix)."""
    if not today - AHEAD <= day <= today + timedelta(days=HORIZON):
        raise InvalidClass("date")


class GetSchedule:
    def __init__(self, schedule: ScheduleRepository, clock: Clock, cities: Cities) -> None:
        self._schedule, self._clock, self._cities = schedule, clock, cities

    async def execute(
        self, principal: Principal, shala: UUID, start: date | None, days: int, skip: int = 0
    ) -> Schedule:
        """`start` None: the shala's today plus `skip` days (the bot's weeks). Raises
        `BadWindow`, `NotFound`. One read."""
        if not 1 <= days <= WINDOW_MAX:
            raise BadWindow(str(days))
        now = self._clock.now()
        if start is None:  # a day either side of the UTC date holds every zone's today
            lo = now.date() + timedelta(days=skip - 1)
            hi = lo + timedelta(days=days + 1)
        else:
            lo, hi = start, start + timedelta(days=days - 1)
        window = await self._schedule.window(shala, principal.account.id, lo, hi)
        if window is None:
            raise NotFound
        zone = _zone(self._cities, window.city)
        today = local_today(now, zone)
        if start is None:
            start = today + timedelta(days=skip)
        end = start + timedelta(days=days - 1)
        if not today - BACK <= start <= today + timedelta(days=HORIZON):
            raise BadWindow(start.isoformat())
        off = window.days_off or frozenset()
        swap_to = {s.to_date: s.from_date for s in window.swaps}
        return Schedule(
            shala_id=window.shala_id,
            name=window.name,
            zone=zone,
            city=window.city,
            moon_policy=window.moon_policy,
            days_off=window.days_off,
            today=today,
            days=tuple(
                ScheduleDay(day, day in window.moon, day.isoweekday() in off, swap_to.get(day))
                for day in (start + timedelta(days=i) for i in range(days))
            ),
            occurrences=tuple(_expand(window, self._cities, start, end)),
            staff=dict(window.staff),
            manage=can_manage_schedule(window.me),
            closures=tuple(c for c in window.closures if c.end >= start and c.start <= end),
        )


class Teaching(StrEnum):
    TEACHING = "teaching"  # mine, as planned
    COVERING = "covering"  # I substitute for someone
    COVERED = "covered"  # someone substitutes for me


def _role(o: Occurrence, me: UUID) -> Teaching | None:
    if o.teacher_id == me:
        return Teaching.COVERING if o.substitute else Teaching.TEACHING
    if o.substitute and o.planned_teacher == me:
        return Teaching.COVERED
    return None


class Only(StrEnum):
    """The "My schedule" filters (Q138)."""

    ALL = "all"
    TEACHERS = "teachers"  # rows my linked teachers teach, or are covered for
    MINE = "mine"  # rows I teach, cover or have covered ("I teach")


@dataclass(frozen=True, slots=True)
class MyRow:
    shala_id: UUID
    occurrence: Occurrence
    zone: str  # the class's IANA zone (the second label)
    city: str  # the class's city slug
    role: Teaching | None
    my_teacher: bool  # one of my linked teachers teaches it that date, or is covered on it


@dataclass(frozen=True, slots=True)
class MyDay:
    date: _dt.date
    my_moon: bool  # a moon day of my own effective calendar (MD-02)


@dataclass(frozen=True, slots=True)
class ShalaRef:
    id: UUID
    name: str
    city: str
    zone: str
    staff: bool  # I am on its staff


@dataclass(frozen=True, slots=True)
class MySchedule:
    zone: str  # mine, or my first shala's when `zone_known` is False (Q141)
    zone_known: bool
    today: date  # in `zone`
    moon_city: str  # my effective moon city
    days: tuple[MyDay, ...]
    shalas: tuple[ShalaRef, ...]  # staff first, then by name
    has_teachers: bool
    is_staff: bool
    rows: tuple[MyRow, ...]
    shifts: tuple[Shift, ...]
    staff: dict[UUID, dict[UUID, str | None]]  # teacher names per shala


def my_rows(
    found: MyWindows,
    cities: Cities,
    zone: str,
    first: date,
    end: date,
    me: UUID,
    only: Only,
) -> tuple[list[MyRow], list[ShalaRef], dict[UUID, dict[UUID, str | None]]]:
    """The rows of my shalas whose instant falls on [first, end] in `zone`, sorted by instant;
    the shalas (staff first, then by name) and their staff names. Shared by My schedule and
    the calendar feed (SC-06)."""
    rows: list[MyRow] = []
    refs: list[ShalaRef] = []
    names: dict[UUID, dict[UUID, str | None]] = {}
    for w in found.windows:
        refs.append(ShalaRef(w.shala_id, w.name, w.city, _zone(cities, w.city), w.me.staff))
        names[w.shala_id] = dict(w.staff)
        slugs = {c.id: c.city or w.city for c in w.classes}
        zones = {c: _zone(cities, slug) for c, slug in slugs.items()}
        for o in _expand(w, cities, first - _READ, end + _READ, keep_swapped=True):
            if not first <= local_date(o, zone) <= end:
                continue
            mine = o.teacher_id in found.teachers or (
                o.substitute and o.planned_teacher in found.teachers
            )
            row = MyRow(w.shala_id, o, zones[o.class_id], slugs[o.class_id], _role(o, me), mine)
            if only is Only.TEACHERS and not row.my_teacher:
                continue
            if only is Only.MINE and row.role is None:
                continue
            rows.append(row)
    rows.sort(key=lambda r: (r.occurrence.starts_at, str(r.shala_id), str(r.occurrence.class_id)))
    return rows, refs, names


class GetMySchedule:
    """SC-03 (ADR-0035): every shala where I am a member, in my zone. One read; my moon city
    comes from the loaded account (`moon_follow_of`), so no log, rest or 🌸 data is read."""

    def __init__(self, schedule: ScheduleRepository, clock: Clock, cities: Cities) -> None:
        self._schedule, self._clock, self._cities = schedule, clock, cities

    async def execute(
        self,
        principal: Principal,
        start: date | None,
        days: int = MY_DAYS,
        skip: int = 0,
        only: Only = Only.ALL,
    ) -> MySchedule:
        """`start` None: my today plus `skip` days. Raises `BadWindow`."""
        if not 1 <= days <= MY_DAYS:
            raise BadWindow(str(days))
        account, now = principal.account, self._clock.now()
        me = account.id
        moon_city = moon_follow_of(account, self._cities).city.slug
        known = account.timezone
        if known is not None:
            base = _first(start, skip, local_today(now, known))  # a bad window reads nothing
            lo, hi = base - _READ, base + timedelta(days=days - 1) + _READ
        else:  # every zone's today is within a day of the UTC date
            base = now.date() + timedelta(days=skip) if start is None else start
            lo, hi = base - _DAY - _READ, base + timedelta(days=days) + _READ
        found: MyWindows = await self._schedule.member_windows(me, lo, hi, moon_city=moon_city)
        windows = found.windows
        zone: str = known or (_zone(self._cities, windows[0].city) if windows else "UTC")
        today = local_today(now, zone)
        first = _first(start, skip, today)
        end = first + timedelta(days=days - 1)
        rows, refs, names = my_rows(found, self._cities, zone, first, end, me, only)
        return MySchedule(
            zone=zone,
            zone_known=known is not None,
            today=today,
            moon_city=moon_city,
            days=tuple(
                MyDay(d, d in found.my_moon)
                for d in (first + timedelta(days=i) for i in range(days))
            ),
            shalas=tuple(refs),
            has_teachers=bool(found.teachers),
            is_staff=any(r.staff for r in refs),
            rows=tuple(rows),
            shifts=shifts({r.zone for r in rows}, zone, first, end),
            staff=names,
        )


def _first(start: date | None, skip: int, today: date) -> date:
    """The window's first day: `start`, or `today` plus `skip`; within [today - 7, today + 365]."""
    first = today + timedelta(days=skip) if start is None else start
    if not today - BACK <= first <= today + timedelta(days=HORIZON):
        raise BadWindow(first.isoformat())
    return first


class ListClasses:
    def __init__(self, schedule: ScheduleRepository) -> None:
        self._schedule = schedule

    async def execute(self, principal: Principal, shala: UUID) -> tuple[StoredClass, ...]:
        return _unwrap(await self._schedule.classes_of(shala, principal.account.id)) or ()


class CreateClass:
    def __init__(self, schedule: ScheduleRepository, clock: Clock, cities: Cities) -> None:
        self._schedule, self._clock, self._cities = schedule, clock, cities

    async def execute(self, principal: Principal, shala: UUID, draft: ClassDraft) -> StoredClass:
        """Raises `InvalidClass`, `UnknownLocation`, `CapReached`, `NotFound`, `NotAllowed`."""
        draft = _checked(draft, self._cities)
        today = caller_today(principal, self._clock)
        created = _unwrap(
            await self._schedule.create(shala, principal.account.id, draft, CAPS, today)
        )
        if created is None:
            raise CapReached
        return created


class UpdateClass:
    def __init__(self, schedule: ScheduleRepository, clock: Clock, cities: Cities) -> None:
        self._schedule, self._clock, self._cities = schedule, clock, cities

    async def execute(
        self,
        principal: Principal,
        shala: UUID,
        class_id: UUID,
        draft: ClassDraft,
        from_date: date | None = None,
    ) -> StoredClass:
        """`from_date`: "applies from" (a split, ADR-0034); None = all dates. The result has a
        new id after a split. `draft.starts_on` is the series' own: a `from` on or before it, or
        on a one-off, changes all dates and never moves the start (review fix)."""
        if from_date is not None:
            _within(from_date, caller_today(principal, self._clock))
            if draft.ends_on is not None and draft.ends_on < from_date:
                raise InvalidClass("until")
        draft = _checked(draft, self._cities)
        updated = _unwrap(
            await self._schedule.update(shala, principal.account.id, class_id, draft, from_date)
        )
        if updated is None:
            raise NotFound
        return updated


class DeleteClass:
    def __init__(self, schedule: ScheduleRepository) -> None:
        self._schedule = schedule

    async def execute(self, principal: Principal, shala: UUID, class_id: UUID) -> None:
        _unwrap(await self._schedule.delete(shala, principal.account.id, class_id))


class SetOverride:
    def __init__(self, schedule: ScheduleRepository, clock: Clock) -> None:
        self._schedule, self._clock = schedule, clock

    async def execute(
        self,
        principal: Principal,
        shala: UUID,
        class_id: UUID,
        key: date,
        override: Override,
        keep: bool = False,
    ) -> None:
        """`key` = the rule's date. The override replaces the date's changes; `keep` (the
        bot's quick hold or cancel) sets the status only. Raises `InvalidClass`, `NotFound`,
        `NotAllowed`."""
        _within(key, caller_today(principal, self._clock))
        o = replace(override, on_date=key)
        changes = (o.moved_to, o.start, o.minutes, o.teacher_id)
        if o.status is OverrideStatus.CANCELLED and any(v is not None for v in changes):
            raise InvalidClass("a cancelled class has no changes")
        if o.moved_to is not None and abs((o.moved_to - key).days) > MOVE_MAX:
            raise InvalidClass("move")
        if o.minutes is not None and not MINUTES_MIN <= o.minutes <= MINUTES_MAX:
            raise InvalidClass("length")
        ends = (
            None
            if o.start is None or o.minutes is None
            else o.start.hour * 60 + o.start.minute + o.minutes
        )
        if ends is not None and ends > DAY_MINUTES:
            raise InvalidClass("past midnight")
        if keep and o.status is OverrideStatus.CANCELLED:
            keep = False  # a cancelled class has no changes
        written = await self._schedule.set_override(shala, principal.account.id, class_id, o, keep)
        if not _unwrap(written):
            raise NotFound


class ClearOverride:
    def __init__(self, schedule: ScheduleRepository) -> None:
        self._schedule = schedule

    async def execute(self, principal: Principal, shala: UUID, class_id: UUID, key: date) -> None:
        _unwrap(await self._schedule.clear_override(shala, principal.account.id, class_id, key))


class AddClosure:
    def __init__(self, schedule: ScheduleRepository, clock: Clock) -> None:
        self._schedule, self._clock = schedule, clock

    async def execute(self, principal: Principal, shala: UUID, start: date, end: date) -> Closure:
        """Both ends included, at most 92 days. Raises `InvalidClass`, `CapReached`, …"""
        today = caller_today(principal, self._clock)
        if end < start or (end - start).days >= CLOSURE_MAX:
            raise InvalidClass("closure")
        _within(end, today)
        _within(max(start, today), today)
        added = _unwrap(
            await self._schedule.add_closure(shala, principal.account.id, start, end, CAPS, today)
        )
        if added is None:
            raise CapReached
        return added


class RemoveClosure:
    def __init__(self, schedule: ScheduleRepository) -> None:
        self._schedule = schedule

    async def execute(self, principal: Principal, shala: UUID, closure: UUID) -> None:
        _unwrap(await self._schedule.remove_closure(shala, principal.account.id, closure))


class AddSwap:
    def __init__(self, schedule: ScheduleRepository, clock: Clock) -> None:
        self._schedule, self._clock = schedule, clock

    async def execute(self, principal: Principal, shala: UUID, a: date, b: date) -> Swap:
        """Q125: hold A's auto-cancelled classes on B. Raises `InvalidClass`, `CapReached`,
        `NotFound`, `NotAllowed`. Two statements: the window read, then the write."""
        me = principal.account.id
        window = await self._schedule.window(shala, me, min(a, b), max(a, b))
        if window is None:
            raise NotFound
        if not can_manage_schedule(window.me):
            raise NotAllowed
        today = caller_today(principal, self._clock) - AHEAD
        on_a = _expand(replace(window, swaps=()), None, a, a)
        moving = {o.type for o in on_a if o.cancelled in (Reason.MOON, Reason.CLOSURE)}
        on_b = _types_on(window, b)
        check_swap(
            a, b, today, window.days_off or frozenset(), window.moon, window.closures,
            {a: moving, b: on_b},
        )  # fmt: skip
        added = _unwrap(await self._schedule.add_swap(shala, me, Swap(a, b), CAPS, today))
        if added is None:
            raise CapReached
        return added


def _types_on(window: ScheduleWindow, day: date) -> set[ClassType]:
    """The types of the classes the rules put on `day` (uncancelled, before any swap)."""
    plain = replace(window, overrides={}, closures=(), swaps=(), moon=frozenset())
    return {o.type for o in _expand(plain, None, day, day)}


class RemoveSwap:
    def __init__(self, schedule: ScheduleRepository) -> None:
        self._schedule = schedule

    async def execute(self, principal: Principal, shala: UUID, from_date: date) -> None:
        _unwrap(await self._schedule.remove_swap(shala, principal.account.id, from_date))


class AdoptShalaDayOff:
    def __init__(self, shalas: ShalaRepository, set_day_off: SetDayOff) -> None:
        self._shalas, self._set_day_off = shalas, set_day_off

    async def execute(self, principal: Principal, shala: UUID) -> DayOffSaved | None:
        """Q109, Q119: one tap, never silent; only for someone who never chose a day off.
        None: nothing to adopt. Raises `NotFound`."""
        card = await self._shalas.card(shala, principal.account.id)
        if card is None:
            raise NotFound
        if not card.days_off or principal.account.day_off.days is not None:
            return None
        return await self._set_day_off.execute(principal, sorted(card.days_off))


@dataclass(frozen=True, slots=True)
class ClassUseCases:
    schedule: GetSchedule
    classes: ListClasses
    create: CreateClass
    update: UpdateClass
    delete: DeleteClass
    override: SetOverride
    clear: ClearOverride
    add_closure: AddClosure
    remove_closure: RemoveClosure
    add_swap: AddSwap
    remove_swap: RemoveSwap
    adopt: AdoptShalaDayOff
    mine: GetMySchedule
