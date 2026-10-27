"""After-practice check-in of a practiced day (PR-06, ADR-0024). Owner-only: there is no
read of anyone else's check-ins; `/me/days` carries the caller's own."""

import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Response
from pydantic import BaseModel, Field

from tristhana.api.deps import CurrentPrincipal, clear_check_in, save_check_in
from tristhana.api.errors import ApiError, error_responses
from tristhana.application.check_in import ClearCheckIn, SaveCheckIn
from tristhana.application.check_in_patch import CheckInPatch
from tristhana.application.practice import DayNotPracticed
from tristhana.domain.check_in import CheckIn, CheckInTag, InvalidCheckIn

router = APIRouter(tags=["check-in"])

Slot = Annotated[int, Path(ge=1, le=1, description="One practice per day for now")]
Scale = Annotated[int | None, Field(default=None, ge=1, le=5, strict=True)]


class CheckInBody(BaseModel):
    mood: Scale = Field(default=None, description="1 😔 … 5 😊")
    energy: Scale = Field(default=None, description="1 low … 5 high")
    effort: Scale = Field(default=None, description="1 easy … 5 hard")
    tags: list[CheckInTag] = Field(default=[], max_length=len(CheckInTag))


class CheckInOut(CheckInBody):
    slot: int

    @classmethod
    def of(cls, c: CheckIn) -> "CheckInOut":
        return cls(
            slot=c.slot,
            mood=c.mood,
            energy=c.energy,
            effort=c.effort,
            tags=[t for t in CheckInTag if t in c.tags],  # display order
        )


@router.put("/me/days/{date}/check-ins/{slot}", responses=error_responses(401, 409, 422, 503))
async def put_check_in(
    date: dt.date,
    slot: Slot,
    body: CheckInBody,
    principal: CurrentPrincipal,
    use_case: Annotated[SaveCheckIn, Depends(save_check_in)],
) -> CheckInOut:
    """Replaces the check-in (all fields). The day must be Practiced. All empty reads back
    as no check-in (send DELETE instead)."""
    check_in = CheckIn(
        mood=body.mood,
        energy=body.energy,
        effort=body.effort,
        tags=frozenset(body.tags),
        slot=slot,
    )
    try:
        saved = await use_case.execute(principal, date, CheckInPatch.full(check_in))
    except DayNotPracticed:
        raise ApiError(409, "day_not_practiced") from None
    except InvalidCheckIn:
        raise ApiError(422, "invalid_check_in") from None
    return CheckInOut.of(saved)


@router.delete(
    "/me/days/{date}/check-ins/{slot}", status_code=204, responses=error_responses(401, 503)
)
async def delete_check_in(
    date: dt.date,
    slot: Slot,
    principal: CurrentPrincipal,
    use_case: Annotated[ClearCheckIn, Depends(clear_check_in)],
) -> Response:
    await use_case.execute(principal, date)
    return Response(status_code=204)
