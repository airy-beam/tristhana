"""Shala classes (SC-02, ADR-0034). Every call is one statement.

The guarded writes return `Guarded` as SC-01's: `me` None = not a member (`NotFound`), `done`
False = the policy said no (`NotAllowed`); after `done`, a missing value means a cap
(`CapReached`) for a create, or an unknown class (`NotFound`) for an update or an override.
The SQL guard mirrors `can_manage_schedule`.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, time
from typing import Protocol
from uuid import UUID

from tristhana.application.ports.shalas import Guarded
from tristhana.domain.classes import ClassType, Closure, MoonPolicy, Override, Swap
from tristhana.domain.moon import MoonDayKind
from tristhana.domain.rest_days import Weekdays
from tristhana.domain.shalas import Membership


@dataclass(frozen=True, slots=True)
class ClassCaps:
    classes: int  # live series
    closures: int  # future ones
    swaps: int  # future ones


@dataclass(frozen=True, slots=True)
class ClassDraft:
    """A class as written. `city` None = the shala's; only an online class names one (Q124)."""

    type: ClassType
    title: str | None
    online: bool
    city: str | None
    teacher_id: UUID | None
    start: time
    minutes: int
    weekdays: Weekdays
    every: int
    starts_on: date
    ends_on: date | None


@dataclass(frozen=True, slots=True)
class StoredClass(ClassDraft):
    id: UUID


@dataclass(frozen=True, slots=True)
class ScheduleWindow:
    """One read: the caller's side, the shala's settings, and what shapes [start-13, end+13].
    `moon` = the stored moon dates of `coalesce(moon_city, city)` (Q111); `staff` = names."""

    me: Membership
    shala_id: UUID
    name: str
    city: str
    moon_city: str | None
    moon_policy: MoonPolicy
    days_off: Weekdays | None
    classes: tuple[StoredClass, ...]
    overrides: Mapping[tuple[UUID, date], Override]
    closures: tuple[Closure, ...]
    swaps: tuple[Swap, ...]
    moon: frozenset[date]
    staff: Mapping[UUID, str | None]


@dataclass(frozen=True, slots=True)
class MyWindows:
    windows: tuple[ScheduleWindow, ...]
    teachers: frozenset[UUID]  # my linked teachers (ID-04)
    my_moon: frozenset[date]  # moon dates of my effective moon city
    my_moon_kinds: Mapping[date, MoonDayKind] = field(
        default_factory=dict[date, MoonDayKind]
    )  # the same dates with their kind (SC-06)


class ScheduleRepository(Protocol):
    async def window(self, shala: UUID, me: UUID, start: date, end: date) -> ScheduleWindow | None:
        """None: no such shala, or not a member."""
        ...

    async def member_windows(
        self,
        me: UUID,
        start: date,
        end: date,
        staff_only: bool = False,
        moon_city: str | None = None,
        moon_end: date | None = None,
        moon_start: date | None = None,
    ) -> MyWindows:
        """SC-03, one statement: a `window` per shala where `me` is a member (staff first, then
        by name; `staff_only`: staff seats only), my linked teacher ids, and the stored moon
        dates of `moon_city` in [moon_start or start, moon_end or end] (SC-06 reads a wider
        moon range than its classes)."""
        ...

    async def classes_of(self, shala: UUID, me: UUID) -> Guarded[tuple[StoredClass, ...]]: ...

    async def create(
        self, shala: UUID, me: UUID, draft: ClassDraft, caps: ClassCaps, today: date
    ) -> Guarded[StoredClass]: ...

    async def update(
        self, shala: UUID, me: UUID, class_id: UUID, draft: ClassDraft, from_date: date | None
    ) -> Guarded[StoredClass]:
        """With `from_date`: the old series ends the day before, a new one starts on it, and
        overrides on or after it move to the new id. Overrides the resulting rules no longer
        produce are deleted."""
        ...

    async def delete(self, shala: UUID, me: UUID, class_id: UUID) -> Guarded[None]:
        """Idempotent."""
        ...

    async def set_override(
        self, shala: UUID, me: UUID, class_id: UUID, override: Override, keep: bool = False
    ) -> Guarded[bool]:
        """Upserts by (class, rule date), replacing the date's changes; `keep`: the status
        only, an existing move, time and substitute stay. Value False: no such class."""
        ...

    async def clear_override(
        self, shala: UUID, me: UUID, class_id: UUID, on_date: date
    ) -> Guarded[None]:
        """Idempotent."""
        ...

    async def add_closure(
        self, shala: UUID, me: UUID, start: date, end: date, caps: ClassCaps, today: date
    ) -> Guarded[Closure]: ...

    async def remove_closure(self, shala: UUID, me: UUID, closure: UUID) -> Guarded[None]: ...

    async def add_swap(
        self, shala: UUID, me: UUID, swap: Swap, caps: ClassCaps, today: date
    ) -> Guarded[Swap]:
        """The write only: `AddSwap` validates it on a window read first (Q125)."""
        ...

    async def remove_swap(self, shala: UUID, me: UUID, from_date: date) -> Guarded[None]: ...
