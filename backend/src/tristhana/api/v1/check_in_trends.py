"""Check-in trends (ST-05): the caller's own averages for the last 12 calendar months."""

import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from tristhana.api.deps import CurrentPrincipal, get_check_in_trends
from tristhana.api.errors import error_responses
from tristhana.application.check_in_trends import GetCheckInTrends
from tristhana.domain.check_in_trends import (
    MIN_BUCKET,
    MIN_TOTAL,
    Average,
    Averages,
    MoonBucket,
    Scale,
)

router = APIRouter(
    prefix="/me/check-in-trends", tags=["check-ins"], responses=error_responses(401, 503)
)


class AvgOut(BaseModel):
    mean: float = Field(description="The average on the 1-5 scale, to one decimal")
    n: int = Field(description="How many check-ins it comes from")

    @classmethod
    def of(cls, a: Average | None) -> "AvgOut | None":
        return None if a is None else cls(mean=a.tenths / 10, n=a.n)


class ScalesOut(BaseModel):
    """Null: fewer than `min_bucket` check-ins carry that scale there."""

    mood: AvgOut | None
    energy: AvgOut | None
    effort: AvgOut | None

    @classmethod
    def of(cls, a: Averages) -> "ScalesOut":
        return cls(
            mood=AvgOut.of(a[Scale.MOOD]),
            energy=AvgOut.of(a[Scale.ENERGY]),
            effort=AvgOut.of(a[Scale.EFFORT]),
        )


class TrendsMonthOut(ScalesOut):
    month: str = Field(description="YYYY-MM", pattern=r"^\d{4}-\d{2}$")


class TrendsMoonOut(BaseModel):
    location: str = Field(description="The city slug the moon days were read for")
    full: ScalesOut = Field(description="The full-moon day, the day before and the day after")
    new: ScalesOut = Field(description="The new-moon day, the day before and the day after")
    other: ScalesOut


class CheckInTrendsOut(BaseModel):
    from_: dt.date = Field(serialization_alias="from", description="The window's first day")
    to: dt.date
    total: int = Field(description="Check-ins with at least one scale in the window")
    enough: bool = Field(description="False: under `min_total`, so nothing else is sent")
    min_total: int
    min_bucket: int
    months: list[TrendsMonthOut] = Field(description="12, oldest first; empty unless `enough`")
    weekdays: list[ScalesOut] | None = Field(description="7, Monday first")
    moon: TrendsMoonOut | None


@router.get("")
async def get_my_check_in_trends(
    principal: CurrentPrincipal,
    use_case: Annotated[GetCheckInTrends, Depends(get_check_in_trends)],
) -> CheckInTrendsOut:
    """Owner only (teachers and shalas never see check-ins). Averages only, never a date of a
    practice or a rest; an average with too few check-ins behind it is null."""
    view = await use_case.execute(principal)
    t = view.trends
    return CheckInTrendsOut(
        from_=t.start,
        to=t.end,
        total=t.total,
        enough=t.enough,
        min_total=MIN_TOTAL,
        min_bucket=MIN_BUCKET,
        months=[
            TrendsMonthOut(
                month=f"{m.year:04d}-{m.month:02d}",
                mood=AvgOut.of(a[Scale.MOOD]),
                energy=AvgOut.of(a[Scale.ENERGY]),
                effort=AvgOut.of(a[Scale.EFFORT]),
            )
            for m, a in t.months
        ],
        weekdays=None if t.weekdays is None else [ScalesOut.of(a) for a in t.weekdays],
        moon=(
            None
            if t.moon is None
            else TrendsMoonOut(
                location=view.city.slug,
                full=ScalesOut.of(t.moon[MoonBucket.FULL]),
                new=ScalesOut.of(t.moon[MoonBucket.NEW]),
                other=ScalesOut.of(t.moon[MoonBucket.OTHER]),
            )
        ),
    )
