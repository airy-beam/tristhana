"""Announcements (NT-03, ADR-0038). Composing is here only (Q176); the tick delivers. A source
that isn't the caller's gets 404 `not_found` exactly like an unknown id; a shala member
without the role gets 403 `not_allowed`. Every answer, errors too, is `no-store`. Times are
UTC instants; the client shows dates in the device's zone."""

from collections.abc import Awaitable
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field, StringConstraints

from tristhana.api.deps import CurrentPrincipal, announcements
from tristhana.api.errors import ApiError, ErrorCode, error_responses
from tristhana.application.announcements import AnnouncementUseCases, Target
from tristhana.application.policies import NotAllowed, NotFound
from tristhana.application.ports.announcements import FeedItem, FeedSource, SentItem
from tristhana.domain.announcements import (
    AnnouncementLimit,
    InvalidAnnouncement,
    Source,
    SourceKind,
)

router = APIRouter(tags=["announcements"], responses=error_responses(401, 503))

UseCases = Annotated[AnnouncementUseCases, Depends(announcements)]
_NO_STORE = {"Cache-Control": "no-store"}
type Kind = Literal["teacher", "shala"]
_KIND: dict[SourceKind, Kind] = {SourceKind.TEACHER: "teacher", SourceKind.SHALA: "shala"}
_SOURCE_KIND: dict[Kind, SourceKind] = {v: k for k, v in _KIND.items()}


class SourceOut(BaseModel):
    kind: Kind = Field(description="teacher: `id` is the teacher's account; shala: the shala")
    id: UUID
    name: str | None = Field(description="The shala's name, or the teacher's display name")


class FeedSourceOut(SourceOut):
    muted: bool = Field(description="Pushes off for this source (the feed still shows them)")


class AnnouncementOut(BaseModel):
    id: UUID
    source: SourceOut
    author_name: str | None = Field(description="null once no longer the teacher or on staff")
    text: str
    created_at: datetime
    pinned_until: datetime | None = Field(description="Set only while the pin is live")
    can_manage: bool = Field(description="May pin or delete it (the author, a shala manager)")


class FeedOut(BaseModel):
    items: list[AnnouncementOut] = Field(description="Live pins first, then newest first")
    sources: list[FeedSourceOut] = Field(description="The caller's teachers and shalas")
    more: bool


class SentOut(BaseModel):
    id: UUID
    source: SourceOut
    text: str
    created_at: datetime
    pinned_until: datetime | None
    audience: int = Field(description="People it went to at send time, muted ones included")


class AnnouncementIn(BaseModel):
    to: Literal["students", "shala"]
    shala_id: UUID | None = Field(default=None, description="Required when `to` is shala")
    text: Annotated[str, StringConstraints(max_length=4000)] = Field(
        description="Plain text; at most 1000 characters once trimmed"
    )
    pin_days: Literal[0, 7, 30] = 0


class PinIn(BaseModel):
    pin_days: Literal[0, 7, 30] = Field(description="0 unpins")


class MuteIn(BaseModel):
    muted: bool


def _fail(status: int, code: ErrorCode) -> ApiError:
    return ApiError(status, code, _NO_STORE)


async def _run[T](work: Awaitable[T]) -> T:
    try:
        return await work
    except NotFound:
        raise _fail(404, "not_found") from None
    except NotAllowed:
        raise _fail(403, "not_allowed") from None
    except AnnouncementLimit:
        raise _fail(409, "announcement_limit") from None
    except InvalidAnnouncement:
        raise _fail(422, "invalid_announcement") from None


def _source(source: Source, name: str | None) -> SourceOut:
    return SourceOut(kind=_KIND[source.kind], id=source.id, name=name)


def _item(i: FeedItem) -> AnnouncementOut:
    return AnnouncementOut(
        id=i.id,
        source=_source(i.source, i.source_name),
        author_name=i.author_name,
        text=i.text,
        created_at=i.created_at,
        pinned_until=i.pinned_until,
        can_manage=i.can_manage,
    )


