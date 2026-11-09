"""Shalas (SC-01, ADR-0033). Non-members get 404 `not_found` exactly like an unknown id, so
ids can't be probed; a member without the right gets 403 `not_allowed`. Joining and accepting
a staff link have no endpoint: they always land in the bot (as ID-04's Q12), and no code ever
appears in a URL or a query (Cloud Run logs those). Every answer, errors too, is `no-store`.
"""

import base64
from collections.abc import Awaitable
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field, StringConstraints

from tristhana.api.deps import CurrentPrincipal, app_settings, links, shalas
from tristhana.api.errors import ApiError, ErrorCode, error_responses
from tristhana.application.moon import UnknownLocation
from tristhana.application.policies import (
    NotAllowed,
    NotFound,
    can_announce_to_shala,
    can_manage_schedule,
)
from tristhana.application.ports.shalas import CapReached, MyShala, ShalaCard
from tristhana.application.shalas import ShalaUseCases
from tristhana.application.teacher_links import LinkUseCases
from tristhana.domain.classes import MoonPolicy
from tristhana.domain.rest_days import InvalidDayOff
from tristhana.domain.shalas import (
    KEEP,
    InvalidShalaName,
    ShalaPatch,
    ShalaRole,
    shala_join_url,
    staff_invite_url,
)
from tristhana.settings import Settings

router = APIRouter(tags=["shalas"], responses=error_responses(401, 503))

UseCases = Annotated[ShalaUseCases, Depends(shalas)]
_NO_STORE = {"Cache-Control": "no-store"}
_PAGE_MAX = 50
type Role = Literal["admin", "teacher", "assistant", "office"]  # never "owner"
type MoonPolicyName = Literal["closed", "pranayama", "open"]  # Q117


class ShalaCityOut(BaseModel):
    slug: str
    name: str = Field(description="In the caller's language")


class ShalaMeOut(BaseModel):
    owner: bool
    roles: list[Role]
    student: bool
    schedule: bool = Field(description="May manage classes (SC-02, Q118)")
    announce: bool = Field(default=False, description="May announce to the shala (NT-03, Q163)")


class ShalaStaffOut(BaseModel):
    id: UUID
    name: str | None
    owner: bool
    roles: list[Role]


class ShalaOut(BaseModel):
    id: UUID
    name: str
    city: ShalaCityOut
    zone: str = Field(description="IANA zone of the city; the client builds the label")
    online: bool
    moon_city: str | None = Field(description="null = the same as the city")
    staff: list[ShalaStaffOut] = Field(description="Oldest first")
    students_total: int | None = Field(description="null for a student (Q106)")
    me: ShalaMeOut
    days_off: list[int] | None = Field(description="ISO weekdays; null = not set (SC-02)")
    moon_policy: MoonPolicyName


class MyShalaOut(BaseModel):
    id: UUID
    name: str
    city: str
    online: bool
    side: Literal["staff", "student"]
    owner: bool
    roles: list[Role]


class ShalaStudentOut(BaseModel):
    id: UUID
    name: str | None


class ShalaStudentsOut(BaseModel):
    students: list[ShalaStudentOut]
    total: int


class ShalaIn(BaseModel):
    name: Annotated[str, StringConstraints(max_length=200)]
    city: str
    online: bool = False
    roles: list[Role] = Field(default_factory=list[Role], description="The owner's own roles")


class ShalaPatchIn(BaseModel):
    name: Annotated[str, StringConstraints(max_length=200)] | None = None
    city: str | None = None
    online: bool | None = None
    moon_city: str | None = Field(default=None, description="null = the same as the city")
    days_off: list[Annotated[int, Field(ge=1, le=7)]] | None = Field(
        default=None, description="At most 2; null or [] = not set"
    )
    moon_policy: MoonPolicyName | None = None


class ShalaJoinLinkIn(BaseModel):
    rotate: bool = Field(default=False, description="True: the old link and QR stop working")


class ShalaLinkOut(BaseModel):
    url: str
    qr: str = Field(description="A PNG data URI")


class ShalaStaffInviteIn(BaseModel):
    role: Role


class ShalaStaffInviteOut(ShalaLinkOut):
    expires_at: datetime = Field(description="Single use; works until this instant (UTC)")


