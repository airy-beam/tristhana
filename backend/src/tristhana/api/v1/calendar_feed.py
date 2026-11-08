"""SC-06: my calendar subscription link (ADR-0036). The token is shown only to its owner."""

from datetime import date, datetime
from typing import Annotated, cast

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field

from tristhana.api.deps import CurrentPrincipal
from tristhana.api.errors import error_responses
from tristhana.application.calendar_feed import CalendarFeedUseCases, feed_urls
from tristhana.application.ports.calendar_feed import FeedLink

router = APIRouter(tags=["calendar-feed"], responses=error_responses(401, 503))
_NO_STORE = {"Cache-Control": "no-store"}


def _use_cases(request: Request) -> CalendarFeedUseCases:
    return cast(CalendarFeedUseCases, request.app.state.calendar_feed)


UseCases = Annotated[CalendarFeedUseCases, Depends(_use_cases)]


class CalendarFeedOut(BaseModel):
    on: bool
    available: bool = Field(description="False: calendar links aren't offered (no public URL)")
    url: str | None = Field(description="The https feed to copy; a secret: never share it")
    google_url: str | None = Field(description="Google Calendar's add-by-URL page")
    subscribe_url: str | None = Field(description="Redirects to webcal:// (Apple, Outlook)")
    created_at: datetime | None
    fetched_on: date | None = Field(description="The UTC date a calendar last fetched it")


def _out(use_cases: CalendarFeedUseCases, link: FeedLink | None) -> CalendarFeedOut:
    if link is None or not use_cases.available:
        return CalendarFeedOut(
            on=False,
            available=use_cases.available,
            url=None,
            google_url=None,
            subscribe_url=None,
            created_at=None,
            fetched_on=None,
        )
    urls = feed_urls(use_cases.public_url, link.token)
    return CalendarFeedOut(
        on=True,
        available=True,
        url=urls.feed,
        google_url=urls.google,
        subscribe_url=urls.subscribe,
        created_at=link.created_at,
        fetched_on=link.fetched_on,
    )


@router.get("/me/calendar-feed")
async def get_calendar_feed(
    principal: CurrentPrincipal, use_cases: UseCases, response: Response
) -> CalendarFeedOut:
    response.headers.update(_NO_STORE)
    if not use_cases.available:
        return _out(use_cases, None)
    return _out(use_cases, await use_cases.get.execute(principal))


@router.post("/me/calendar-feed")
async def post_calendar_feed(
    principal: CurrentPrincipal, use_cases: UseCases, response: Response
) -> CalendarFeedOut:
    """Create my link; if I have one, return it unchanged (a stale "Create" never breaks a
    subscribed calendar). A new link is `POST /me/calendar-feed/rotate`."""
    response.headers.update(_NO_STORE)
    if not use_cases.available:
        return _out(use_cases, None)
    return _out(use_cases, await use_cases.create.execute(principal))


@router.post("/me/calendar-feed/rotate")
async def rotate_calendar_feed(
    principal: CurrentPrincipal, use_cases: UseCases, response: Response
) -> CalendarFeedOut:
    """Replace my link with a new one: the old link stops working at once."""
    response.headers.update(_NO_STORE)
    if not use_cases.available:
        return _out(use_cases, None)
    return _out(use_cases, await use_cases.create.execute(principal, rotate=True))


@router.delete("/me/calendar-feed", status_code=204)
async def delete_calendar_feed(
    principal: CurrentPrincipal, use_cases: UseCases, response: Response
) -> None:
    """Turn it off (idempotent): the link stops working at once."""
    await use_cases.revoke.execute(principal)
    response.headers.update(_NO_STORE)
