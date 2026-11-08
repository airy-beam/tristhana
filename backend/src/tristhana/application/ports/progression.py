from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID

from tristhana.domain.locale import Locale
from tristhana.domain.progression import (
    Change,
    Earlier,
    Position,
    Progression,
    ProgressionEvent,
)


@dataclass(frozen=True, slots=True)
class ProgressionView:
    progression: Progression | None  # None = not set yet
    earlier: Earlier = field(default_factory=Earlier)
    events: tuple[ProgressionEvent, ...] = ()  # newest first, at most HISTORY_LIMIT


@dataclass(frozen=True, slots=True)
class MarkLink:
    """A teacher link as a mark needs it (PR-08 Phase 3): who, and how to tell the student
    (their zone or locale for their today, their Telegram id for the note; None = no Telegram
    identity, so no note)."""

    teacher_id: UUID
    student_id: UUID
    timezone: str | None
    locale: Locale
    telegram_id: str | None


@dataclass(frozen=True, slots=True)
class TeacherMarkView:
    link: MarkLink
    view: ProgressionView  # the student's, read in the same statement as the link


class ProgressionRepository(Protocol):
    """One statement per method (ADR-0026). Progression is plain, owner-only data."""

    async def get(self, account_id: UUID) -> ProgressionView:
        """The state, what the history held (`Earlier`) and the newest events."""
        ...

    async def for_teacher(self, teacher: UUID, student: UUID) -> TeacherMarkView | None:
        """The link `teacher` → `student` with the student's view, in one statement. None =
        not linked that way (unknown, unlinked or reversed)."""
        ...

    async def apply(
        self,
        account_id: UUID,
        change: Change,
        expected_event_id: int | None,
        marked_by: UUID,
        *,
        before: Position | None,
        link_teacher: UUID | None = None,
    ) -> ProgressionEvent | None:
        """Append the event and store its state, only if the latest event is still
        `expected_event_id` and the position is still `before` (compare-and-set). `before`
        None means only "no stored row" (a START): an existing row is never overwritten then.
        With `link_teacher`, only while that teacher is linked to the account. None = someone
        changed it first (or no link)."""
        ...

    async def undo(self, account_id: UUID, event_id: int) -> bool:
        """Delete the event if it is the latest, restoring the state before it (undoing the
        START unsets the progression); or a teacher's `given` that no later position event
        moved on from, restoring its `from` and keeping the items (ADR-0037). False = neither."""
        ...

    async def dismiss_hint(self, account_id: UUID, target: Position) -> None:
        """Remember "Not new" for `target` at the current latest event (no row: nothing)."""
        ...
