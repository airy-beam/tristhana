"""ID-05: my request for the directory line (ADR-0042). The checker's side has no endpoint:
it lives in the bot only. While no platform admin is configured, `available` is false and a
PUT is 503 `unavailable`; reading and removing my own row always work, so a line can never
get stuck on."""

from datetime import date, datetime
from typing import Annotated, Literal, cast

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field

from tristhana.api.deps import CurrentPrincipal
from tristhana.api.errors import ApiError, error_responses
from tristhana.application.directory_listing import ListingUnavailable, ListingUseCases
from tristhana.domain.directory_listing import (
    InvalidListing,
    Listing,
    ListingMark,
    ListingWait,
    clean,
    wait_left,
)

router = APIRouter(prefix="/me", tags=["directory-listing"], responses=error_responses(401, 503))
_NO_STORE = {"Cache-Control": "no-store"}

type Level = Literal["authorised", "authorised-1", "authorised-2", "certified"]
type Status = Literal["none", "pending", "listed", "not_found", "withdrawn"]


def _use_cases(request: Request) -> ListingUseCases:
    return cast(ListingUseCases, request.app.state.listings)


UseCases = Annotated[ListingUseCases, Depends(_use_cases)]


class ListingMarkOut(BaseModel):
    """All another person sees of a teacher's listing, and only while it is listed."""

    name_as_listed: str
    checked_on: date = Field(description="Shown as month and year only")
    declared_level: Level | None = Field(
        description="The teacher's own words, not checked: show it on the teacher card only"
    )

    @classmethod
    def maybe(cls, mark: ListingMark | None) -> "ListingMarkOut | None":
        if mark is None:
            return None
        return cls(
            name_as_listed=mark.name_as_listed,
            checked_on=mark.checked_on,
            declared_level=mark.level.value if mark.level else None,
        )


class ListingOut(BaseModel):
    status: Status
    name_as_listed: str | None
    region: str | None
    declared_level: Level | None
    note: str | None = Field(description="For the checker only; kept only while pending")
    requested_at: datetime | None
    checked_on: date | None
    can_send: bool = Field(description="False: a new request must wait (one a day)")
    available: bool = Field(
        description="False: requests aren't taken right now (hide the entry and the form); "
        "an existing row can still be read and removed"
    )


class ListingIn(BaseModel):
    name_as_listed: str = Field(max_length=400, description="1-100 characters once cleaned")
    region: str = Field(max_length=400, description="1-60 characters once cleaned")
    declared_level: str | None = Field(default=None, max_length=40)
    note: str | None = Field(default=None, max_length=1200, description="At most 300")


def _out(found: Listing | None, use_cases: ListingUseCases) -> ListingOut:
    now, available = use_cases.clock.now(), use_cases.available
    if found is None:
        return ListingOut(
            status="none",
            name_as_listed=None,
            region=None,
            declared_level=None,
            note=None,
            requested_at=None,
            checked_on=None,
            can_send=True,
            available=available,
        )
    return ListingOut(
        status=found.status.value,
        name_as_listed=found.name_as_listed,
        region=found.region,
        declared_level=found.level.value if found.level else None,
        note=found.note,
        requested_at=found.requested_at,
        checked_on=found.checked_on,
        can_send=wait_left(found, now) is None,
        available=available,
    )


@router.get("/directory-listing")
async def get_directory_listing(
    principal: CurrentPrincipal, use_cases: UseCases, response: Response
) -> ListingOut:
    response.headers.update(_NO_STORE)
    return _out(await use_cases.get.execute(principal), use_cases)


@router.put("/directory-listing", responses=error_responses(409, 422))
async def put_directory_listing(
    body: ListingIn, principal: CurrentPrincipal, use_cases: UseCases, response: Response
) -> ListingOut:
    """Send a request, or edit mine. A waiting request and the level change in place; a new
    request, or a listed name or region that changed, is looked up by a person (409
    `listing_wait`: at most one a day). 422 `invalid_listing`: empty, too long, unknown level."""
    try:
        details = clean(body.name_as_listed, body.region, body.declared_level, body.note)
        saved = await use_cases.request.execute(principal, details)
    except InvalidListing:
        raise ApiError(422, "invalid_listing") from None
    except ListingWait:
        raise ApiError(409, "listing_wait") from None
    except ListingUnavailable:
        raise ApiError(503, "unavailable") from None
    response.headers.update(_NO_STORE)
    return _out(saved.listing, use_cases)


@router.delete("/directory-listing", status_code=204)
async def delete_directory_listing(
    principal: CurrentPrincipal, use_cases: UseCases, response: Response
) -> None:
    """Remove my line and my details (idempotent). No one is told."""
    await use_cases.withdraw.execute(principal)
    response.headers.update(_NO_STORE)
