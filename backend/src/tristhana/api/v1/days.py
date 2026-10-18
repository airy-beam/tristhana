"""The caller's day statuses (PR-01, PR-04). Dates are local calendar dates; "today" comes
from the server (the account's zone), never from the client."""

import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field

from tristhana.api.deps import CurrentPrincipal, clear_day_status, get_days, set_day_status
from tristhana.api.errors import ApiError, error_responses
from tristhana.api.v1.practice import PracticeOut
from tristhana.application.days import ClearDayStatus, GetDays, SetDayStatus
from tristhana.domain.days import DateInFuture, DateTooEarly, DayLog, DayStatus, InvalidRange

router = APIRouter(prefix="/me/days", tags=["days"], responses=error_responses(401, 503))


class Day(BaseModel):
    date: dt.date
    status: DayStatus
    practices: list[PracticeOut] = Field(default=[], description="Only on a practiced day")

    @classmethod
    def of(cls, day: DayLog) -> "Day":
        return cls(
            date=day.local_date,
            status=day.status,
            practices=[PracticeOut.of(p) for p in day.practices],
        )


class Days(BaseModel):
    today: dt.date = Field(description="The caller's local date (server-computed)")
    timezone_known: bool = Field(description="False: today comes from a provisional zone")
    days: list[Day] = Field(description="Logged days only, oldest first")


class DayStatusBody(BaseModel):
    status: DayStatus


@router.get("", responses=error_responses(422))
async def list_days(
    principal: CurrentPrincipal,
    use_case: Annotated[GetDays, Depends(get_days)],
    start: Annotated[dt.date | None, Query(alias="from")] = None,
    end: Annotated[dt.date | None, Query(alias="to")] = None,
) -> Days:
    """Defaults to the 7 days ending today; at most 371 days per request."""
    try:
        view = await use_case.execute(principal, start, end)
    except InvalidRange:
        raise ApiError(422, "invalid_range") from None
    return Days(
        today=view.today, timezone_known=view.timezone_known, days=[Day.of(d) for d in view.days]
    )


@router.put("/{date}", responses=error_responses(422))
async def put_day(
    date: dt.date,
    body: DayStatusBody,
    principal: CurrentPrincipal,
    use_case: Annotated[SetDayStatus, Depends(set_day_status)],
) -> Day:
    try:
        return Day.of(await use_case.execute(principal, date, body.status))
    except DateInFuture:
        raise ApiError(422, "date_in_future") from None
    except DateTooEarly:
        raise ApiError(422, "date_too_early") from None


@router.delete("/{date}", status_code=204)
async def delete_day(
    date: dt.date,
    principal: CurrentPrincipal,
    use_case: Annotated[ClearDayStatus, Depends(clear_day_status)],
) -> Response:
    """Idempotent: 204 even if nothing was logged."""
    await use_case.execute(principal, date)
    return Response(status_code=204)
