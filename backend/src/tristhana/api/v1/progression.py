"""The caller's progression (PR-08, ADR-0026): where the practice ends now, the milestone
items, the newest events, and changes that answer with their celebrations (GM-01 part 1).
Names come from the catalog (`GET /catalog`); the Mini App renders the lines with Fluent."""

import datetime as dt
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Path, Response
from pydantic import BaseModel, Field

from tristhana.api.deps import (
    CurrentPrincipal,
    dismiss_new_asana_hint,
    get_progression,
    mark_item,
    mark_new_asana,
    progression_track,
    set_position,
    undo_progression,
)
from tristhana.api.errors import ApiError, error_responses
from tristhana.api.v1.practice import Length
from tristhana.application.ports.progression import ProgressionView
from tristhana.application.progression import (
    ChangeResult,
    DismissNewAsanaHint,
    GetProgression,
    MarkItem,
    MarkNewAsana,
    NotLatest,
    ProgressionChanged,
    SetPractice,
    UndoProgression,
)
from tristhana.domain.days import DateInFuture, DateTooEarly
from tristhana.domain.progression import (
    CelebrationKind,
    EventKind,
    InvalidProgression,
    Position,
    ProgressionEvent,
    Track,
    last_asana,
    position_length,
)

router = APIRouter(
    prefix="/me/progression", tags=["progression"], responses=error_responses(401, 503)
)


class PositionOut(BaseModel):
    series: str | None = Field(description="Series slug; null with `last` null = standing only")
    last: str | None = Field(description="The last given stop point (natural key)")

    @classmethod
    def of(cls, p: Position) -> "PositionOut":
        return cls(series=p.series, last=p.key)

    @classmethod
    def maybe(cls, p: Position | None) -> "PositionOut | None":
        return cls.of(p) if p is not None else None


class SeriesLastOut(BaseModel):
    slug: str
    last: str | None = Field(description="Earlier series: their last stop; later ones: null")


class EventOut(BaseModel):
    id: int
    kind: EventKind
    occurred_on: dt.date
    before: PositionOut | None = Field(alias="from", serialization_alias="from")
    after: PositionOut | None = Field(alias="to", serialization_alias="to")
    item: str | None
    marked_by_self: bool

    @classmethod
    def of(cls, e: ProgressionEvent) -> "EventOut":
        return cls.model_validate(
            {
                "id": e.id,
                "kind": e.kind,
                "occurred_on": e.occurred_on,
                "from": PositionOut.maybe(e.before),
                "to": PositionOut.maybe(e.after),
                "item": e.item,
                "marked_by_self": e.marked_by_self,
            }
        )


class ProgressionOut(BaseModel):
    set: bool
    position: PositionOut | None = Field(description="null = not set yet")
    length: Length | None = Field(
        description="The position as a practice (the series below + this one); null = "
        "standing only, unset or stale"
    )
    by_series: list[SeriesLastOut]
    items: list[str] = Field(description="Milestone items given (catalog `milestone_items`)")
    next: PositionOut | None = Field(description="The next stop; null at the end or when stale")
    later: list[PositionOut] = Field(description='"Another new asana…": later stops')
    suggested: PositionOut | None = Field(description="Unset only: from the logged practices")
    suggested_length: Length | None = Field(description="`suggested` as a practice")
    events: list[EventOut] = Field(description="Newest first, at most 20")
    last_event_id: int | None = Field(description="Send back as `expected_event_id`")
    today: dt.date | None = Field(default=None, description="The caller's local date")

    @classmethod
    def of(
        cls,
        track: Track,
        view: ProgressionView,
        suggested: Position | None = None,
        today: dt.date | None = None,
    ) -> "ProgressionOut":
        p = view.progression
        length = position_length(track, p.position) if p else None
        suggested_length = position_length(track, suggested) if suggested else None
        return cls(
            set=p is not None,
            position=PositionOut.of(p.position) if p else None,
            length=Length.of(length) if length else None,
            by_series=[
                SeriesLastOut(slug=s.slug, last=last_asana(track, p, s.slug) if p else None)
                for s in track.catalog.series
            ],
            items=[i.key for i in track.items if p and i.key in p.items],
            next=PositionOut.maybe(track.next(p.position)) if p else None,
            later=[PositionOut.of(q) for q in track.after(p.position)] if p else [],
            suggested=PositionOut.maybe(suggested),
            suggested_length=Length.of(suggested_length) if suggested_length else None,
            events=[EventOut.of(e) for e in view.events],
            last_event_id=p.last_event_id if p else None,
            today=today,
        )