class ShalaRolesIn(BaseModel):
    roles: list[Role]


def _roles(roles: frozenset[ShalaRole]) -> list[Role]:
    return sorted(r.value for r in roles)  # type: ignore[misc]


def _fail(status: int, code: ErrorCode) -> ApiError:
    return ApiError(status, code, _NO_STORE)


async def _run[T](work: Awaitable[T]) -> T:
    try:
        return await work
    except NotFound:
        raise _fail(404, "not_found") from None
    except NotAllowed:
        raise _fail(403, "not_allowed") from None
    except CapReached:
        raise _fail(409, "shala_caps") from None
    except InvalidShalaName:
        raise _fail(422, "invalid_shala_name") from None
    except UnknownLocation:
        raise _fail(422, "unknown_location") from None
    except InvalidDayOff:
        raise _fail(422, "invalid_day_off") from None


def _out(card: ShalaCard, use_cases: ShalaUseCases, locale: str) -> ShalaOut:
    city = use_cases.cities.find(card.city)
    return ShalaOut(
        id=card.id,
        name=card.name,
        city=ShalaCityOut(slug=card.city, name=city.name(locale) if city else card.city),
        zone=city.location.tz if city else "Etc/UTC",
        online=card.online,
        moon_city=card.moon_city,
        staff=[
            ShalaStaffOut(id=s.id, name=s.name, owner=s.owner, roles=_roles(s.roles))
            for s in card.staff
        ],
        students_total=card.students_total,
        me=ShalaMeOut(
            owner=card.me.owner,
            roles=_roles(card.me.roles),
            student=card.me.student,
            schedule=can_manage_schedule(card.me),
            announce=can_announce_to_shala(card.me),
        ),
        days_off=None if card.days_off is None else sorted(card.days_off),
        moon_policy=MoonPolicy(card.moon_policy).value,
    )


def _mine(s: MyShala) -> MyShalaOut:
    return MyShalaOut(
        id=s.id,
        name=s.name,
        city=s.city,
        online=s.online,
        side="student" if s.me.student else "staff",
        owner=s.me.owner,
        roles=_roles(s.me.roles),
    )


def _qr(link_cases: LinkUseCases, url: str) -> str:
    return f"data:image/png;base64,{base64.b64encode(link_cases.qr.png(url)).decode()}"


def _bot(settings: Settings) -> str:
    if not settings.telegram_bot_username:  # dev without a bot: there's no link to build
        raise _fail(503, "unavailable")
    return settings.telegram_bot_username


@router.get("/me/shalas")
async def get_my_shalas(
    principal: CurrentPrincipal, use_cases: UseCases, response: Response
) -> list[MyShalaOut]:
    response.headers.update(_NO_STORE)
    return [_mine(s) for s in await _run(use_cases.mine.execute(principal))]


@router.post("/shalas", status_code=201, responses=error_responses(409, 422))
async def post_shala(
    body: ShalaIn, principal: CurrentPrincipal, use_cases: UseCases, response: Response
) -> ShalaOut:
    roles = frozenset(ShalaRole(r) for r in body.roles)
    card = await _run(use_cases.create.execute(principal, body.name, body.city, body.online, roles))
    response.headers.update(_NO_STORE)
    return _out(card, use_cases, principal.account.locale)


@router.get("/shalas/{id}", responses=error_responses(404))
async def get_shala(
    id: UUID, principal: CurrentPrincipal, use_cases: UseCases, response: Response
) -> ShalaOut:
    card = await _run(use_cases.get.execute(principal, id))
    response.headers.update(_NO_STORE)
    return _out(card, use_cases, principal.account.locale)


@router.patch("/shalas/{id}", responses=error_responses(403, 404, 422))
async def patch_shala(
    id: UUID,
    body: ShalaPatchIn,
    principal: CurrentPrincipal,
    use_cases: UseCases,
    response: Response,
) -> ShalaOut:
    sent = body.model_fields_set
    patch = ShalaPatch(
        name=body.name if "name" in sent and body.name is not None else KEEP,
        city=body.city if "city" in sent and body.city is not None else KEEP,
        online=body.online if "online" in sent and body.online is not None else KEEP,
        moon_city=body.moon_city if "moon_city" in sent else KEEP,
        days_off=frozenset(body.days_off or ()) if "days_off" in sent else KEEP,
        moon_policy=(
            MoonPolicy(body.moon_policy)
            if "moon_policy" in sent and body.moon_policy is not None
            else KEEP
        ),
    )
    card = await _run(use_cases.update.execute(principal, id, patch))
    response.headers.update(_NO_STORE)
    return _out(card, use_cases, principal.account.locale)


