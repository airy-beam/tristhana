"""In-memory `TeacherRequestRepository` (ID-07 spec §3, ADR-0046).

Its own module, like `teacher_link_fakes.py`: `InMemoryStorage.teacher_requests` loads it on
first use. It sits on the in-memory links and shalas, as the SQL joins their tables: validity
is derived on every read from the membership rows, the rules are the domain's, and the guard
calls the policy itself (`test_db_teacher_requests.py` pins the SQL to the same matrix).
`created_at` comes from the shalas' own tick, the fake's "database clock", so a membership
made before a request is older than it and a rejoin is newer.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any
from uuid import UUID, uuid4

from tests.shala_fakes import InMemoryShalas
from tests.teacher_link_fakes import InMemoryTeacherLinks
from tristhana.application.policies import can_ask_teacher
from tristhana.application.ports.shalas import Guarded
from tristhana.application.ports.teacher_requests import (
    Answer,
    Answered,
    ApprovedAll,
    Asked,
    AskedTeacher,
    CardRequests,
    Choices,
    DueClosing,
    MyRequests,
    TeacherChoice,
    WaitingPage,
    WaitingRequest,
    Withdrawn,
)
from tristhana.domain.shalas import ShalaRole
from tristhana.domain.teacher_requests import (
    AskState,
    RequestCaps,
    RequestState,
    answerable,
    ask_state,
    closing_due,
    counts_as_asked,
    kept,
    request_key,
    waiting_for_student,
    waiting_for_teacher,
)


@dataclass
class RequestRow:
    id: UUID
    student_id: UUID
    teacher_id: UUID
    shala_id: UUID
    state: RequestState
    asked_on: date
    quiet_note_agreed: bool
    created_at: datetime


@dataclass
class InMemoryTeacherRequests:
    links: InMemoryTeacherLinks
    shalas: InMemoryShalas
    rows: dict[tuple[UUID, UUID], RequestRow] = field(
        default_factory=dict[tuple[UUID, UUID], RequestRow]
    )
    notifications: Any = None  # an `InMemoryNotifications`: the ledger `due` reads
    fail_with: Exception | None = None
    writes: list[str] = field(default_factory=list[str])  # finished writes, in order
    calls: list[str] = field(default_factory=list[str])  # every port call, in order

    def __post_init__(self) -> None:
        self.links.on_unlink.append(self._close)

    # Seeding and inspection (not part of the port).

    def add(
        self,
        student: UUID,
        teacher: UUID,
        shala: UUID,
        *,
        state: RequestState = RequestState.WAITING,
        asked_on: date = date(2026, 11, 17),
        agreed: bool = True,
        created_at: datetime | None = None,
    ) -> RequestRow:
        at = created_at or self._next_instant()
        row = RequestRow(uuid4(), student, teacher, shala, state, asked_on, agreed, at)
        self.rows[(student, teacher)] = row
        return row

    def state_of(self, student: UUID, teacher: UUID) -> RequestState | None:
        row = self._live().get((student, teacher))
        return None if row is None else row.state

    # The port.

    async def choices(self, shala: UUID, me: UUID, now: datetime) -> Choices | None:
        self._call("choices")
        return self._choices(shala, me, now)

    async def card(self, shala: UUID, me: UUID, now: datetime) -> CardRequests:
        self._call("card")
        member = self.shalas.membership(shala, me)
        teaches = member is not None and member.staff and ShalaRole.TEACHER in member.roles
        return CardRequests(
            self._choices(shala, me, now), self._waiting_for(me, now) if teaches else 0
        )

    async def ask(
        self,
        shala: UUID,
        me: UUID,
        teacher: UUID,
        asked_on: date,
        agreed: bool,
        caps: RequestCaps,
        now: datetime,
    ) -> Guarded[Asked]:
        self._call("ask")
        await asyncio.sleep(0)  # the round trip: a double tap races here
        membership = self.shalas.membership(shala, me)
        if membership is None:
            return Guarded(None, False)
        if not can_ask_teacher(membership, self.shalas.membership(shala, teacher)):
            return Guarded(membership, False)
        earlier = self._live().get((me, teacher))
        their_waiting = self._waiting_for(teacher, now)
        state = ask_state(
            linked=(me, teacher) in self.links.rows,
            earlier=None if earlier is None else (earlier.state, earlier.created_at),
            now=now,
            my_asked=sum(
                1
                for r in self._live().values()
                if r.student_id == me and counts_as_asked(r.state, r.created_at, now)
            ),
            my_waiting=sum(
                1
                for r in self._live().values()
                if r.student_id == me and self._student_sees(r, now)
            ),
            my_teachers=len(self.links.teachers_of(me)),
            their_waiting=their_waiting,
            their_students=len(self.links.students_of(teacher)),
            caps=caps,
            still_valid=earlier is None or self._student_valid(earlier),
        )
        if state is AskState.CREATED:
            self.add(me, teacher, shala, asked_on=asked_on, agreed=agreed)
            self.writes.append("ask")
            their_waiting += 1
        account = self.links.accounts.accounts[teacher]
        asked = Asked(
            state,
            account.display_name,
            account.locale,
            self._telegram_id(teacher),
            self.shalas.shalas[shala].name,
            their_waiting,
        )
        return Guarded(membership, True, asked)

    async def withdraw(self, me: UUID, teacher: UUID) -> Withdrawn:
        self._call("withdraw")
        await asyncio.sleep(0)
        row = self._live().get((me, teacher))
        linked = (me, teacher) in self.links.rows
        if row is None or row.state not in (RequestState.WAITING, RequestState.DECLINED):
            return Withdrawn(False, linked)
        row.state = RequestState.WITHDRAWN
        self.writes.append("withdraw")
        return Withdrawn(True, linked)

    async def mine(self, me: UUID, now: datetime) -> MyRequests:
        self._call("mine")
        asked = tuple(
            AskedTeacher(
                r.teacher_id,
                self._name(r.teacher_id),
                r.shala_id,
                self.shalas.shalas[r.shala_id].name,
            )
            for r in self._ordered()
            if r.student_id == me and self._student_sees(r, now)
        )
        return MyRequests(asked, self._waiting_for(me, now))

    async def waiting(
        self,
        me: UUID,
        now: datetime,
        offset: int,
        limit: int,
        student: UUID | None = None,
        before: datetime | None = None,
    ) -> WaitingPage:
        self._call("waiting")
        rows = [
            r
            for r in self._ordered()
            if r.teacher_id == me
            and self._teacher_sees(r, now)
            and (before is None or r.created_at < before)
        ]
        shown = [r for r in rows if student is None or r.student_id == student]
        page = tuple(
            WaitingRequest(
                r.student_id,
                self._name(r.student_id),
                r.shala_id,
                self.shalas.shalas[r.shala_id].name,
            )
            for r in shown[offset : offset + limit]
        )
        return WaitingPage(page, len(rows), self._next_instant())

    async def approve(self, me: UUID, student: UUID, caps: RequestCaps, now: datetime) -> Answer:
        self._call("approve")
        await asyncio.sleep(0)  # the round trip: two taps race here
        row = self._live().get((student, me))
        if (student, me) in self.links.rows:
            return self._answer(Answered.ALREADY, me, student, now)
        if row is None or not self._answerable(row, now):
            return self._answer(Answered.GONE, me, student, now)
        if self._over(me, student, caps):
            return self._answer(Answered.FULL, me, student, now)
        self._link(row)
        self.writes.append("approve")
        return self._answer(Answered.DONE, me, student, now)

    async def approve_all(
        self, me: UUID, before: datetime, caps: RequestCaps, now: datetime
    ) -> ApprovedAll:
        self._call("approve_all")
        await asyncio.sleep(0)
        approved = 0
        for row in self._ordered():
            if (
                row.teacher_id != me
                or not self._teacher_sees(row, now)
                or row.created_at >= before
                or self._over(me, row.student_id, caps)
            ):
                continue
            self._link(row)
            approved += 1
        if approved:
            self.writes.append("approve_all")
        return ApprovedAll(approved, self._waiting_for(me, now))

    async def decline(self, me: UUID, student: UUID, now: datetime) -> Answer:
        self._call("decline")
        return self._set(me, student, now, RequestState.DECLINED, "decline")

    async def reopen(self, me: UUID, student: UUID, now: datetime) -> Answer:
        self._call("reopen")
        return self._set(me, student, now, RequestState.WAITING, "reopen")

    async def due(self, now: datetime, limit: int) -> list[DueClosing]:
        self._call("due")
        out: list[DueClosing] = []
        for row in self._ordered():
            linked = (row.student_id, row.teacher_id) in self.links.rows
            closing = closing_due(row.state, row.created_at, linked, now)
            telegram_id = self._telegram_id(row.student_id)
            if (
                closing is None
                or not self._student_valid(row)
                or telegram_id is None
                or self._in_ledger(row)
            ):
                continue
            student = self.links.accounts.accounts[row.student_id]
            out.append(
                DueClosing(
                    id=row.id,
                    closing=closing,
                    student_id=row.student_id,
                    telegram_id=telegram_id,
                    locale=student.locale,
                    zone=student.timezone,
                    teacher_id=row.teacher_id,
                    teacher_name=self._name(row.teacher_id),
                    shala_id=row.shala_id,
                    my_teachers=len(self.links.teachers_of(row.student_id)),
                )
            )
        return out[:limit]

    async def prune(self, before: datetime) -> int:
        self._call("prune")
        dead = [key for key, row in self.rows.items() if row.created_at <= before]
        for key in dead:
            del self.rows[key]
        return len(dead)

    # Internals.

    def _call(self, name: str) -> None:
        self.links.accounts._check()  # pyright: ignore[reportPrivateUsage]
        self.calls.append(name)
        if self.fail_with is not None:
            error, self.fail_with = self.fail_with, None
            raise error

    def _choices(self, shala: UUID, me: UUID, now: datetime) -> Choices | None:
        membership = self.shalas.membership(shala, me)
        if membership is None or not membership.student:
            return None
        offer = [
            TeacherChoice(teacher, self._name(teacher))
            for teacher in self.shalas.staff_of(shala)
            if can_ask_teacher(membership, self.shalas.membership(shala, teacher))
            and (me, teacher) not in self.links.rows
            and not self._kept(me, teacher, now)
        ]
        waiting = [
            TeacherChoice(r.teacher_id, self._name(r.teacher_id))
            for r in self._ordered()
            if r.student_id == me and r.shala_id == shala and self._student_sees(r, now)
        ]
        return Choices(shala, self.shalas.shalas[shala].name, tuple(offer), tuple(waiting))

    def _live(self) -> dict[tuple[UUID, UUID], RequestRow]:
        """ON DELETE CASCADE, read lazily: a row whose accounts or shala are gone is gone."""
        accounts = self.links.accounts.accounts
        return {
            key: row
            for key, row in self.rows.items()
            if row.student_id in accounts
            and row.teacher_id in accounts
            and row.shala_id in self.shalas.shalas
        }

    def _ordered(self) -> list[RequestRow]:
        return sorted(self._live().values(), key=lambda r: (r.created_at, r.student_id))

    def _student_valid(self, row: RequestRow) -> bool:
        member = self.shalas.students_rows.get((row.shala_id, row.student_id))
        return member is not None and member.created_at <= row.created_at

    def _teacher_valid(self, row: RequestRow) -> bool:
        member = self.shalas.staff.get((row.shala_id, row.teacher_id))
        return (
            member is not None
            and member.created_at <= row.created_at
            and ShalaRole.TEACHER in (member.roles or frozenset())
        )

    def _linked(self, row: RequestRow) -> bool:
        """The link wins in every read: a linked pair is nobody's waiting request."""
        return (row.student_id, row.teacher_id) in self.links.rows

    def _student_sees(self, row: RequestRow, now: datetime) -> bool:
        return (
            waiting_for_student(row.state, row.created_at, now)
            and self._student_valid(row)
            and not self._linked(row)
        )

    def _teacher_sees(self, row: RequestRow, now: datetime) -> bool:
        return (
            waiting_for_teacher(row.state, row.created_at, now)
            and self._student_valid(row)
            and self._teacher_valid(row)
            and not self._linked(row)
        )

    def _answerable(self, row: RequestRow, now: datetime) -> bool:
        return (
            answerable(row.state, row.created_at, now)
            and self._student_valid(row)
            and self._teacher_valid(row)
        )

    def _kept(self, student: UUID, teacher: UUID, now: datetime) -> bool:
        row = self._live().get((student, teacher))
        return row is not None and kept(row.created_at, now)

    def _waiting_for(self, teacher: UUID, now: datetime) -> int:
        return sum(
            1
            for r in self._live().values()
            if r.teacher_id == teacher and self._teacher_sees(r, now)
        )

    def _over(self, teacher: UUID, student: UUID, caps: RequestCaps) -> bool:
        return (
            len(self.links.teachers_of(student)) >= caps.teachers
            or len(self.links.students_of(teacher)) >= caps.students
        )

    def _link(self, row: RequestRow) -> None:
        """The approve statement: the state and the link together."""
        row.state = RequestState.APPROVED
        self.links.add(
            row.student_id,
            row.teacher_id,
            linked_on=row.asked_on,
            quiet_note_agreed=row.quiet_note_agreed,
        )

    def _set(
        self, me: UUID, student: UUID, now: datetime, state: RequestState, name: str
    ) -> Answer:
        row = self._live().get((student, me))
        if (student, me) in self.links.rows:
            return self._answer(Answered.ALREADY, me, student, now)
        if row is None or not self._answerable(row, now):
            return self._answer(Answered.GONE, me, student, now)
        if row.state is not state:
            row.state = state
            self.writes.append(name)
        return self._answer(Answered.DONE, me, student, now)

    def _answer(self, outcome: Answered, me: UUID, student: UUID, now: datetime) -> Answer:
        # A name only with a request row: an id alone never reads anyone's name.
        known = outcome is not Answered.GONE and (student, me) in self._live()
        return Answer(outcome, self._name(student) if known else None, self._waiting_for(me, now))

    def _close(self, student: UUID, teacher: UUID) -> None:
        """`unlink`'s CTE: a removed link closes the pair's request."""
        row = self.rows.get((student, teacher))
        if row is not None:
            row.state = RequestState.WITHDRAWN

    def _in_ledger(self, row: RequestRow) -> bool:
        if self.notifications is None:
            return False
        delivery = self.notifications.deliveries.get((row.student_id, request_key(row.id)))
        if delivery is None:
            return False
        retryable = delivery["status"] == "failed" and delivery["attempts"] < 3
        return not retryable

    def _name(self, account: UUID) -> str | None:
        found = self.links.accounts.accounts.get(account)
        return found.display_name if found else None

    def _telegram_id(self, account_id: UUID) -> str | None:
        for key, owner in self.links.accounts.identities.items():
            if owner == account_id:
                return key.provider_user_id
        return None

    def _next_instant(self) -> datetime:
        return self.shalas._next_instant()  # pyright: ignore[reportPrivateUsage]
