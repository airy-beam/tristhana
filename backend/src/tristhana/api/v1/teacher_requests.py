"""Teacher requests (ID-07, ADR-0046): a student of a shala asked the caller to be their
teacher, or the caller asked someone. The same use cases as the bot.

Asking (UI-06 stage 4B, ADR-0049): the app shows the bot's consent texts, and the ask names
the consent it showed (`RequestConsent`); the domain says what that grants, so no client sends
a flag. Every write is keyed on the caller, so an id in a path is no capability, and nobody
but the two people sees a request.

The student's side carries no state and no date: a quiet "no" serialises exactly as waiting,
in the choices, in the ask's `result` and in `/me/links`. On the teacher's side every reason a
request can no longer be answered is one 404 `request_gone`.
"""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from pydantic import AwareDatetime, BaseModel, Field

from tristhana.api.deps import CurrentPrincipal, teacher_requests
from tristhana.api.errors import ApiError, ErrorCode, error_responses
from tristhana.application.policies import NotAllowed, NotFound
from tristhana.application.ports.teacher_requests import (
    Answer,
    Answered,
    AskedTeacher,
    TeacherChoice,
    WaitingRequest,
)
from tristhana.application.teacher_requests import RequestUseCases
from tristhana.domain.teacher_links import MAX_STUDENTS
from tristhana.domain.teacher_requests import AskState, RequestConsent

router = APIRouter(tags=["links"], responses=error_responses(401, 503))

UseCases = Annotated[RequestUseCases, Depends(teacher_requests)]
_NO_STORE = {"Cache-Control": "no-store"}


class RequestShalaOut(BaseModel):
    """The shala a request came through."""

    id: UUID
    name: str


class AskedTeacherOut(BaseModel):
    """A teacher the caller asked and is waiting for. Nothing else, on purpose."""

    teacher_id: UUID
    name: str | None
    shala: RequestShalaOut

    @classmethod
    def of(cls, asked: AskedTeacher) -> "AskedTeacherOut":
        return cls(
            teacher_id=asked.teacher_id,
            name=asked.name,
            shala=RequestShalaOut(id=asked.shala_id, name=asked.shala_name),
        )


class StudentRequestOut(BaseModel):
    """Someone waiting for the caller's answer: a name they could already see as staff."""

    student_id: UUID
    name: str | None
    shala: RequestShalaOut

    @classmethod
    def of(cls, waiting: WaitingRequest) -> "StudentRequestOut":
        return cls(
            student_id=waiting.student_id,
            name=waiting.name,
            shala=RequestShalaOut(id=waiting.shala_id, name=waiting.shala_name),
        )


class StudentRequestsOut(BaseModel):
    requests: list[StudentRequestOut] = Field(description="Oldest first")
    total: int = Field(description="Everyone waiting for the caller, whatever the page")
    as_of: AwareDatetime = Field(
        description="The moment the list was drawn: send it back unchanged to `approve-all`"
    )


class ApproveAllIn(BaseModel):
    as_of: AwareDatetime = Field(description="`as_of` of the list the person was looking at")


class ApprovedAllOut(BaseModel):
    approved: int
    left: int = Field(description="Still waiting: asked after `as_of`, or a list is full")


class TeacherChoiceOut(BaseModel):
    """A teacher of the shala, as its members already see them on the card."""

    id: UUID
    name: str | None

    @classmethod
    def of(cls, choice: TeacherChoice) -> "TeacherChoiceOut":
        return cls(id=choice.id, name=choice.name)


class TeacherChoicesOut(BaseModel):
    """Who a student of the shala can ask, and who they wait for there. A quiet "no" is in
    `waiting`, exactly as silence is."""

    offer: list[TeacherChoiceOut] = Field(description="Oldest staff first")
    waiting: list[TeacherChoiceOut] = Field(description="Asked through this shala, no answer")


class AskIn(BaseModel):
    shala_id: UUID
    teacher_id: UUID
    consent: RequestConsent = Field(
        description="The consent text the picker showed (ADR-0049); it decides what the tap "
        "grants. Unknown values are 422"
    )


type AskResultName = Literal["created", "linked", "waiting", "recent", "too_many", "full"]

_RESULT: dict[AskState, AskResultName] = {
    AskState.CREATED: "created",
    AskState.LINKED: "linked",
    AskState.WAITING: "waiting",
    AskState.RECENT: "recent",
    AskState.TOO_MANY: "too_many",
    AskState.FULL: "full",
}


class AskOut(BaseModel):
    """What this tap came to, as the student may see it, and nothing else: never the
    teacher's answer (a quiet "no" gives `waiting` or `recent`, as silence does)."""

    result: AskResultName


def _fail(status: int, code: ErrorCode) -> ApiError:
    return ApiError(status, code, _NO_STORE)