@router.delete("/shalas/{id}", status_code=204, responses=error_responses(403, 404))
async def delete_shala(
    id: UUID, principal: CurrentPrincipal, use_cases: UseCases, response: Response
) -> None:
    await _run(use_cases.delete.execute(principal, id))
    response.headers.update(_NO_STORE)


@router.get("/shalas/{id}/students", responses=error_responses(403, 404))
async def get_shala_students(
    id: UUID,
    principal: CurrentPrincipal,
    use_cases: UseCases,
    response: Response,
    offset: Annotated[int, Query(ge=0, le=1000)] = 0,
    limit: Annotated[int, Query(ge=1, le=_PAGE_MAX)] = 20,
) -> ShalaStudentsOut:
    page = await _run(use_cases.students.execute(principal, id, offset, limit))
    response.headers.update(_NO_STORE)
    return ShalaStudentsOut(
        students=[ShalaStudentOut(id=s.id, name=s.name) for s in page.students], total=page.total
    )


@router.post("/shalas/{id}/join-link", responses=error_responses(403, 404))
async def post_join_link(
    id: UUID,
    body: ShalaJoinLinkIn,
    principal: CurrentPrincipal,
    use_cases: UseCases,
    link_cases: Annotated[LinkUseCases, Depends(links)],
    settings: Annotated[Settings, Depends(app_settings)],
    response: Response,
) -> ShalaLinkOut:
    bot = _bot(settings)
    get = use_cases.rotate if body.rotate else use_cases.join_link
    url = shala_join_url(bot, await _run(get.execute(principal, id)))
    response.headers.update(_NO_STORE)
    return ShalaLinkOut(url=url, qr=_qr(link_cases, url))


@router.post("/shalas/{id}/staff-invites", responses=error_responses(403, 404, 409))
async def post_staff_invite(
    id: UUID,
    body: ShalaStaffInviteIn,
    principal: CurrentPrincipal,
    use_cases: UseCases,
    link_cases: Annotated[LinkUseCases, Depends(links)],
    settings: Annotated[Settings, Depends(app_settings)],
    response: Response,
) -> ShalaStaffInviteOut:
    bot = _bot(settings)
    invite = await _run(use_cases.invite_staff.execute(principal, id, ShalaRole(body.role)))
    url = staff_invite_url(bot, invite.code)
    response.headers.update(_NO_STORE)
    return ShalaStaffInviteOut(url=url, qr=_qr(link_cases, url), expires_at=invite.expires_at)


@router.put("/shalas/{id}/staff/{account_id}", responses=error_responses(403, 404))
async def put_staff_roles(
    id: UUID,
    account_id: UUID,
    body: ShalaRolesIn,
    principal: CurrentPrincipal,
    use_cases: UseCases,
    response: Response,
) -> ShalaOut:
    roles = frozenset(ShalaRole(r) for r in body.roles)
    card = await _run(use_cases.set_roles.execute(principal, id, account_id, roles))
    response.headers.update(_NO_STORE)
    return _out(card, use_cases, principal.account.locale)


@router.delete(
    "/shalas/{id}/staff/{account_id}", status_code=204, responses=error_responses(403, 404)
)
async def delete_staff(
    id: UUID, account_id: UUID, principal: CurrentPrincipal, use_cases: UseCases, response: Response
) -> None:
    """Idempotent; the caller's own id is leaving (never the owner, Q102)."""
    await _run(use_cases.remove_staff.execute(principal, id, account_id))
    response.headers.update(_NO_STORE)


@router.delete(
    "/shalas/{id}/students/{account_id}", status_code=204, responses=error_responses(403, 404)
)
async def delete_student(
    id: UUID, account_id: UUID, principal: CurrentPrincipal, use_cases: UseCases, response: Response
) -> None:
    """Idempotent; the caller's own id is leaving."""
    await _run(use_cases.remove_student.execute(principal, id, account_id))
    response.headers.update(_NO_STORE)
