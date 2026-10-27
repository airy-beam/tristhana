from dataclasses import dataclass
from datetime import date
from typing import Protocol
from uuid import UUID

from tristhana.application.practice_patch import PracticePatch
from tristhana.domain.check_in import CheckIn
from tristhana.domain.practice import Practice
from tristhana.domain.progression import Position, Progression


@dataclass(frozen=True, slots=True)
class SavedPractice:
    practice: Practice
    check_in: CheckIn | None = None  # the day's check-in, read in the same statement (PR-06)
    progression: Progression | None = None  # read in the same statement too (PR-08)
    length_changed: bool = False  # this write changed the stored length
    new_asana_hint: Position | None = None  # "New asana? 🎉" (set by `SavePractice`)


@dataclass(frozen=True, slots=True)
class CopiedPractice:
    practice: Practice
    source: date  # the day it was copied from


class PracticeRepository(Protocol):
    """One statement per method. Writes only land on a day whose status is Practiced."""

    async def save(
        self, account_id: UUID, local_date: date, patch: PracticePatch
    ) -> SavedPractice | None:
        """Upsert the patched fields of slot 1, with the day's check-in; None when the day
        isn't Practiced."""
        ...

    async def copy_latest(
        self, account_id: UUID, local_date: date, timezone: str | None
    ) -> SavedPractice | None:
        """Copy context, online, length and duration (not the start time) of the newest
        practice before `local_date`; None when the day isn't Practiced or there is none."""
        ...

    async def copy_usual(
        self, account_id: UUID, local_date: date, timezone: str | None
    ) -> CopiedPractice | None:
        """Like `copy_latest`, but from the newest non-Led practice (a Friday led class is
        rarely what someone does on Monday); the newest of any kind when there is none."""
        ...

    async def delete(self, account_id: UUID, local_date: date) -> None: ...

    async def recent(self, account_id: UUID, before: date, limit: int) -> list[Practice]:
        """Practices on days before `before`, newest first."""
        ...

    async def recent_with_progression(
        self, account_id: UUID, before: date, limit: int
    ) -> tuple[list[Practice], Progression | None]:
        """`recent` plus the progression state (PR-08 presets), still one statement."""
        ...
