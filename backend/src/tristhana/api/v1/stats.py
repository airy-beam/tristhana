"""Practice stats (ST-01..03, ADR-0020): one request per year for the Mini App."""

import datetime as dt
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from tristhana.api.deps import CurrentPrincipal, year_stats
from tristhana.api.errors import ApiError, error_responses
from tristhana.api.v1.days import AutoDayOut
from tristhana.application.stats import GetYearStats, InvalidYear
from tristhana.domain.days import DayStatus
from tristhana.domain.practice import PracticeContext
from tristhana.domain.stats import Summary

router = APIRouter(prefix="/me/stats", tags=["stats"], responses=error_responses(401, 503))

type CellOut = DayStatus | Literal["none"]


class RestCounts(BaseModel):
    rest: int
    moon: int
    ladies: int
    sick: int
    travel: int


class ContextCounts(BaseModel):
    mysore: int
    led: int
    private: int
    self: int  # pyright: ignore[reportSelfClsParameterName]


class SeriesCount(BaseModel):
    number: int = Field(description="0 = short practice, else the furthest series")
    practices: int


class Duration(BaseModel):
    total_min: int
    count: int = Field(description="Practices with a duration")


class SummaryOut(BaseModel):
    practiced: int
    possible: int = Field(description="Practiced + 'No practice' (rest-like never count)")
    skipped: int
    unlogged: int = Field(description="Unmarked days strictly before today (auto excluded)")
    auto: int = Field(default=0, description="Unlogged days shown as rest (moon, day off)")
    rest: RestCounts
    contexts: ContextCounts
    online: int
    series: list[SeriesCount]
    unspecified: int = Field(description="Practiced without details (e.g. pranayama only)")
    duration: Duration

    @classmethod
    def of(cls, s: Summary) -> "SummaryOut":
        return cls(
            practiced=s.practiced,
            possible=s.possible,
            skipped=s.skipped,
            unlogged=s.unlogged,
            auto=s.auto,
            rest=RestCounts(**{k: s.rest.get(DayStatus(k), 0) for k in RestCounts.model_fields}),
            contexts=ContextCounts(**{c.value: s.contexts.get(c, 0) for c in PracticeContext}),
            online=s.online,
            series=[SeriesCount(number=n, practices=c) for n, c in sorted(s.series.items())],
            unspecified=s.unspecified,
            duration=Duration(total_min=s.duration_total, count=s.duration_count),
        )


class MoonMarker(BaseModel):
    date: dt.date
    phase: Literal["purnima", "amavasya"]


class MoonOut(BaseModel):
    location: str
    days: list[MoonMarker]


class Runs(BaseModel):
    current: int | None = Field(description="Practices in a row now (current year only)")
    longest: int = Field(description="Most in a row in this year (a run is counted whole)")


class StatsOut(BaseModel):
    today: dt.date
    timezone_known: bool
    year: int
    first_year: int | None
    cells: list[CellOut] = Field(description="One per date: Jan 1 … min(today, Dec 31)")
    moon: MoonOut
    months: list[SummaryOut] = Field(min_length=12, max_length=12)
    year_total: SummaryOut
    runs: Runs
    auto: list[AutoDayOut] = Field(default=[], description="The year's auto-rest, up to today")


@router.get("", responses=error_responses(422))
async def get_stats(
    principal: CurrentPrincipal,
    use_case: Annotated[GetYearStats, Depends(year_stats)],
    year: Annotated[int | None, Query(description="Default: the local current year")] = None,
) -> StatsOut:
    """The caller's own stats for a year (ladies' holiday included: only the owner calls
    this; the Mini App draws it as rest unless the person switches it on)."""
    try:
        view = await use_case.execute(principal, year)
    except InvalidYear:
        raise ApiError(422, "invalid_year") from None
    s = view.stats
    return StatsOut(
        today=view.today,
        timezone_known=view.timezone_known,
        year=view.year,
        first_year=view.first_year,
        cells=[c if c is not None else "none" for c in s.cells],
        moon=MoonOut(
            location=view.city.slug,
            days=[MoonMarker(date=d.date, phase=d.kind.phase.value) for d in view.moon_days],
        ),
        months=[SummaryOut.of(m) for m in s.months],
        year_total=SummaryOut.of(s.year_total),
        runs=Runs(current=s.current_run, longest=s.longest_run),
        auto=AutoDayOut.all(s.auto),
    )
