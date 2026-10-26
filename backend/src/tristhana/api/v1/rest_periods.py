"""The caller's rest periods (WH-01 part 2, ADR-0023): a 🌸 / sick / travel statement over a
few days. Its days show as that status unless something else is logged, and practice
reminders skip them. Dates are local calendar dates; "today" comes from the server."""

import datetime as dt
from collections.abc import Iterable
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from tristhana.api.deps import (
    CurrentPrincipal,
    end_rest_period,
    restore_rest_period,
    start_rest_period,
)
from tristhana.api.errors import ApiError, error_responses
from tristhana.application.rest_periods import EndRestPeriod, RestoreRestPeriod, StartRestPeriod
from tristhana.domain.days import DateInFuture, DayStatus
from tristhana.domain.rest_periods import PAUSE_DAYS, InvalidRestPeriod, PauseOffer, RestPeriod

router = APIRouter(
    prefix="/me/rest-periods", tags=["rest-periods"], responses=error_responses(401, 503)
)

PeriodKind = Literal["ladies", "sick", "travel"]  # inline in the schema (an enum per field)


class RestPeriodOut(BaseModel):
    start: dt.date
    end: dt.date = Field(description="Inclusive")
    kind: Literal["ladies", "sick", "travel", "rest"] = Field(
        description="`rest`: the kind can't be read any more (a lost key): plain rest"
    )

    @classmethod
    def of(cls, p: RestPeriod | None) -> "RestPeriodOut | None":
        if p is None:
            return None
        return cls(start=p.start, end=p.end, kind=p.kind.value)  # type: ignore[arg-type]

    @classmethod
    def all(cls, periods: Iterable[RestPeriod]) -> "list[RestPeriodOut]":
        return [out for p in periods if (out := cls.of(p)) is not None]


class PauseOfferOut(BaseModel):
    """ "For how many days?" after 🌸 / 🤒 / ✈️ on today or yesterday (WH-01)."""

    start: dt.date
    kind: PeriodKind
    reminders_on: bool = Field(description="Practice reminders on: the pause wording")
    choices: list[int] = Field(description="Day counts for the first screen")
    more: list[int] = Field(description="Day counts behind Other…")

    @classmethod
    def of(cls, offer: PauseOffer | None) -> "PauseOfferOut | None":
        if offer is None:
            return None
        choices, more = PAUSE_DAYS[offer.kind]
        return cls(
            start=offer.start,
            kind=offer.kind.value,  # type: ignore[arg-type]
            reminders_on=offer.reminders_on,
            choices=list(choices),
            more=list(more),
        )


class StartBody(BaseModel):
    start: dt.date = Field(description="Today or yesterday (the day just logged)")
    days: int = Field(description="Including `start`; one of the offer's choices or more")
    kind: PeriodKind


class KeepBody(BaseModel):
    end: dt.date = Field(description="Inclusive, as the period was before it was cut")
    kind: PeriodKind


class PeriodResult(BaseModel):
    period: RestPeriodOut | None = Field(description="null: nothing is left (or none)")


@router.post("", responses=error_responses(422))
async def post_rest_period(
    body: StartBody,
    principal: CurrentPrincipal,
    use_case: Annotated[StartRestPeriod, Depends(start_rest_period)],
) -> RestPeriodOut:
    """Starts a period on `start` (logged already). It replaces what it overlaps: an earlier
    period ends the day before, periods starting inside it are removed. 422
    `invalid_rest_period` also when `start` is logged by now with another status."""
    try:
        placed = await use_case.execute(principal, body.start, body.days, DayStatus(body.kind))
    except InvalidRestPeriod:
        raise ApiError(422, "invalid_rest_period") from None
    except DateInFuture:
        raise ApiError(422, "date_in_future") from None
    out = RestPeriodOut.of(placed.period)
    if out is None:  # the day shows another status by now (a stale question)
        raise ApiError(422, "invalid_rest_period")
    return out


@router.put("/{start}", responses=error_responses(422))
async def put_rest_period(
    start: dt.date,
    body: KeepBody,
    principal: CurrentPrincipal,
    use_case: Annotated[RestoreRestPeriod, Depends(restore_rest_period)],
) -> PeriodResult:
    """ "Keep the pause": restores a period cut by 🧘 Practiced exactly as it was (same
    overlap rule as a new one). `period: null` once it is over (nothing left to keep), or
    when no 🧘 Practiced day inside it shows it was cut (never a backfill), or when a newer
    pause started after the cut (never undone)."""
    try:
        kept = await use_case.execute(principal, RestPeriod(start, body.end, DayStatus(body.kind)))
    except InvalidRestPeriod:
        raise ApiError(422, "invalid_rest_period") from None
    return PeriodResult(period=RestPeriodOut.of(kept))


@router.post("/{start}/end")
async def end_rest_period_early(
    start: dt.date,
    principal: CurrentPrincipal,
    use_case: Annotated[EndRestPeriod, Depends(end_rest_period)],
) -> PeriodResult:
    """End early: the period stops covering today (removed when ≤ 1 day is left; past days
    stay). Idempotent."""
    ended = await use_case.execute(principal, start)
    return PeriodResult(period=RestPeriodOut.of(ended.period))
