"""The caller's teachers and students (ID-04, ADR-0030). Names only cross accounts. The
invite code never appears in a URL or a query (Cloud Run logs those), and accepting an
invite has no endpoint: it always lands in the bot (Q12)."""

import base64
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field

from tristhana.api.deps import CurrentPrincipal, app_settings, links
from tristhana.api.errors import ApiError, error_responses
from tristhana.application.ports.teacher_links import Links, LinksChanged, NotLinked
from tristhana.application.teacher_links import LinkUseCases
from tristhana.domain.teacher_links import effective_primary, invite_url
from tristhana.settings import Settings

router = APIRouter(prefix="/me", tags=["links"], responses=error_responses(401, 503))

UseCases = Annotated[LinkUseCases, Depends(links)]


class TeacherOut(BaseModel):
    id: UUID
    name: str | None
    primary: bool = Field(description="The main teacher: the chosen one, else the oldest link")
    primary_chosen: bool = Field(description="False: `primary` is the automatic default")
    linked_at: datetime


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
