from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID

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


class ProgressionRepository(Protocol):
    """One statement per method (ADR-0026). Progression is plain, owner-only data."""

    async def get(self, account_id: UUID) -> ProgressionView:
        """The state, what the history held (`Earlier`) and the newest events."""
        ...

    async def apply(
        self, account_id: UUID, change: Change, expected_event_id: int | None, marked_by: UUID
    ) -> ProgressionEvent | None:
        """Append the event and store its state, only if the latest event is still
        `expected_event_id` (compare-and-set). None = someone changed it first."""
        ...

    async def undo(self, account_id: UUID, event_id: int) -> bool:
        """Delete the event only if it is the latest, restoring the state before it (undoing
        the START unsets the progression). False = not the latest."""
        ...

    async def dismiss_hint(self, account_id: UUID, target: Position) -> None:
        """Remember "Not new" for `target` at the current latest event (no row: nothing)."""
        ...
