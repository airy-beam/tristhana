"""The caller's teachers and students (ID-04, ADR-0030), and what a teacher sees of a
student (ST-06, ADR-0031). The invite code never appears in a URL or a query (Cloud Run
logs those), and accepting an invite has no endpoint: it always lands in the bot (Q12)."""

import base64
from datetime import date as date_
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field

from tristhana.api.deps import (
    CurrentPrincipal,
    app_settings,
    links,
    mark_for_student,
    progression_track,
    teacher_view,
)
from tristhana.api.errors import ApiError, error_responses
from tristhana.api.v1.directory_listing import ListingMarkOut
from tristhana.api.v1.practice import Length
from tristhana.api.v1.progression import PositionOut
from tristhana.application.policies import Principal
from tristhana.application.ports.teacher_links import Links, LinksChanged, NotLinked
from tristhana.application.progression import ProgressionChanged
from tristhana.application.teacher_links import LinkUseCases
from tristhana.application.teacher_marks import MarkForStudent
from tristhana.application.teacher_view import TeacherViewUseCases
from tristhana.domain.progression import Position, Progression, Track, teacher_targets
from tristhana.domain.teacher_links import MAX_STUDENTS, effective_primary, invite_url
from tristhana.domain.teacher_view import SharedDay
from tristhana.settings import Settings

router = APIRouter(prefix="/me", tags=["links"], responses=error_responses(401, 503))

UseCases = Annotated[LinkUseCases, Depends(links)]
ViewCases = Annotated[TeacherViewUseCases, Depends(teacher_view)]
MarkCase = Annotated[MarkForStudent, Depends(mark_for_student)]
TrackDep = Annotated[Track, Depends(progression_track)]


class TeacherOut(BaseModel):
    id: UUID
    name: str | None
    primary: bool = Field(description="The main teacher: the chosen one, else the oldest link")
    primary_chosen: bool = Field(description="False: `primary` is the automatic default")
    linked_at: datetime
    listing: ListingMarkOut | None = Field(
        default=None, description="ID-05: the directory line, only while listed; else null"
    )


class StudentOut(BaseModel):
    """No primary field: a teacher never learns whether they are someone's main teacher."""

    id: UUID
    name: str | None
    linked_at: datetime


class LinksOut(BaseModel):
    teachers: list[TeacherOut]
    students: list[StudentOut]

    @classmethod
    def of(cls, found: Links) -> "LinksOut":
        main = effective_primary(found.teachers)
        return cls(
            teachers=[
                TeacherOut(
                    id=t.id,
                    name=t.name,
                    primary=t.id == main,
                    primary_chosen=t.chosen_primary,
                    linked_at=t.linked_at,
                    listing=ListingMarkOut.maybe(found.listings.get(t.id)),
                )
                for t in found.teachers
            ],
            students=[
                StudentOut(id=s.id, name=s.name, linked_at=s.linked_at) for s in found.students
            ],
        )


class InviteIn(BaseModel):
    rotate: bool = Field(default=False, description="True: the old link and QR stop working")


class InviteOut(BaseModel):
    url: str
    qr: str = Field(description="A PNG data URI")


@router.get("/links")
async def get_links(
    principal: CurrentPrincipal, use_cases: UseCases, response: Response
) -> LinksOut:
    response.headers["Cache-Control"] = "no-store"
    return LinksOut.of(await use_cases.get.execute(principal))


@router.post("/invite")
async def post_invite(
    body: InviteIn,
    principal: CurrentPrincipal,
    use_cases: UseCases,
    settings: Annotated[Settings, Depends(app_settings)],
    response: Response,
) -> InviteOut:
    if not settings.telegram_bot_username:  # dev without a bot: there's no link to build
        raise ApiError(503, "unavailable")
    get = use_cases.rotate if body.rotate else use_cases.invite
    url = invite_url(settings.telegram_bot_username, await get.execute(principal))
    png = base64.b64encode(use_cases.qr.png(url)).decode()
    response.headers["Cache-Control"] = "no-store"
    return InviteOut(url=url, qr=f"data:image/png;base64,{png}")


@router.put("/teachers/{id}/primary", responses=error_responses(404, 409))
async def put_primary(
    id: UUID, principal: CurrentPrincipal, use_cases: UseCases, response: Response
) -> LinksOut:
    try:
        await use_cases.primary.execute(principal, id)
    except NotLinked:
        raise ApiError(404, "not_linked") from None
    except LinksChanged:
        raise ApiError(409, "links_changed") from None
    response.headers["Cache-Control"] = "no-store"
    return LinksOut.of(await use_cases.get.execute(principal))


