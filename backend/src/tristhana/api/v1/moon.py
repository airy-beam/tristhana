"""Moon days and reminder settings (MD-03). Dates are the followed city's local dates."""

import datetime as dt
import hashlib
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, Query, Response
from pydantic import BaseModel, Field

from tristhana.api.deps import (
    CurrentPrincipal,
    cities,
    moon_view,
    notification_settings,
    set_moon_location,
)
from tristhana.api.errors import ApiError, error_responses
from tristhana.application.moon import (
    GetMoonView,
    NotificationSettingsUseCase,
    SetMoonLocation,
    UnknownLocation,
)
from tristhana.domain.days import InvalidRange
from tristhana.domain.moon import Cities, MoonDayKind
from tristhana.domain.notifications import (
    InvalidSettings,
    MoonReminders,
    NotificationSettings,
    QuietHours,
)

router = APIRouter(tags=["moon"])


class CityOut(BaseModel):
    slug: str
    name_en: str
    name_ru: str
    timezone: str


class Location(BaseModel):
    slug: str
    explicit: bool = Field(description="False: the default city (Mysuru), never chosen")


class MoonDayOut(BaseModel):
    date: dt.date
    kind: MoonDayKind
    phase: Literal["purnima", "amavasya"]


class MoonDays(BaseModel):
    location: Location
    today: dt.date
    days: list[MoonDayOut]


class LocationBody(BaseModel):
    slug: str | None = Field(description="A city slug; null = back to the default")


class MoonSettings(BaseModel):
    offsets: list[Literal[1, 3, 7]] = Field(description="Days before; [] = off")
    at: dt.time = Field(description="Local wall clock, 15-minute grid")


class Quiet(BaseModel):
    start: dt.time
    end: dt.time


class NotificationSettingsBody(BaseModel):
    moon: MoonSettings
    quiet: Quiet
    daily_cap: int = Field(ge=1, le=10)


class NotificationSettingsOut(NotificationSettingsBody):
    timezone: str | None = Field(description="Reminders need it; null = none are sent")


def _settings_out(s: NotificationSettings, zone: str | None) -> NotificationSettingsOut:
    return NotificationSettingsOut(
        moon=MoonSettings(offsets=sorted(s.moon.offsets), at=s.moon.at),  # type: ignore[arg-type]
        quiet=Quiet(start=s.quiet.start, end=s.quiet.end),
        daily_cap=s.daily_cap,
        timezone=zone,
    )


@router.get(
    "/moon/cities", responses={304: {"description": "Not modified"}}, response_model=list[CityOut]
)
async def get_cities(
    response: Response,
    directory: Annotated[Cities, Depends(cities)],
    if_none_match: Annotated[str | None, Header()] = None,
) -> list[CityOut] | Response:
    """Public: the cities whose moon calendars can be followed (the default first)."""
    out = [
        CityOut(slug=c.slug, name_en=c.name_en, name_ru=c.name_ru, timezone=c.location.tz)
        for c in directory.ordered("en")
    ]
    etag = '"' + hashlib.sha256(repr(out).encode()).hexdigest()[:16] + '"'
    headers = {"ETag": etag, "Cache-Control": "public, max-age=3600"}
    if etag in {t.strip().removeprefix("W/") for t in (if_none_match or "").split(",")}:
        return Response(status_code=304, headers=headers)
    response.headers.update(headers)
    return out


@router.get("/me/moon-days", responses=error_responses(401, 422, 503))
async def get_moon_days(
    principal: CurrentPrincipal,
    use_case: Annotated[GetMoonView, Depends(moon_view)],
    start: Annotated[dt.date | None, Query(alias="from")] = None,
    end: Annotated[dt.date | None, Query(alias="to")] = None,
) -> MoonDays:
    """Defaults to today … +60 days; at most 371 days per request."""
    try:
        view = await use_case.execute(principal, start, end)
    except InvalidRange:
        raise ApiError(422, "invalid_range") from None
    return MoonDays(
        location=Location(slug=view.city.slug, explicit=view.explicit),
        today=view.today,
        days=[MoonDayOut(date=d.date, kind=d.kind, phase=d.kind.phase.value) for d in view.days],
    )


@router.put("/me/moon-location", responses=error_responses(401, 422, 503))
async def put_moon_location(
    body: LocationBody,
    principal: CurrentPrincipal,
    use_case: Annotated[SetMoonLocation, Depends(set_moon_location)],
    directory: Annotated[Cities, Depends(cities)],
) -> Location:
    try:
        account = await use_case.execute(principal, body.slug)
    except UnknownLocation:
        raise ApiError(422, "unknown_location") from None
    slug = account.moon_location or directory.default.slug
    return Location(slug=slug, explicit=account.moon_location is not None)


@router.get("/me/notification-settings", responses=error_responses(401, 503))
async def get_notification_settings(
    principal: CurrentPrincipal,
    use_case: Annotated[NotificationSettingsUseCase, Depends(notification_settings)],
) -> NotificationSettingsOut:
    return _settings_out(await use_case.get(principal), principal.account.timezone)


@router.put("/me/notification-settings", responses=error_responses(401, 422, 503))
async def put_notification_settings(
    body: NotificationSettingsBody,
    principal: CurrentPrincipal,
    use_case: Annotated[NotificationSettingsUseCase, Depends(notification_settings)],
) -> NotificationSettingsOut:
    settings = NotificationSettings(
        moon=MoonReminders(frozenset(body.moon.offsets), body.moon.at.replace(tzinfo=None)),
        quiet=QuietHours(
            body.quiet.start.replace(tzinfo=None), body.quiet.end.replace(tzinfo=None)
        ),
        daily_cap=body.daily_cap,
    )
    try:
        saved = await use_case.save(principal, settings)
    except InvalidSettings:
        raise ApiError(422, "invalid_settings") from None
    return _settings_out(saved, principal.account.timezone)