def _feed_source(s: FeedSource) -> FeedSourceOut:
    return FeedSourceOut(kind=_KIND[s.source.kind], id=s.source.id, name=s.name, muted=s.muted)


def _sent(s: SentItem, teacher_name: str | None) -> SentOut:
    name = s.shala_name if s.source.kind is SourceKind.SHALA else teacher_name
    return SentOut(
        id=s.id,
        source=_source(s.source, name),
        text=s.text,
        created_at=s.created_at,
        pinned_until=s.pinned_until,
        audience=s.audience,
    )


@router.get("/me/announcements", responses=error_responses(404, 422))
async def get_announcements(
    principal: CurrentPrincipal,
    use_cases: UseCases,
    response: Response,
    kind: Kind | None = None,
    id: UUID | None = None,
    offset: Annotated[int, Query(ge=0, le=1000)] = 0,
    limit: Annotated[int, Query(ge=1, le=20)] = 20,
) -> FeedOut:
    """The caller's teachers and shalas: the last 30 days plus live pins (Q171). `kind` and
    `id` together narrow it to one source."""
    if (kind is None) != (id is None):
        raise _fail(422, "invalid_announcement")
    source = Source(_SOURCE_KIND[kind], id) if kind is not None and id is not None else None
    feed = await _run(use_cases.feed.execute(principal, source, offset, limit))
    response.headers.update(_NO_STORE)
    return FeedOut(
        items=[_item(i) for i in feed.items],
        sources=[_feed_source(s) for s in feed.sources],
        more=feed.more,
    )


@router.get("/me/announcements/sent")
async def get_sent_announcements(
    principal: CurrentPrincipal, use_cases: UseCases, response: Response
) -> list[SentOut]:
    """My own, the last 30 days, newest first."""
    found = await _run(use_cases.sent.execute(principal))
    response.headers.update(_NO_STORE)
    return [_sent(s, principal.account.display_name) for s in found]


@router.post("/me/announcements", status_code=201, responses=error_responses(403, 404, 409, 422))
async def post_announcement(
    body: AnnouncementIn, principal: CurrentPrincipal, use_cases: UseCases, response: Response
) -> SentOut:
    """Saved now, delivered by the next tick (within about 10 minutes)."""
    if (body.to == "shala") != (body.shala_id is not None):
        raise _fail(422, "invalid_announcement")
    target = Target(body.shala_id)
    sent = await _run(use_cases.send.execute(principal, target, body.text, body.pin_days))
    response.headers.update(_NO_STORE)
    return _sent(sent, principal.account.display_name)


@router.patch("/me/announcements/{id}", responses=error_responses(403, 404, 422))
async def patch_announcement(
    id: UUID, body: PinIn, principal: CurrentPrincipal, use_cases: UseCases, response: Response
) -> SentOut:
    """Pin (one per source: the earlier pin goes) or unpin."""
    item = await _run(use_cases.pin.execute(principal, id, body.pin_days))
    response.headers.update(_NO_STORE)
    return _sent(
        item, principal.account.display_name if item.source.id == principal.account.id else None
    )


@router.delete("/me/announcements/{id}", status_code=204, responses=error_responses(403))
async def delete_announcement(
    id: UUID, principal: CurrentPrincipal, use_cases: UseCases
) -> Response:
    """Idempotent. Messages already delivered stay in people's chats."""
    await _run(use_cases.delete.execute(principal, id))
    return Response(status_code=204, headers=_NO_STORE)


@router.put("/me/announcement-mutes/{kind}/{id}", status_code=204, responses=error_responses(404))
async def put_announcement_mute(
    kind: Kind, id: UUID, body: MuteIn, principal: CurrentPrincipal, use_cases: UseCases
) -> Response:
    """Push only; the sender is never told (Q167). Idempotent."""
    await _run(use_cases.mute.execute(principal, Source(_SOURCE_KIND[kind], id), body.muted))
    return Response(status_code=204, headers=_NO_STORE)
