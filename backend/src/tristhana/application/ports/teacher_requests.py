"""Teacher requests (ID-07, ADR-0046). One statement per call.

A request counts only while it is *valid*: the student's `shala_student` row and the
teacher's `shala_staff` row both exist, both older than the request, and the staff row holds
the Teacher role. Every read and the approval carry that join, so leaving, a removal or a role
change needs no cleanup write, and a rejoin never revives an old request. The student's own
reads check only the student's side: a teacher who lost the role still looks like "waiting".

`created_at` is the database's clock (the column default), the same clock as the membership
rows it is compared with; the `now` arguments only measure the 7 and 30 days from it.
`WaitingPage.as_of` comes from that clock too, for `approve_all`.

The student's side never carries a state, a date or the teacher's counts.
"""

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from tristhana.application.ports.shalas import Guarded
from tristhana.domain.locale import Locale
from tristhana.domain.teacher_requests import AskState, Closing, RequestCaps


@dataclass(frozen=True, slots=True)
class TeacherChoice:
    """A teacher of the shala, as its members already see them on the card."""

    id: UUID
    name: str | None


@dataclass(frozen=True, slots=True)
class Choices:
    """The question screen, and the student's rows on the shala card."""

    shala_id: UUID
    shala_name: str
    offer: tuple[TeacherChoice, ...]  # Teacher role, not linked to me, no row for the pair
    waiting: tuple[TeacherChoice, ...]  # asked through this shala, as the student sees it


@dataclass(frozen=True, slots=True)
class Asked:
    """`ask`'s result, with what the teacher's note needs. Only `state` and `teacher_name`
    are the student's to see (`AskTeacher` drops the rest)."""

    state: AskState
    teacher_name: str | None
    teacher_locale: Locale
    teacher_telegram_id: str | None
    shala_name: str
    waiting: int  # how many wait for the teacher, this one included when created


@dataclass(frozen=True, slots=True)
class Withdrawn:
    """`removed` False: nothing was waiting. `linked`: the teacher confirmed meanwhile (or
    the two are linked another way), so "remove" is on the teacher card."""

    removed: bool
    linked: bool


@dataclass(frozen=True, slots=True)
class AskedTeacher:
    """One of my waiting requests: no state and no date (a quiet no looks the same)."""

    teacher_id: UUID
    name: str | None
    shala_id: UUID
    shala_name: str


@dataclass(frozen=True, slots=True)
class MyRequests:
    asked: tuple[AskedTeacher, ...]  # oldest first
    waiting: int  # how many wait for my answer, as a teacher


@dataclass(frozen=True, slots=True)
class WaitingRequest:
    """Someone waiting for my answer: a name I could already see as staff."""

    student_id: UUID
    name: str | None
    shala_id: UUID
    shala_name: str


@dataclass(frozen=True, slots=True)
class WaitingPage:
    requests: tuple[WaitingRequest, ...]  # oldest first
    total: int  # all that wait for me, whatever the page or the filter
    as_of: datetime  # the moment the list was drawn: `approve_all` takes it back


class Answered(StrEnum):
    """What the teacher's tap came to. `GONE` is one answer for every reason (expired,
    withdrawn, a membership or the role gone, an account or the shala deleted, pruned)."""

    DONE = "done"
    ALREADY = "already"  # the two are linked: a "no" never removes a link
    GONE = "gone"
    FULL = "full"  # a link cap is reached; the request stays


@dataclass(frozen=True, slots=True)
class Answer:
    outcome: Answered
    student_name: str | None = None
    waiting: int = 0  # how many still wait for me after this tap


@dataclass(frozen=True, slots=True)
class ApprovedAll:
    approved: int
    left: int  # still waiting: asked after the list was drawn, or over a cap


@dataclass(frozen=True, slots=True)
class DueClosing:
    """A request whose closing note is owed and not yet in the ledger (the tick's read)."""

    id: UUID  # the ledger key is `request_key(id)`
    closing: Closing
    student_id: UUID
    telegram_id: str
    locale: Locale
    zone: str | None  # the student's, for the ledger's local date
    teacher_id: UUID
    teacher_name: str | None
    shala_id: UUID  # "pick another teacher" opens this shala's question
    my_teachers: int  # the student's links now: "Make main" only from the second


class TeacherRequestRepository(Protocol):
    async def choices(self, shala: UUID, me: UUID, now: datetime) -> Choices | None:
        """None: no such shala, or not a student there."""
        ...

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
        """A guarded insert. `me` None: not a member; `done` False: `can_ask_teacher` said
        no. A row older than `KEEP` is recycled in the same statement, so the 30 days do not
        depend on the prune. `agreed`: the quiet-note consent of the screen that was tapped."""
        ...

    async def withdraw(self, me: UUID, teacher: UUID) -> Withdrawn:
        """Waiting or quietly declined becomes withdrawn; anything else is left alone."""
        ...

    async def mine(self, me: UUID, now: datetime) -> MyRequests: ...

    async def waiting(
        self, me: UUID, now: datetime, offset: int, limit: int, student: UUID | None = None
    ) -> WaitingPage:
        """`student`: only that person's request (one request's screen), with the full total."""
        ...

    async def approve(self, me: UUID, student: UUID, caps: RequestCaps, now: datetime) -> Answer:
        """The request becomes approved and the link is inserted, in one statement:
        `linked_on` is the request's `asked_on`, `quiet_note_agreed` the stored one,
        `is_primary` false. Works on a waiting or a quietly declined request inside the 7
        days, while valid and under both link caps."""
        ...

    async def approve_all(
        self, me: UUID, before: datetime, caps: RequestCaps, now: datetime
    ) -> ApprovedAll:
        """Waiting requests made before `before`, oldest first, as many as the caps allow.
        Never a declined one."""
        ...

    async def decline(self, me: UUID, student: UUID, now: datetime) -> Answer:
        """Idempotent inside the 7 days. The student is never told."""
        ...

    async def reopen(self, me: UUID, student: UUID, now: datetime) -> Answer:
        """Undo of a decline, inside the 7 days (Q320)."""
        ...

    async def due(self, now: datetime, limit: int) -> list[DueClosing]:
        """Confirmed as soon as the link exists; no answer from day 7, a declined and a
        silent request alike. Only while the student is still in the shala, reachable, and
        the note is not in the ledger (sent, blocked, failed for good or in flight)."""
        ...

    async def prune(self, before: datetime) -> int:
        """Rows created before `before` (the tick: `now - KEEP`)."""
        ...