@router.delete("/teachers/{id}", status_code=204)
async def delete_teacher(
    id: UUID, principal: CurrentPrincipal, use_cases: UseCases, response: Response
) -> None:
    await use_cases.remove_teacher.execute(principal, id)
    response.headers["Cache-Control"] = "no-store"


@router.delete("/students/{id}", status_code=204)
async def delete_student(
    id: UUID, principal: CurrentPrincipal, use_cases: UseCases, response: Response
) -> None:
    await use_cases.remove_student.execute(principal, id)
    response.headers["Cache-Control"] = "no-store"


class DayOut(BaseModel):
    date: date_
    state: SharedDay | None
    length: Length | None


class StudentTodayOut(BaseModel):
    id: UUID
    name: str | None
    today: SharedDay | None


class StudentsOut(BaseModel):
    students: list[StudentTodayOut]
    total: int


class StudentCardOut(BaseModel):
    id: UUID
    name: str | None
    days: list[DayOut]
    last_asana: PositionOut | None
    next_asanas: list[PositionOut] = Field(
        description="PR-08 Phase 3: the stops this teacher may mark, in order (0-3); "
        "empty when unset or at the end of the confirmed series"
    )
    quiet: bool


class NewAsanaIn(BaseModel):
    seen: PositionOut = Field(alias="from", description="The card's `last_asana`")
    to: PositionOut = Field(description="One of the card's `next_asanas`")


@router.get("/students")
async def get_students(
    principal: CurrentPrincipal,
    use_cases: ViewCases,
    response: Response,
    offset: Annotated[int, Query(ge=0, le=MAX_STUDENTS)] = 0,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> StudentsOut:
    found, total = await use_cases.students.execute(principal, offset, limit)
    response.headers["Cache-Control"] = "no-store"
    return StudentsOut(
        students=[StudentTodayOut(id=s.id, name=s.name, today=s.today) for s in found], total=total
    )


async def _card(principal: Principal, id: UUID, use_cases: TeacherViewUseCases) -> StudentCardOut:
    try:
        card = await use_cases.student.execute(principal, id)
    except NotLinked:
        raise ApiError(404, "not_linked") from None
    return StudentCardOut(
        id=card.id,
        name=card.name,
        days=[
            DayOut(date=d.date, state=d.shown, length=Length.of(d.length) if d.length else None)
            for d in card.days
        ],
        last_asana=PositionOut.maybe(card.last_asana),
        next_asanas=[PositionOut.of(p) for p in card.next_asanas],
        quiet=card.quiet,
    )


@router.get("/students/{id}", responses=error_responses(404))
async def get_student(
    id: UUID, principal: CurrentPrincipal, use_cases: ViewCases, response: Response
) -> StudentCardOut:
    card = await _card(principal, id, use_cases)
    response.headers["Cache-Control"] = "no-store"
    return card


@router.post("/students/{id}/new-asana", responses=error_responses(404, 409, 422))
async def post_new_asana(
    id: UUID,
    body: NewAsanaIn,
    principal: CurrentPrincipal,
    mark: MarkCase,
    use_cases: ViewCases,
    track: TrackDep,
    response: Response,
) -> StudentCardOut:
    """PR-08 Phase 3: a linked teacher marks one of the card's `next_asanas`; the student gets
    one silent message and can undo it. Not optimistic: the answer is the refreshed card, the
    same whatever the student's history or the message's delivery. 404 `not_linked`;
    409 `progression_changed` (out of date, or a retry: refetch the card); 422
    `invalid_progression` (`to` isn't within the next stops of `from`)."""
    seen = Position(body.seen.series, body.seen.last)
    target = Position(body.to.series, body.to.last)
    if target not in teacher_targets(track, Progression(seen)):
        raise ApiError(422, "invalid_progression")
    try:
        await mark.execute(principal, id, seen, target)
    except NotLinked:
        raise ApiError(404, "not_linked") from None
    except ProgressionChanged:
        raise ApiError(409, "progression_changed") from None
    card = await _card(principal, id, use_cases)
    response.headers["Cache-Control"] = "no-store"
    return card
