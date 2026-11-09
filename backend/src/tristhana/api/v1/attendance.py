"""Class attendance (SC-05, ADR-0039). As SC-01/02: non-members get 404 `not_found` exactly
like an unknown id; a member without the right gets 403 `not_allowed`; every answer is
`no-store`. `key` is the occurrence's rule date (`OccurrenceOut.key`). A mark is presence only:
nothing here reads or writes a log.
"""

import datetime as dt
from collections.abc import Awaitable
from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field

from tristhana.api.deps import CurrentPrincipal, shalas
from tristhana.api.errors import ApiError, ErrorCode, error_responses
from tristhana.api.v1.classes import AttendanceCountsOut, ClassTypeName
from tristhana.application.attendance import AttendanceUseCases, Roster
from tristhana.application.policies import NotAllowed, NotFound
from tristhana.application.shalas import ShalaUseCases
from tristhana.domain.attendance import (
    API_PAGE,
    MAX_DELTA,
    InvalidAttendance,
    NotAttendable,
)

router = APIRouter(tags=["attendance"], responses=error_responses(401, 503))

_NO_STORE = {"Cache-Control": "no-store"}
type State = Literal["claimed", "confirmed"]


def _attendance(request_shalas: Annotated[ShalaUseCases, Depends(shalas)]) -> AttendanceUseCases:
    assert request_shalas.attendance is not None  # noqa: S101 - always wired by the app
    return request_shalas.attendance


UseCases = Annotated[AttendanceUseCases, Depends(_attendance)]


class MyMarkOut(BaseModel):
    class_id: UUID
    key: date
    state: State
    day: dt.date = Field(description="My local date of the class instant (the day to log)")
    log_day: bool = Field(description='Offer "Log this day" (not after Conference or Chanting)')


class RosterOccurrenceOut(BaseModel):
    key: date
    on: date
    start: str = Field(description="HH:MM in the class zone")
    end: str
    starts_at: datetime
    zone: str = Field(description="The class's IANA zone")
    city: str
    type: ClassTypeName
    title: str | None
    cancelled: bool


class RosterPersonOut(BaseModel):
    account_id: UUID
    name: str | None
    state: State | None
    staff: bool


class RosterOut(BaseModel):
    shala_id: UUID
    shala_name: str
    occurrence: RosterOccurrenceOut
    attendable: bool = Field(description="False: read-only (not started, cancelled, > 7 days)")
    confirmed: int
    claimed: int
    people: list[RosterPersonOut] = Field(description="Claims first, then regulars, then names")
    more: bool


class AttendanceIn(BaseModel):
    present: list[UUID] = Field(default_factory=list[UUID], max_length=MAX_DELTA)
    removed: list[UUID] = Field(default_factory=list[UUID], max_length=MAX_DELTA)
    confirm_claims: bool = False


def _fail(status: int, code: ErrorCode) -> ApiError:
    return ApiError(status, code, _NO_STORE)


async def _run[T](work: Awaitable[T]) -> T:
    try:
        return await work
    except NotFound:
        raise _fail(404, "not_found") from None
    except NotAllowed:
        raise _fail(403, "not_allowed") from None
    except NotAttendable:
        raise _fail(409, "not_attendable") from None
    except InvalidAttendance:
        raise _fail(422, "invalid_attendance") from None


def _roster(r: Roster) -> RosterOut:
    o = r.occurrence
    return RosterOut(
        shala_id=r.shala_id,
        shala_name=r.shala_name,
        occurrence=RosterOccurrenceOut(
            key=o.key,
            on=o.on,
            start=f"{o.start:%H:%M}",
            end=f"{o.end:%H:%M}",
            starts_at=o.starts_at,
            zone=r.zone,
            city=r.city,
            type=o.type.value,
            title=o.title,
            cancelled=o.cancelled is not None,
        ),
        attendable=r.attendable,
        confirmed=r.counts.confirmed,
        claimed=r.counts.claimed,
        people=[
            RosterPersonOut(
                account_id=p.account_id,
                name=p.name,
                state=None if p.state is None else p.state.value,
                staff=p.staff,
            )
            for p in r.people
        ],
        more=r.more,
    )


@router.put("/me/attendance/{class_id}/{key}", responses=error_responses(404, 409))
async def claim_attendance(
    class_id: UUID, key: date, principal: CurrentPrincipal, use_cases: UseCases, response: Response
) -> MyMarkOut:
    """🙋 I was there: a member marks a started class of the last 7 days (staff: confirmed)."""
    response.headers.update(_NO_STORE)
    m = await _run(use_cases.claim.execute(principal, class_id, key))
    return MyMarkOut(
        class_id=m.class_id, key=m.key, state=m.state.value, day=m.day, log_day=m.log_day
    )


@router.delete("/me/attendance/{class_id}/{key}", status_code=204)
async def remove_my_attendance(
    class_id: UUID, key: date, principal: CurrentPrincipal, use_cases: UseCases
) -> Response:
    """Removes my own mark, confirmed or not; idempotent."""
    await use_cases.remove.execute(principal, class_id, key)
    return Response(status_code=204, headers=_NO_STORE)


_PATH = "/shalas/{id}/classes/{class_id}/occurrences/{key}/attendance"


@router.get(_PATH, responses=error_responses(403, 404))
async def get_attendance(
    id: UUID,
    class_id: UUID,
    key: date,
    principal: CurrentPrincipal,
    use_cases: UseCases,
    response: Response,
    q: Annotated[str | None, Query(max_length=64)] = None,
    offset: Annotated[int, Query(ge=0, le=10_000)] = 0,
    limit: Annotated[int, Query(ge=1, le=API_PAGE)] = API_PAGE,
) -> RosterOut:
    """Staff only (any seat): the roster of one occurrence."""
    response.headers.update(_NO_STORE)
    roster = await _run(
        use_cases.roster.execute(principal, class_id, key, q, offset, limit, shala=id)
    )
    return _roster(roster)


@router.patch(_PATH, responses=error_responses(403, 404, 409, 422))
async def mark_attendance(
    id: UUID,
    class_id: UUID,
    key: date,
    body: AttendanceIn,
    principal: CurrentPrincipal,
    use_cases: UseCases,
    response: Response,
) -> AttendanceCountsOut:
    """Deltas: `present` → confirmed, `removed` → unmarked, `confirm_claims` → every 🙋."""
    response.headers.update(_NO_STORE)
    counts = await _run(
        use_cases.mark.execute(
            principal, class_id, key, body.present, body.removed, body.confirm_claims, shala=id
        )
    )
    return AttendanceCountsOut(confirmed=counts.confirmed, claimed=counts.claimed)
