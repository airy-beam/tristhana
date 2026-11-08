"""In-memory `ScheduleRepository` (`Storage.schedule`, SC-02 spec §3). Its own module, like
`shala_fakes.py`, so the existing suites keep collecting before SC-02 exists:
`InMemoryStorage.schedule` loads it on first use.

The port shapes the spec leaves open are assumed here, and are the ones to adjust with the port
(`tristhana.application.ports.classes`):

- `ClassCaps(classes, closures, swaps)`;
- `ClassDraft(type, title, online, city, teacher_id, start, minutes, weekdays, every,
  starts_on, ends_on)`: `ClassIn`; `city` None = the shala's city (only an online class names
  one, Q124);
- `StoredClass(id, <the ClassDraft fields>)`: a row of `shala_class`, `ClassOut` minus `rrule`;
- `ScheduleWindow(me, shala_id, name, city, moon_city, moon_policy, days_off, classes,
  overrides, closures, swaps, moon, staff)`: the one-statement read. `overrides` is a mapping
  `(class_id, on_date) -> Override`, `moon` the stored moon dates of
  `coalesce(moon_city, city)` within the window ± 7 days, `staff` the staff names by id;
- the guarded writes return `Guarded` (SC-01): `me` None = not a member, `done` False = the
  policy said no, `value` None after `done` = capped (`CapReached`) or, for an update or an
  override, an unknown class (`NotFound`). `add_swap` raises `InvalidClass` from `check_swap`
  with the data read in the same statement.

The guards call `application/policies.py` themselves; `test_db_classes.py` pins the SQL to the
same matrix.
"""

from dataclasses import dataclass, field, replace
from datetime import date, time, timedelta
from typing import Any
from uuid import UUID, uuid4

from tests.fakes import InMemoryMoon
from tests.shala_fakes import InMemoryShalas
from tristhana.application.policies import can_manage_schedule
from tristhana.application.ports.classes import (
    ClassCaps,
    ClassDraft,
    ScheduleWindow,
    StoredClass,
)
from tristhana.application.ports.shalas import Guarded
from tristhana.domain.classes import (
    ClassSeries,
    ClassType,
    Closure,
    MoonPolicy,
    Override,
    Reason,
    Swap,
    check_swap,
    expand,
    rule_dates,
)
from tristhana.domain.shalas import Membership

MARGIN = timedelta(days=13)


