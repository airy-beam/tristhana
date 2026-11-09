"""Class attendance (SC-05, ADR-0039). Every call is one statement.

The reads return a `ScheduleWindow` of the class's shala around the rule date, so the use case
expands the occurrence in the domain and a forged key can only fail. The guarded writes return
`Guarded` as SC-01's: `me` None = not a member (`NotFound`), `done` False = the policy said no
(`NotAllowed`). The SQL guards mirror `can_claim_attendance` and `can_take_attendance`.
Nothing here reads or writes a log, a rest or a check-in.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Protocol
from uuid import UUID

from tristhana.application.ports.classes import ScheduleWindow
from tristhana.application.ports.shalas import Guarded
from tristhana.domain.attendance import AttendanceState, Counts, Snapshot


@dataclass(frozen=True, slots=True)
class AttendanceTarget:
    """The class's shala over [key - 12, key + 12] (moves and swaps reach ±12) and my row."""

    window: ScheduleWindow
    mine: AttendanceState | None


@dataclass(frozen=True, slots=True)
class RosterPerson:
    account_id: UUID
    name: str | None
    state: AttendanceState | None
    staff: bool
    regular: bool  # a sort key only (Q191), never shown


@dataclass(frozen=True, slots=True)
class RosterRead:
    target: AttendanceTarget
    people: tuple[RosterPerson, ...]  # claims, regulars, then by name; at most `limit`
    more: bool
    counts: Counts


@dataclass(frozen=True, slots=True)
class Marked:
    """`valid` False: an id in `present` isn't a member of the shala, nothing written."""

    valid: bool
    counts: Counts
    present: frozenset[UUID] = frozenset()  # rows now confirmed by this write


class AttendanceRepository(Protocol):
    async def occurrence(self, me: UUID, class_id: UUID, key: date) -> AttendanceTarget | None:
        """None: no such class, or not a member of its shala."""
        ...

    async def roster(
        self, me: UUID, class_id: UUID, key: date, q: str | None, offset: int, limit: int
    ) -> RosterRead | None:
        """The people of one occurrence for staff (empty for a student): current students,
        staff with a mark at the shala in the 90 days before `key`, and anyone with a row on
        it; `q` filters by name. None as `occurrence`."""
        ...

    async def claim(
        self, me: UUID, snap: Snapshot, state: AttendanceState
    ) -> Guarded[AttendanceState]:
        """An upsert that keeps `confirmed`; the value is the stored state."""
        ...

    async def remove(self, me: UUID, class_id: UUID, key: date) -> bool:
        """My own row only; idempotent. True: a row was removed."""
        ...

    async def mark(
        self,
        me: UUID,
        snap: Snapshot,
        present: Sequence[UUID],
        removed: Sequence[UUID],
        confirm_claims: bool,
    ) -> Guarded[Marked]:
        """Staff: `present` → confirmed, `removed` → unmarked, `confirm_claims` → every current
        claim confirmed (deltas, so a concurrent claim isn't lost)."""
        ...
