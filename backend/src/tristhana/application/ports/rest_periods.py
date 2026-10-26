from dataclasses import dataclass
from datetime import date
from typing import Protocol
from uuid import UUID

from tristhana.domain.days import DayStatus
from tristhana.domain.rest_periods import RestPeriod


@dataclass(frozen=True, slots=True)
class Placed:
    period: RestPeriod
    practice_on: bool = False  # practice reminders on (the wording), read in the same statement


@dataclass(frozen=True, slots=True)
class Ended:
    period: RestPeriod | None  # what is left (None: removed, or there was none)
    kind: DayStatus | None = None  # the period's kind as it was (None: there was none)


class RestPeriodRepository(Protocol):
    """One write statement per method (ADR-0023), serialised per account so coverage never
    overlaps. The kind is sealed at rest; callers always see the true kind."""

    async def place(self, account_id: UUID, period: RestPeriod) -> Placed:
        """Insert or replace the period starting on `period.start` and apply the overlap
        rule (`domain.rest_periods.place`) in the same statement."""
        ...

    async def restore(self, account_id: UUID, period: RestPeriod, today: date) -> RestPeriod | None:
        """ "Keep the pause": `place`, but only if a 🧘 Practiced day lies in
        [start, min(end, today)] (a cut happened), in the same statement; None otherwise,
        and nothing changes. Never a way to backfill rest days."""
        ...

    async def end(self, account_id: UUID, start: date, today: date) -> Ended:
        """End the period starting on `start` per `domain.rest_periods.end_from` (removed
        when nothing is left). Idempotent."""
        ...