@dataclass
class InMemorySchedule:
    shalas: InMemoryShalas
    moon: InMemoryMoon
    classes: dict[UUID, tuple[UUID, StoredClass]] = field(
        default_factory=dict[UUID, tuple[UUID, StoredClass]]
    )
    overrides: dict[tuple[UUID, date], Override] = field(
        default_factory=dict[tuple[UUID, date], Override]
    )
    closures: dict[UUID, tuple[UUID, Closure]] = field(
        default_factory=dict[UUID, tuple[UUID, Closure]]
    )
    swaps: dict[tuple[UUID, date], Swap] = field(default_factory=dict[tuple[UUID, date], Swap])
    reads: list[str] = field(default_factory=list[str])
    writes: list[str] = field(default_factory=list[str])

    # Seeding (not part of the port).

    def add_class(self, shala: UUID, **kw: Any) -> StoredClass:
        fields: dict[str, Any] = {
            "type": ClassType.MYSORE,
            "title": None,
            "online": False,
            "city": None,
            "teacher_id": None,
            "start": time(6, 0),
            "minutes": 210,
            "weekdays": frozenset({1, 2, 3, 4, 5}),
            "every": 1,
            "starts_on": date(2026, 11, 2),
            "ends_on": None,
        }
        fields.update(kw)
        row = StoredClass(id=uuid4(), **fields)
        self.classes[row.id] = (shala, row)
        return row

    def add_override(self, class_id: UUID, override: Override) -> None:
        self.overrides[(class_id, override.on_date)] = override

    def seed_closure(self, shala: UUID, start: date, end: date) -> Closure:
        closure = Closure(uuid4(), start, end)
        self.closures[closure.id] = (shala, closure)
        return closure

    def of(self, shala: UUID) -> list[StoredClass]:
        return [row for s, row in self.classes.values() if s == shala]

    # The port.

    async def window(self, shala: UUID, me: UUID, start: date, end: date) -> ScheduleWindow | None:
        self._call("window")
        return self._read(shala, me, start, end)

    async def staff_windows(self, me: UUID, start: date, end: date) -> tuple[ScheduleWindow, ...]:
        self._call("staff_windows")
        ids = [s for (s, a) in self.shalas.staff if a == me]
        found = (self._read(s, me, start, end) for s in ids)
        return tuple(sorted((w for w in found if w), key=lambda w: (w.name, str(w.shala_id))))

    def _read(self, shala: UUID, me: UUID, start: date, end: date) -> ScheduleWindow | None:
        m = self.shalas.membership(shala, me)
        if m is None:
            return None
        row = self.shalas.shalas[shala]
        lo, hi = start - MARGIN, end + MARGIN
        moon_city = row.moon_city or row.city  # Q111: a removed moon city falls back
        return ScheduleWindow(
            me=m,
            shala_id=shala,
            name=row.name,
            city=row.city,
            moon_city=row.moon_city,
            moon_policy=MoonPolicy(getattr(row, "moon_policy", "closed")),
            days_off=getattr(row, "days_off", None),
            classes=tuple(
                c
                for c in self.of(shala)
                if c.starts_on <= hi and (c.ends_on is None or c.ends_on >= lo)
            ),
            overrides={
                k: o
                for k, o in self.overrides.items()
                if k[0] in self._ids(shala) and lo <= k[1] <= hi
            },
            closures=tuple(
                c for s, c in self.closures.values() if s == shala and c.start <= hi and c.end >= lo
            ),
            swaps=tuple(
                sw
                for (s, _), sw in self.swaps.items()
                if s == shala and (lo <= sw.from_date <= hi or lo <= sw.to_date <= hi)
            ),
            moon=frozenset(
                d.date for d in self.moon.days_by_location.get(moon_city, []) if lo <= d.date <= hi
            ),
            staff={a: self.shalas._name(a) for a in self.shalas.staff_of(shala)},  # pyright: ignore[reportPrivateUsage]
        )

    async def classes_of(self, shala: UUID, me: UUID) -> Guarded[tuple[StoredClass, ...]]:
        self._call("classes_of")
        m = self._manager(shala, me)
        if m is None or not can_manage_schedule(m):
            return Guarded(m, False)
        return Guarded(m, True, tuple(sorted(self.of(shala), key=lambda c: (c.starts_on, c.start))))

    async def create(
        self, shala: UUID, me: UUID, draft: ClassDraft, caps: ClassCaps, today: date
    ) -> Guarded[StoredClass]:
        self._call("create")
        m = self._manager(shala, me)
        if m is None or not can_manage_schedule(m):
            return Guarded(m, False)
        live = [c for c in self.of(shala) if c.ends_on is None or c.ends_on >= today]
        if len(live) >= caps.classes:
            return Guarded(m, True, None)
        row = StoredClass(id=uuid4(), **_fields(draft))
        self.classes[row.id] = (shala, row)
        self.writes.append("create")
        return Guarded(m, True, row)

    async def update(
        self,
        shala: UUID,
        me: UUID,
        class_id: UUID,
        draft: ClassDraft,
        from_date: date | None,
    ) -> Guarded[StoredClass]:
        """Without `from`: the row changes. With it: the old series ends the day before and a
        new one starts on it; overrides on or after `from` move to the new id. Overrides the
        resulting rule no longer produces are deleted (ADR-0034)."""
        self._call("update")
        m = self._manager(shala, me)
        if m is None or not can_manage_schedule(m):
            return Guarded(m, False)
        found = self.classes.get(class_id)
        if found is None or found[0] != shala:
            return Guarded(m, True, None)
        old = found[1]
        if from_date is None:
            new = StoredClass(id=old.id, **_fields(draft))
            self.classes[old.id] = (shala, new)
        else:
            self.classes[old.id] = (shala, replace(old, ends_on=from_date - timedelta(days=1)))
            new = replace(StoredClass(id=uuid4(), **_fields(draft)), starts_on=from_date)
            self.classes[new.id] = (shala, new)
            for key in [k for k in self.overrides if k[0] == old.id and k[1] >= from_date]:
                self.overrides[(new.id, key[1])] = self.overrides.pop(key)
        for cid in {old.id, new.id}:
            self._drop_stale(cid)
        self.writes.append("update")
        return Guarded(m, True, new)

    async def delete(self, shala: UUID, me: UUID, class_id: UUID) -> Guarded[None]:
        self._call("delete")
        m = self._manager(shala, me)
        if m is None or not can_manage_schedule(m):
            return Guarded(m, False)
        found = self.classes.get(class_id)
        if found is not None and found[0] == shala:
            del self.classes[class_id]
            for key in [k for k in self.overrides if k[0] == class_id]:
                del self.overrides[key]
            self.writes.append("delete")
        return Guarded(m, True)

    async def set_override(
        self, shala: UUID, me: UUID, class_id: UUID, override: Override, keep: bool = False
    ) -> Guarded[bool]:
        self._call("set_override")
        m = self._manager(shala, me)
        if m is None or not can_manage_schedule(m):
            return Guarded(m, False)
        found = self.classes.get(class_id)
        if found is None or found[0] != shala:
            return Guarded(m, True, False)
        old = self.overrides.get((class_id, override.on_date))
        if old is not None and keep:
            override = replace(old, status=override.status)  # keeps a move and a substitute
        self.overrides[(class_id, override.on_date)] = override
        self.writes.append("set_override")
        return Guarded(m, True, True)

    async def clear_override(
        self, shala: UUID, me: UUID, class_id: UUID, on_date: date
    ) -> Guarded[None]:
        self._call("clear_override")
        m = self._manager(shala, me)
        if m is None or not can_manage_schedule(m):
            return Guarded(m, False)
        found = self.classes.get(class_id)
        if (
            found is not None
            and found[0] == shala
            and self.overrides.pop((class_id, on_date), None) is not None
        ):
            self.writes.append("clear_override")
        return Guarded(m, True)

    async def add_closure(
        self, shala: UUID, me: UUID, start: date, end: date, caps: ClassCaps, today: date
    ) -> Guarded[Closure]:
        self._call("add_closure")
        m = self._manager(shala, me)
        if m is None or not can_manage_schedule(m):
            return Guarded(m, False)
        future = [c for s, c in self.closures.values() if s == shala and c.end >= today]
        if len(future) >= caps.closures:
            return Guarded(m, True, None)
        closure = Closure(uuid4(), start, end)
        self.closures[closure.id] = (shala, closure)
        self.writes.append("add_closure")
        return Guarded(m, True, closure)

    async def remove_closure(self, shala: UUID, me: UUID, closure: UUID) -> Guarded[None]:
        self._call("remove_closure")
        m = self._manager(shala, me)
        if m is None or not can_manage_schedule(m):
            return Guarded(m, False)
        found = self.closures.get(closure)
        if found is not None and found[0] == shala:
            del self.closures[closure]
            self.writes.append("remove_closure")
        return Guarded(m, True)

    async def add_swap(
        self, shala: UUID, me: UUID, swap: Swap, caps: ClassCaps, today: date
    ) -> Guarded[Swap]:
        self._call("add_swap")
        m = self._manager(shala, me)
        if m is None or not can_manage_schedule(m):
            return Guarded(m, False)
        future = [s for (sh, _), s in self.swaps.items() if sh == shala and s.from_date >= today]
        if len(future) >= caps.swaps:
            return Guarded(m, True, None)
        a, b = swap.from_date, swap.to_date
        window = await self.window(shala, me, min(a, b), max(a, b))
        assert window is not None
        series = _series(window)
        on_a = expand(
            series,
            dict(window.overrides),
            list(window.closures),
            [],
            window.moon,
            window.moon_policy,
            a,
            a,
            True,
        )
        on_b = expand(series, {}, [], [], frozenset(), MoonPolicy.OPEN, b, b, True)
        moving = {o.type for o in on_a if o.cancelled in (Reason.MOON, Reason.CLOSURE)}
        check_swap(
            a,
            b,
            today,
            window.days_off or frozenset(),
            window.moon,
            list(window.closures),
            {a: moving, b: {o.type for o in on_b}},
        )
        self.swaps[(shala, a)] = swap
        self.writes.append("add_swap")
        return Guarded(m, True, swap)

    async def remove_swap(self, shala: UUID, me: UUID, from_date: date) -> Guarded[None]:
        self._call("remove_swap")
        m = self._manager(shala, me)
        if m is None or not can_manage_schedule(m):
            return Guarded(m, False)
        if self.swaps.pop((shala, from_date), None) is not None:
            self.writes.append("remove_swap")
        return Guarded(m, True)

    # Internals.

    def _call(self, name: str) -> None:
        self.shalas._call(name)  # pyright: ignore[reportPrivateUsage]
        self.reads.append(name)

    def _manager(self, shala: UUID, me: UUID) -> Membership | None:
        return self.shalas.membership(shala, me)

    def _ids(self, shala: UUID) -> set[UUID]:
        return {c.id for c in self.of(shala)}

    def _drop_stale(self, class_id: UUID) -> None:
        found = self.classes.get(class_id)
        if found is None:
            return
        series = _as_series(found[1], "UTC")
        for key in [k for k in self.overrides if k[0] == class_id]:
            if key[1] not in set(rule_dates(series, key[1], key[1])):
                del self.overrides[key]


def _fields(draft: ClassDraft) -> dict[str, Any]:
    return {
        name: getattr(draft, name)
        for name in (
            "type",
            "title",
            "online",
            "city",
            "teacher_id",
            "start",
            "minutes",
            "weekdays",
            "every",
            "starts_on",
            "ends_on",
        )
    }


def _as_series(row: StoredClass, zone: str) -> ClassSeries:
    return ClassSeries(
        id=row.id,
        type=row.type,
        title=row.title,
        online=row.online,
        zone=zone,
        teacher_id=row.teacher_id,
        start=row.start,
        minutes=row.minutes,
        weekdays=frozenset(row.weekdays),
        every=row.every,
        starts_on=row.starts_on,
        ends_on=row.ends_on,
    )


def _series(window: ScheduleWindow) -> list[ClassSeries]:
    from tests.fakes import cities

    def zone(slug: str) -> str:
        found = cities().find(slug)
        assert found is not None, slug
        return found.location.tz

    return [_as_series(c, zone(c.city or window.city)) for c in window.classes]
