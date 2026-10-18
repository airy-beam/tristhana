from datetime import date
from typing import Protocol
from uuid import UUID

from tristhana.application.practice_patch import PracticePatch
from tristhana.domain.practice import Practice


class PracticeRepository(Protocol):
    """One statement per method. Writes only land on a day whose status is Practiced."""

    async def save(
        self, account_id: UUID, local_date: date, patch: PracticePatch
    ) -> Practice | None:
        """Upsert the patched fields of slot 1; None when the day isn't Practiced."""
        ...

    async def copy_latest(
        self, account_id: UUID, local_date: date, timezone: str | None
    ) -> Practice | None:
        """Copy context, online, length and duration (not the start time) of the newest
        practice before `local_date`; None when the day isn't Practiced or there is none."""
        ...

    async def delete(self, account_id: UUID, local_date: date) -> None: ...

    async def recent(self, account_id: UUID, before: date, limit: int) -> list[Practice]:
        """Practices on days before `before`, newest first."""
        ...