class CelebrationOut(BaseModel):
    kind: CelebrationKind
    series: str | None
    key: str | None = Field(description="The new stop, or the item")
    first: PositionOut | None = Field(
        description="A jump over several stops: the first new one (maybe in the series before)"
    )


class ChangeOut(BaseModel):
    progression: ProgressionOut
    event: EventOut | None = Field(description="null = nothing changed")
    celebrations: list[CelebrationOut] = Field(
        description="Empty for a give: it was held before (show the quiet line)"
    )


class EventBody(BaseModel):
    kind: Literal["set", "given", "item_given", "item_removed"]
    series: str | None = Field(default=None, description="set/given: null with last = standing")
    last: str | None = None
    item: str | None = Field(default=None, max_length=64)
    occurred_on: dt.date | None = Field(default=None, description="Default: local today")
    expected_event_id: int | None = Field(description="`last_event_id` as last seen")


class HintBody(BaseModel):
    series: str = Field(max_length=64)
    last: str = Field(max_length=64)


@router.get("")
async def get_mine(
    principal: CurrentPrincipal,
    use_case: Annotated[GetProgression, Depends(get_progression)],
    track: Annotated[Track, Depends(progression_track)],
) -> ProgressionOut:
    found = await use_case.execute(principal)
    return ProgressionOut.of(track, found.view, found.suggested, found.today)


@router.post("/events", status_code=201, responses=error_responses(409, 422))
async def post_event(
    body: EventBody,
    principal: CurrentPrincipal,
    set_: Annotated[SetPractice, Depends(set_position)],
    give: Annotated[MarkNewAsana, Depends(mark_new_asana)],
    item: Annotated[MarkItem, Depends(mark_item)],
    track: Annotated[Track, Depends(progression_track)],
) -> ChangeOut:
    """Set (first time or a correction, never celebrates), a new asana (forward only), or a
    milestone item. 409 `progression_changed`: refetch and show the fresh state."""
    target = Position(body.series, body.last)
    on, expected = body.occurred_on, body.expected_event_id
    try:
        match body.kind:
            case "set":
                result = await set_.execute(principal, target, on, expected)
            case "given":
                result = await give.execute(principal, target, on, expected)
            case "item_given" | "item_removed":
                if body.item is None:
                    raise InvalidProgression("item missing")
                given = body.kind == "item_given"
                result = await item.execute(principal, body.item, given, on, expected)
    except InvalidProgression:
        raise ApiError(422, "invalid_progression") from None
    except ProgressionChanged:
        raise ApiError(409, "progression_changed") from None
    except DateInFuture:
        raise ApiError(422, "date_in_future") from None
    except DateTooEarly:
        raise ApiError(422, "date_too_early") from None
    return _change_out(track, result)


def _change_out(track: Track, result: ChangeResult) -> ChangeOut:
    return ChangeOut(
        progression=ProgressionOut.of(track, result.view),
        event=EventOut.of(result.event) if result.event else None,
        celebrations=[
            CelebrationOut(
                kind=c.kind, series=c.series, key=c.key, first=PositionOut.maybe(c.first)
            )
            for c in result.celebrations
        ],
    )


@router.delete("/events/{event_id}", responses=error_responses(409))
async def delete_event(
    event_id: Annotated[int, Path(ge=1)],
    principal: CurrentPrincipal,
    use_case: Annotated[UndoProgression, Depends(undo_progression)],
    track: Annotated[Track, Depends(progression_track)],
) -> ProgressionOut:
    """Undo: only the latest event (409 `not_latest`)."""
    try:
        view = await use_case.execute(principal, event_id)
    except NotLatest:
        raise ApiError(409, "not_latest") from None
    return ProgressionOut.of(track, view)


@router.post("/hint-dismissals", status_code=204)
async def post_hint_dismissal(
    body: HintBody,
    principal: CurrentPrincipal,
    use_case: Annotated[DismissNewAsanaHint, Depends(dismiss_new_asana_hint)],
) -> Response:
    """ "Not new": the question isn't asked again for this stop until the position changes."""
    await use_case.execute(principal, Position(body.series, body.last))
    return Response(status_code=204)
