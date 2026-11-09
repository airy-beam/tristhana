"""ST-07: shareable cards (ADR-0040). The Mini App asks for a card, shows the returned image
URL as a preview and hands it to Telegram (`shareToStory`, `downloadFile`); "Send to my
chat" makes the bot post the same PNG. The image itself is served at `/share/v1/` (outside
`/api/v1`): the URL is the capability."""

from datetime import datetime
from typing import Annotated, Literal, cast

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from tristhana.api.deps import CurrentPrincipal
from tristhana.api.errors import ApiError, error_responses
from tristhana.application.share_cards import (
    AlreadySent,
    AsanaSubject,
    BotUnreachable,
    CardNotFound,
    CountSubject,
    InvalidPeriod,
    MonthSubject,
    NothingToShare,
    RateLimited,
    SendFailed,
    ShareCardUseCases,
    Subject,
    YearSubject,
)
from tristhana.domain.share_cards import CardFormat

router = APIRouter(
    prefix="/me/share-cards", tags=["share-cards"], responses=error_responses(401, 503)
)


def _use_cases(request: Request) -> ShareCardUseCases:
    return cast(ShareCardUseCases, request.app.state.share_cards)


UseCases = Annotated[ShareCardUseCases, Depends(_use_cases)]


class MonthCardIn(BaseModel):
    kind: Literal["month"]
    year: int = Field(ge=2000, le=9999)
    month: int = Field(ge=1, le=12)


class YearCardIn(BaseModel):
    kind: Literal["year"]
    year: int = Field(ge=2000, le=9999)


class AsanaCardIn(BaseModel):
    kind: Literal["asana"]
    event_id: int = Field(ge=1, description="A given asana from My asanas (PR-08)")


class CountCardIn(BaseModel):
    kind: Literal["count"]
    count: int = Field(ge=1, le=100_000, description="A practice count already reached (GM-01)")


class ShareCardIn(BaseModel):
    format: Literal["story", "square"]
    card: Annotated[
        MonthCardIn | YearCardIn | AsanaCardIn | CountCardIn, Field(discriminator="kind")
    ]


class ShareCardOut(BaseModel):
    id: str = Field(description="The card's token: the image URL is its capability")
    image_url: str
    width: int
    height: int
    file_name: str
    expires_at: datetime


class ShareSentOut(BaseModel):
    sent: bool


def _subject(card: MonthCardIn | YearCardIn | AsanaCardIn | CountCardIn) -> Subject:
    match card:
        case MonthCardIn():
            return MonthSubject(card.year, card.month)
        case YearCardIn():
            return YearSubject(card.year)
        case AsanaCardIn():
            return AsanaSubject(card.event_id)
        case CountCardIn():
            return CountSubject(card.count)


@router.post("", status_code=201, responses=error_responses(404, 422, 429))
async def create_share_card(
    body: ShareCardIn, principal: CurrentPrincipal, use_cases: UseCases
) -> ShareCardOut:
    """Renders one card of the caller's own data (two tones only: no rest, 🌸 or unlogged
    days; no name). 404 `not_found` (an event or count that isn't the caller's or can't be
    shared); 422 `invalid_period` (future), `nothing_to_share` (no practice); 429
    `rate_limited` (50 cards per 24 h); 503 `unavailable` when cards are off."""
    if not use_cases.available:
        raise ApiError(503, "unavailable")
    try:
        created = await use_cases.create.execute(
            principal, _subject(body.card), CardFormat(body.format)
        )
    except CardNotFound:
        raise ApiError(404, "not_found") from None
    except InvalidPeriod:
        raise ApiError(422, "invalid_period") from None
    except NothingToShare:
        raise ApiError(422, "nothing_to_share") from None
    except RateLimited:
        raise ApiError(429, "rate_limited") from None
    return ShareCardOut(
        id=created.token,
        image_url=use_cases.image_url(created.token),
        width=created.width,
        height=created.height,
        file_name=created.file_name,
        expires_at=created.expires_at,
    )


@router.post("/{card_id}/send", responses=error_responses(404, 409))
async def send_share_card(
    card_id: str, principal: CurrentPrincipal, use_cases: UseCases
) -> ShareSentOut:
    """The bot posts the card as a photo in the caller's own chat, once per card. 409
    `already_sent`, `bot_unreachable` (blocked or never started); 404 for someone else's,
    unknown or expired cards."""
    try:
        await use_cases.send.execute(principal, card_id)
    except CardNotFound:
        raise ApiError(404, "not_found") from None
    except AlreadySent:
        raise ApiError(409, "already_sent") from None
    except BotUnreachable:
        raise ApiError(409, "bot_unreachable") from None
    except SendFailed:
        raise ApiError(503, "unavailable") from None
    return ShareSentOut(sent=True)
