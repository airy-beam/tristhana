"""Teacher requests (ID-07, ADR-0046): a student of a shala asks, the teacher confirms. Both
adapters use these, except `GetTeacherChoices` and `AskTeacher`: the consent text lives in
one place, the bot (as ID-04's Q12).

A request is not a link. No use case here reads a log, and none grants a view of one: the
link, and with it the teacher view, exists only after `ApproveRequest`. Every write is keyed
on the caller's account, so an id from a client can only ever touch the caller's own rows.
Nobody but the two people sees a request (Q322).

The student is never told about a "no": `DeclineRequest` sends nothing, and what the student
can read back (`Choices`, `MyRequests`, `AskResult`) carries no state and no date. The two
closing notes are the tick's (`TeacherRequestRepository.due`).
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from tristhana.application.policies import (
    NotAllowed,
    NotFound,
    Principal,
    can_answer_request,
    can_withdraw_request,
)
from tristhana.application.ports.notifications import Notifier, Recipient, TeacherAsked
from tristhana.application.ports.storage import Clock
from tristhana.application.ports.teacher_requests import (
    Answer,
    ApprovedAll,
    CardRequests,
    Choices,
    MyRequests,
    TeacherRequestRepository,
    WaitingPage,
    Withdrawn,
)
from tristhana.application.settings import caller_today
from tristhana.domain.teacher_requests import CAPS, AskState


@dataclass(frozen=True, slots=True)
class AskResult:
    """What the student's tap came to, as the student may see it: never the teacher's
    queue, language or contact."""

    state: AskState
    teacher_name: str | None


class GetTeacherChoices:
    def __init__(self, requests: TeacherRequestRepository, clock: Clock) -> None:
        self._requests = requests
        self._clock = clock

    async def execute(self, principal: Principal, shala: UUID) -> Choices:
        """The teachers a student of `shala` can ask, and the ones they wait for. Raises
        `NotFound`: no such shala, or the caller is not a student there."""
        found = await self._requests.choices(shala, principal.account.id, self._clock.now())
        if found is None:
            raise NotFound
        return found


class GetCardRequests:
    def __init__(self, requests: TeacherRequestRepository, clock: Clock) -> None:
        self._requests = requests
        self._clock = clock

    async def execute(self, principal: Principal, shala: UUID) -> CardRequests:
        """The requests part of a shala's card, read beside the card: a student's choices
        there, or how many wait for a teacher of it. Keyed on the caller, and empty for
        anyone else (the card's own read says "not found")."""
        return await self._requests.card(shala, principal.account.id, self._clock.now())


class AskTeacher:
    def __init__(
        self, requests: TeacherRequestRepository, notifier: Notifier, clock: Clock
    ) -> None:
        self._requests = requests
        self._notifier = notifier
        self._clock = clock

    async def execute(
        self, principal: Principal, shala: UUID, teacher_id: UUID, *, quiet_note_agreed: bool
    ) -> AskResult:
        """The student's consent tap. `asked_on` is their local date, the boundary of "from
        today on" in the consent, stored now and copied by the approval. `quiet_note_agreed`
        is what the tapped screen's text granted. The teacher's note is best effort: the
        waiting list is the record, so a blocked bot fails nothing. Raises `NotFound` (not a
        member), `NotAllowed` (not a student, or the other person holds no Teacher role)."""
        account = principal.account
        asked_on = caller_today(principal, self._clock)
        guarded = await self._requests.ask(
            shala, account.id, teacher_id, asked_on, quiet_note_agreed, CAPS, self._clock.now()
        )
        if guarded.me is None:
            raise NotFound
        if not guarded.done or guarded.value is None:
            raise NotAllowed
        asked = guarded.value
        if asked.state is AskState.CREATED and asked.teacher_telegram_id is not None:
            await self._notifier.tell_teacher_asked(
                Recipient(asked.teacher_telegram_id, asked.teacher_locale),
                TeacherAsked(account.id, account.display_name, asked.shala_name, asked.waiting),
            )
        return AskResult(asked.state, asked.teacher_name)


class WithdrawRequest:
    def __init__(self, requests: TeacherRequestRepository) -> None:
        self._requests = requests

    async def execute(self, principal: Principal, teacher_id: UUID) -> Withdrawn:
        """Silent and idempotent: the teacher gets no message. The pair's row stays, so this
        teacher can't be asked again for the rest of the 30 days (Q317)."""
        account = principal.account
        if not can_withdraw_request(account, account.id):
            raise NotAllowed
        return await self._requests.withdraw(account.id, teacher_id)


class GetMyRequests:
    def __init__(self, requests: TeacherRequestRepository, clock: Clock) -> None:
        self._requests = requests
        self._clock = clock

    async def execute(self, principal: Principal) -> MyRequests:
        """The teachers I wait for, and how many people wait for me."""
        return await self._requests.mine(principal.account.id, self._clock.now())


class GetWaitingRequests:
    def __init__(self, requests: TeacherRequestRepository, clock: Clock) -> None:
        self._requests = requests
        self._clock = clock

    async def execute(
        self,
        principal: Principal,
        offset: int,
        limit: int,
        student: UUID | None = None,
        before: datetime | None = None,
    ) -> WaitingPage:
        """The people waiting for the caller's answer, oldest first. `student`: one request's
        screen. `as_of` goes back into `ApproveAllRequests`; `before` is an earlier list's
        `as_of`, and counts who `ApproveAllRequests` would confirm for it."""
        account = principal.account
        if not can_answer_request(account, account.id):
            raise NotAllowed
        return await self._requests.waiting(
            account.id, self._clock.now(), offset, limit, student, before
        )


class ApproveRequest:
    def __init__(self, requests: TeacherRequestRepository, clock: Clock) -> None:
        self._requests = requests
        self._clock = clock

    async def execute(self, principal: Principal, student_id: UUID) -> Answer:
        """ "Yes, my student": the link comes to exist, counted from the day the student
        asked. No message leaves here; the student's note is the tick's. No moon write and
        no Keep offer either: an approver is on a shala's staff and follows it with or
        without students (ADR-0046)."""
        account = principal.account
        if not can_answer_request(account, account.id):
            raise NotAllowed
        return await self._requests.approve(account.id, student_id, CAPS, self._clock.now())


class ApproveAllRequests:
    def __init__(self, requests: TeacherRequestRepository, clock: Clock) -> None:
        self._requests = requests
        self._clock = clock

    async def execute(self, principal: Principal, before: datetime) -> ApprovedAll:
        """Confirms who was waiting when the list was drawn (`WaitingPage.as_of`), so someone
        who asked a moment later is never confirmed unseen. Never a declined request."""
        account = principal.account
        if not can_answer_request(account, account.id):
            raise NotAllowed
        return await self._requests.approve_all(account.id, before, CAPS, self._clock.now())


class DeclineRequest:
    def __init__(self, requests: TeacherRequestRepository, clock: Clock) -> None:
        self._requests = requests
        self._clock = clock

    async def execute(self, principal: Principal, student_id: UUID) -> Answer:
        """ "Not my student". The student isn't told and sees no change."""
        account = principal.account
        if not can_answer_request(account, account.id):
            raise NotAllowed
        return await self._requests.decline(account.id, student_id, self._clock.now())


class ReopenRequest:
    def __init__(self, requests: TeacherRequestRepository, clock: Clock) -> None:
        self._requests = requests
        self._clock = clock

    async def execute(self, principal: Principal, student_id: UUID) -> Answer:
        """Undo of "Not my student", inside the 7 days (Q320)."""
        account = principal.account
        if not can_answer_request(account, account.id):
            raise NotAllowed
        return await self._requests.reopen(account.id, student_id, self._clock.now())


@dataclass(frozen=True, slots=True)
class RequestUseCases:
    choices: GetTeacherChoices
    card: GetCardRequests
    ask: AskTeacher
    withdraw: WithdrawRequest
    mine: GetMyRequests
    waiting: GetWaitingRequests
    approve: ApproveRequest
    approve_all: ApproveAllRequests
    decline: DeclineRequest
    reopen: ReopenRequest