def _answered(answer: Answer, *, linked_is_done: bool) -> None:
    """One mapping for the three taps. Already linked: a yes has what it wanted; a "no" or
    an undo has no request left to act on, and never removes a link."""
    outcome = answer.outcome
    if outcome is Answered.FULL:
        raise ApiError(409, "list_full", _NO_STORE)
    if outcome is Answered.GONE or (outcome is Answered.ALREADY and not linked_is_done):
        raise ApiError(404, "request_gone", _NO_STORE)


@router.get("/shalas/{id}/teacher-choices", responses=error_responses(404))
async def get_teacher_choices(
    id: UUID, principal: CurrentPrincipal, use_cases: UseCases, response: Response
) -> TeacherChoicesOut:
    """The teachers a student of the shala can ask, and the ones they wait for there. 404
    `not_found`: no such shala, not a member, or on its staff (one body for all three)."""
    try:
        found = await use_cases.choices.execute(principal, id)
    except NotFound:
        raise _fail(404, "not_found") from None
    response.headers["Cache-Control"] = "no-store"
    return TeacherChoicesOut(
        offer=[TeacherChoiceOut.of(c) for c in found.offer],
        waiting=[TeacherChoiceOut.of(c) for c in found.waiting],
    )


@router.post("/me/teacher-requests", responses=error_responses(403, 404))
async def post_teacher_request(
    body: AskIn, principal: CurrentPrincipal, use_cases: UseCases, response: Response
) -> AskOut:
    """The student's consent tap: asks the teacher, who gets one silent note (sent inside
    this request, at most 3 s; a failure fails nothing). 404 `not_found`: not a student of
    the shala. 403 `not_allowed`: that person holds no Teacher role there, or the caller is
    on its staff."""
    try:
        asked = await use_cases.ask.execute(
            principal, body.shala_id, body.teacher_id, consent=body.consent
        )
    except NotFound:
        raise _fail(404, "not_found") from None
    except NotAllowed:
        raise _fail(403, "not_allowed") from None
    response.headers["Cache-Control"] = "no-store"
    return AskOut(result=_RESULT[asked.state])


@router.delete("/me/teacher-requests/{teacher_id}", status_code=204)
async def delete_teacher_request(
    teacher_id: UUID, principal: CurrentPrincipal, use_cases: UseCases, response: Response
) -> None:
    """The student takes a request back. Idempotent and silent: the teacher gets no message,
    and the answer is the same whether anything was waiting."""
    await use_cases.withdraw.execute(principal, teacher_id)
    response.headers["Cache-Control"] = "no-store"


@router.get("/me/student-requests")
async def get_student_requests(
    principal: CurrentPrincipal,
    use_cases: UseCases,
    response: Response,
    offset: Annotated[int, Query(ge=0, le=MAX_STUDENTS)] = 0,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> StudentRequestsOut:
    """The people waiting for the caller's answer."""
    page = await use_cases.waiting.execute(principal, offset, limit)
    response.headers["Cache-Control"] = "no-store"
    return StudentRequestsOut(
        requests=[StudentRequestOut.of(r) for r in page.requests],
        total=page.total,
        as_of=page.as_of,
    )


@router.post("/me/student-requests/approve-all")
async def post_approve_all(
    body: ApproveAllIn, principal: CurrentPrincipal, use_cases: UseCases, response: Response
) -> ApprovedAllOut:
    """Confirms who was waiting at `as_of`, so someone who asked a moment later is never
    confirmed unseen."""
    done = await use_cases.approve_all.execute(principal, body.as_of)
    response.headers["Cache-Control"] = "no-store"
    return ApprovedAllOut(approved=done.approved, left=done.left)


@router.post(
    "/me/student-requests/{student_id}/approve",
    status_code=204,
    responses=error_responses(404, 409),
)
async def post_approve(
    student_id: UUID, principal: CurrentPrincipal, use_cases: UseCases, response: Response
) -> None:
    """ "Yes, my student": the link comes to exist. 404 `request_gone` (refetch the list);
    409 `list_full` (the request stays)."""
    _answered(await use_cases.approve.execute(principal, student_id), linked_is_done=True)
    response.headers["Cache-Control"] = "no-store"


@router.post(
    "/me/student-requests/{student_id}/decline", status_code=204, responses=error_responses(404)
)
async def post_decline(
    student_id: UUID, principal: CurrentPrincipal, use_cases: UseCases, response: Response
) -> None:
    """ "Not my student". Idempotent; the student is not told. 404 `request_gone`."""
    _answered(await use_cases.decline.execute(principal, student_id), linked_is_done=False)
    response.headers["Cache-Control"] = "no-store"


@router.post(
    "/me/student-requests/{student_id}/reopen", status_code=204, responses=error_responses(404)
)
async def post_reopen(
    student_id: UUID, principal: CurrentPrincipal, use_cases: UseCases, response: Response
) -> None:
    """Undo of "Not my student", while the request can still be answered. 404
    `request_gone`."""
    _answered(await use_cases.reopen.execute(principal, student_id), linked_is_done=False)
    response.headers["Cache-Control"] = "no-store"
