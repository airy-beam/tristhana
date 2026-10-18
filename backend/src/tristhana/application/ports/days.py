from datetime import date
from typing import Protocol
from uuid import UUID

from tristhana.domain.days import DayLog


class DayLogRepository(Protocol):
    """One statement per method (see `AccountRepository`). Implementations keep private
    statuses private at rest (ADR-0016); callers always see the true `DayStatus`."""

    async def upsert(self, account_id: UUID, day: DayLog, timezone: str | None) -> DayLog:
        """Insert or replace the status of that date. `timezone` = the zone "today" was
        computed in, or None when it was a provisional guess."""
        ...

    async def delete(self, account_id: UUID, local_date: date) -> None:
        """Idempotent: deleting a day that was never logged is fine."""
        ...

    async def list_range(self, account_id: UUID, start: date, end: date) -> list[DayLog]:
        """Logged days in [start, end], oldest first."""
        ...
