"""The caller's day statuses (PR-01, PR-04). Dates are local calendar dates; "today" comes
from the server (the account's zone), never from the client."""

import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field

from tristhana.api.deps import CurrentPrincipal, clear_day_status, get_days, set_day_status
from tristhana.api.errors import ApiError, error_responses
from tristhana.api.v1.practice import PracticeOut
from tristhana.api.v1.rest_periods import PauseOfferOut, RestPeriodOut
from tristhana.application.days import ClearDayStatus, GetDays, SetDayStatus
from tristhana.domain.days import DateInFuture, DateTooEarly, DayLog, DayStatus, InvalidRange
from tristhana.domain.rest_days import AutoDay, AutoKind

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


class AutoDayOut(BaseModel):
    """An unlogged day shown as rest (PR-09, ADR-0022): never stored, a log always wins."""

    date: dt.date
    kind: AutoKind
    also_day_off: bool = Field(default=False, description="A moon day on the weekly day off")

    @classmethod
    def all(cls, auto: dict[dt.date, AutoDay]) -> "list[AutoDayOut]":
        return [
            cls(date=d, kind=a.kind, also_day_off=a.also_day_off) for d, a in sorted(auto.items())
        ]


class Days(BaseModel):
    today: dt.date = Field(description="The caller's local date (server-computed)")
    timezone_known: bool = Field(description="False: today comes from a provisional zone")
    days: list[Day] = Field(description="Logged days only, oldest first")
    auto: list[AutoDayOut] = Field(default=[], description="Unlogged days shown as rest")
    moon_location: str = Field(description="The city auto moon days follow")
    periods: list[RestPeriodOut] = Field(
        default=[],
        description="Rest periods overlapping the window, unclipped (WH-01): their unlogged "
        "days up to today show as their kind; `auto` never includes them",
    )
    practice_on: bool = Field(default=False, description="Practice reminders on (labels)")


class DaySaved(Day):
    pause_offer: PauseOfferOut | None = Field(
        default=None, description="Ask: for how many days? (after 🌸/🤒/✈️ today or yesterday)"
    )
    period: RestPeriodOut | None = Field(default=None, description="The period covering it")
    cut: RestPeriodOut | None = Field(
        default=None,
        description="A period 🧘 Practiced just cut, as it was (for 'keep the pause')",
    )


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
        today=view.today,
        timezone_known=view.timezone_known,
        days=[Day.of(d) for d in view.days],
        auto=AutoDayOut.all(view.auto),
        moon_location=view.city.slug,
        periods=RestPeriodOut.all(view.periods),
        practice_on=view.practice_on,
    )


@router.put("/{date}", responses=error_responses(422))
async def put_day(
    date: dt.date,
    body: DayStatusBody,
    principal: CurrentPrincipal,
    use_case: Annotated[SetDayStatus, Depends(set_day_status)],
) -> DaySaved:
    """Overwrites any earlier status. Inside a rest period (WH-01): 🧘 Practiced ends it the
    day before (on its start day, removes it) and returns it as `cut`; other statuses
    change only that day. After 🌸/🤒/✈️ on today or yesterday, `pause_offer` may ask for
    how many days (POST /me/rest-periods)."""
    try:
        saved = await use_case.execute(principal, date, body.status)
    except DateInFuture:
        raise ApiError(422, "date_in_future") from None
    except DateTooEarly:
        raise ApiError(422, "date_too_early") from None
    day = Day.of(saved.day)
    return DaySaved(
        date=day.date,
        status=day.status,
        practices=day.practices,
        pause_offer=PauseOfferOut.of(saved.offer),
        period=RestPeriodOut.of(saved.period),
        cut=RestPeriodOut.of(saved.cut),
    )


@router.delete("/{date}", status_code=204)
async def delete_day(
    date: dt.date,
    principal: CurrentPrincipal,
    use_case: Annotated[ClearDayStatus, Depends(clear_day_status)],
) -> Response:
    """Idempotent: 204 even if nothing was logged. Removes a rest period starting that day."""
    await use_case.execute(principal, date)
    return Response(status_code=204)
