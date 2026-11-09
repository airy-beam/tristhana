"""In-memory `AttendanceRepository` (`Storage.attendance`, SC-05 spec §3, ADR-0039).

It reads windows from `InMemorySchedule` (one `_read` around the rule date), keeps rows keyed
by (class, rule date, person) with the snapshot, and attaches itself to the schedule fake so
`window` / `member_windows` carry my marks and the staff counts. Leaving or a removal deletes
the person's rows at that shala (Q186), through the shala fake's `on_leave` hook. The guards
call `application/policies.py` themselves; `test_db_attendance.py` pins the SQL to them.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any
from uuid import UUID

from tests.schedule_fakes import InMemorySchedule
from tristhana.application.policies import can_claim_attendance, can_take_attendance
from tristhana.application.ports.attendance import (
    AttendanceTarget,
    Marked,
    RosterPerson,
    RosterRead,
)
from tristhana.application.ports.shalas import Guarded
from tristhana.domain.attendance import (
    PRACTISES_HERE_DAYS,
    REGULAR_DAYS,
    AttendanceState,
    Counts,
    Snapshot,
)

_REACH = timedelta(days=12)


@dataclass
class Row:
    snap: Snapshot
    state: AttendanceState
    updated_at: datetime | None = None


@dataclass
class InMemoryAttendance:
    schedule: InMemorySchedule
    rows: dict[tuple[UUID, date, UUID], Row] = field(
        default_factory=dict[tuple[UUID, date, UUID], Row]
    )
    calls: list[str] = field(default_factory=list[str])

    def __post_init__(self) -> None:
        self.schedule.attendance = self
        self.schedule.shalas.on_leave.append(self._leave)

    # Seeding (not part of the port).

    def seed(self, snap: Snapshot, account: UUID, state: AttendanceState) -> None:
        self.rows[(snap.class_id, snap.key, account)] = Row(snap, state)

    def state_of(self, class_id: UUID, key: date, account: UUID) -> AttendanceState | None:
        row = self.rows.get((class_id, key, account))
        return None if row is None else row.state

    def window_fields(
        self, shala: UUID, me: UUID, staff: bool, lo: date, hi: date
    ) -> dict[str, Any]:
        mine = {
            (c, k): r.state
            for (c, k, a), r in self.rows.items()
            if a == me and r.snap.shala_id == shala and lo <= k <= hi
        }
        counts: dict[tuple[UUID, date], Counts] = {}
        if staff:
            for (c, k, _), r in self.rows.items():
                if r.snap.shala_id != shala or not lo <= k <= hi:
                    continue
                old = counts.get((c, k), Counts(0, 0))
                if r.state is AttendanceState.CONFIRMED:
                    counts[(c, k)] = Counts(old.confirmed + 1, old.claimed)
                else:
                    counts[(c, k)] = Counts(old.confirmed, old.claimed + 1)
        return {"mine": mine, "counts": counts}

    def _leave(self, shala: UUID, account: UUID) -> None:
        for k in [k for k, r in self.rows.items() if k[2] == account and r.snap.shala_id == shala]:
            del self.rows[k]

    def _shala_of(self, class_id: UUID) -> UUID | None:
        found = self.schedule.classes.get(class_id)
        return None if found is None else found[0]

    def _counts(self, class_id: UUID, key: date) -> Counts:
        states = [r.state for (c, k, _), r in self.rows.items() if c == class_id and k == key]
        confirmed = sum(1 for s in states if s is AttendanceState.CONFIRMED)
        return Counts(confirmed, len(states) - confirmed)

    # The port.

    async def occurrence(self, me: UUID, class_id: UUID, key: date) -> AttendanceTarget | None:
        self.calls.append("occurrence")
        self.schedule.shalas._call("attendance.occurrence")  # pyright: ignore[reportPrivateUsage]
        shala = self._shala_of(class_id)
        if shala is None:
            return None
        window = self.schedule._read(shala, me, key - _REACH, key + _REACH)  # pyright: ignore[reportPrivateUsage]
        if window is None:
            return None
        return AttendanceTarget(window, self.state_of(class_id, key, me))

    async def roster(
        self, me: UUID, class_id: UUID, key: date, q: str | None, offset: int, limit: int
    ) -> RosterRead | None:
        self.calls.append("roster")
        self.schedule.shalas._call("attendance.roster")  # pyright: ignore[reportPrivateUsage]
        shala = self._shala_of(class_id)
        if shala is None:
            return None
        window = self.schedule._read(shala, me, key - _REACH, key + _REACH)  # pyright: ignore[reportPrivateUsage]
        if window is None:
            return None
        target = AttendanceTarget(window, self.state_of(class_id, key, me))
        if not can_take_attendance(window.me):
            return RosterRead(target, (), False, Counts(0, 0))
        shalas = self.schedule.shalas
        here = {
            a
            for (_c, k, a), r in self.rows.items()
            if r.snap.shala_id == shala and key - timedelta(days=PRACTISES_HERE_DAYS) <= k
        }
        students = set(shalas.students_of(shala))
        staff = set(shalas.staff_of(shala))
        on_it = {a for (c, k, a) in self.rows if c == class_id and k == key}
        people = students | (staff & here) | on_it
        regular = {
            a
            for (c, k, a) in self.rows
            if c == class_id and key - timedelta(days=REGULAR_DAYS) <= k < key
        }
        found: list[RosterPerson] = []
        for a in people:
            name = shalas._name(a)  # pyright: ignore[reportPrivateUsage]
            if q is not None and q.casefold() not in (name or "").casefold():
                continue
            found.append(
                RosterPerson(a, name, self.state_of(class_id, key, a), a in staff, a in regular)
            )
        found.sort(
            key=lambda p: (
                p.state is not AttendanceState.CLAIMED,
                not p.regular,
                (p.name or "").casefold(),
                str(p.account_id),
            )
        )
        page = found[offset : offset + limit]
        return RosterRead(
            target, tuple(page), len(found) > offset + limit, self._counts(class_id, key)
        )

    async def claim(
        self, me: UUID, snap: Snapshot, state: AttendanceState
    ) -> Guarded[AttendanceState]:
        self.calls.append("claim")
        m = self.schedule.shalas.membership(snap.shala_id, me)
        if m is None:
            return Guarded(None, False)
        if not can_claim_attendance(m):
            return Guarded(m, False)
        k = (snap.class_id, snap.key, me)
        old = self.rows.get(k)
        new = AttendanceState.CONFIRMED if old and old.state is AttendanceState.CONFIRMED else state
        self.rows[k] = Row(snap, new)
        return Guarded(m, True, new)

    async def remove(self, me: UUID, class_id: UUID, key: date) -> bool:
        self.calls.append("remove")
        return self.rows.pop((class_id, key, me), None) is not None

    async def mark(
        self,
        me: UUID,
        snap: Snapshot,
        present: Sequence[UUID],
        removed: Sequence[UUID],
        confirm_claims: bool,
    ) -> Guarded[Marked]:
        self.calls.append("mark")
        shalas = self.schedule.shalas
        m = shalas.membership(snap.shala_id, me)
        if m is None:
            return Guarded(None, False)
        if not can_take_attendance(m):
            return Guarded(m, False)
        if any(shalas.membership(snap.shala_id, a) is None for a in present):
            return Guarded(m, True, Marked(False, self._counts(snap.class_id, snap.key)))
        for a in removed:
            self.rows.pop((snap.class_id, snap.key, a), None)
        for a in present:
            self.rows[(snap.class_id, snap.key, a)] = Row(snap, AttendanceState.CONFIRMED)
        if confirm_claims:
            for (c, k, _), r in self.rows.items():
                if c == snap.class_id and k == snap.key:
                    r.state = AttendanceState.CONFIRMED
        return Guarded(
            m, True, Marked(True, self._counts(snap.class_id, snap.key), frozenset(present))
        )
