from datetime import date
from typing import Protocol
from uuid import UUID

from tristhana.domain.diary import DiaryNote


class DiaryRepository(Protocol):
    """One statement per method. Notes are sealed at rest (ADR-0016, ADR-0025) and never
    tied to the day's status; callers see plain text, or `DiaryNote(None)` if unreadable."""

    async def save(self, account_id: UUID, local_date: date, text: str) -> None:
        """Insert or replace the day's note."""
        ...

    async def get(self, account_id: UUID, local_date: date) -> DiaryNote | None: ...

    async def delete(self, account_id: UUID, local_date: date) -> None:
        """Idempotent."""
        ...
