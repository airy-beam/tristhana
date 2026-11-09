"""Badges (GM-02, ADR-0041): the caller's own, earned only, in file order."""

import datetime as dt
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from tristhana.api.deps import CurrentPrincipal, get_badges
from tristhana.api.errors import error_responses
from tristhana.application.badges import GetBadges
from tristhana.domain.badges import Earned, RuleKind

router = APIRouter(prefix="/me/badges", tags=["badges"], responses=error_responses(401, 503))


class BadgeOut(BaseModel):
    key: str = Field(description="Fluent `badge-<key>`; an unknown key is skipped by the client")
    group: Literal["practice", "asanas"]
    icon: str
    earned_on: dt.date | None = Field(
        description="The date it came from; null = a practice count kept by the GM-01 ledger"
    )
    at_record_start: bool = Field(description="An asana held when the record began")
    count: int | None = Field(description="For the copy: practices, Led, moon days…")
    days: int | None = Field(description="Return: days with no practice before it")
    before: str | None = Field(description="Before dawn: the local wall-clock threshold, HH:MM")
    series: str | None = Field(description="Series slug (series and stop badges)")
    stop: str | None = Field(description="Stop key in `series` (stop badges)")
    item: str | None = Field(description="Milestone item key (label: `milestone-label`)")

    @classmethod
    def of(cls, e: Earned) -> "BadgeOut":
        d = e.badge
        target = d.target
        return cls(
            key=d.key,
            group=d.group.value,
            icon=d.icon,
            earned_on=e.on,
            at_record_start=e.at_record_start,
            count=d.count,
            days=d.days,
            before=d.before.strftime("%H:%M") if d.before else None,
            series=target.series if target else None,
            stop=target.key if target and d.rule is RuleKind.STOP else None,
            item=d.item,
        )


class BadgesOut(BaseModel):
    badges: list[BadgeOut]


@router.get("")
async def get_my_badges(
    principal: CurrentPrincipal, use_case: Annotated[GetBadges, Depends(get_badges)]
) -> BadgesOut:
    """Owner only (teachers and shalas never see badges). Derived on every read: nothing is
    stored, and a badge follows the data it comes from."""
    view = await use_case.execute(principal)
    return BadgesOut(badges=[BadgeOut.of(e) for e in view.earned])
