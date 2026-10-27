from dataclasses import dataclass, field
from datetime import date
from typing import Protocol
from uuid import UUID

from tristhana.domain.days import DayLog, DayStatus
from tristhana.domain.diary import DiaryNote
from tristhana.domain.rest_periods import RestPeriod


@dataclass(frozen=True, slots=True)
class History:
    days: list[DayLog]  # in the requested range, oldest first
    first_date: date | None  # the earliest logged day ever (None: nothing logged)
    periods: tuple[RestPeriod, ...] = ()  # rest periods overlapping the range (WH-01)


@dataclass(frozen=True, slots=True)
class RangeView:
    days: list[DayLog]  # logged days in the range, oldest first
    moon_dates: frozenset[date]  # moon days of the location in the range (auto-rest)
    periods: tuple[RestPeriod, ...] = ()  # rest periods overlapping the range, unclipped
    practice_on: bool = False  # practice reminders on (labels on covered days)
    notes: dict[date, DiaryNote] = field(default_factory=dict[date, DiaryNote])  # PR-07


@dataclass(frozen=True, slots=True)
class Upserted:
    """A day upsert plus the pre-statement snapshot the pause offer needs (WH-01)."""

    day: DayLog
    prev: DayStatus | None = None  # the logged status of the day before
    periods: tuple[RestPeriod, ...] = ()  # periods covering the day before or the day
    practice_on: bool = False
    cut: RestPeriod | None = None  # a period as it was before this 🧘 Practiced cut it


@dataclass(frozen=True, slots=True)
class Inserted:
    """`insert_if_absent`: whether it was written, and a period it cut (🧘 only)."""

    inserted: bool
    cut: RestPeriod | None = None


class DayLogRepository(Protocol):
    """One statement per method (see `AccountRepository`). Implementations keep private
    statuses private at rest (ADR-0016); callers always see the true `DayStatus`."""

    async def upsert(self, account_id: UUID, day: DayLog, timezone: str | None) -> Upserted:
        """Insert or replace the status of that date. `timezone` = the zone "today" was
        computed in, or None when it was a provisional guess."""
        ...

    async def insert_if_absent(
        self, account_id: UUID, day: DayLog, timezone: str | None
    ) -> Inserted:
        """Log the day only if it has no status yet (a reminder tap never overwrites);
        False when it was already logged."""
        ...

    async def delete(self, account_id: UUID, local_date: date) -> None:
        """Idempotent: deleting a day that was never logged is fine."""
        ...

    async def list_range(self, account_id: UUID, start: date, end: date) -> list[DayLog]:
        """Logged days in [start, end], oldest first."""
        ...

    async def range_with_moon(
        self, account_id: UUID, start: date, end: date, location: str
    ) -> RangeView:
        """`list_range` plus the location's moon dates, in one statement (PR-09)."""
        ...

    async def history(self, account_id: UUID, start: date, end: date) -> History:
        """`list_range` plus the first logged date, in one statement (stats)."""
        ...
