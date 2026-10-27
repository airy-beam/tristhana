"""Progression use cases (PR-08, GM-01 part 1, ADR-0026). Shared by the bot and the API; every
call acts on the caller's own record (`Principal`). A write is one read, the domain rules and
one compare-and-set statement; celebrations come from the read already made."""

from dataclasses import dataclass, replace
from datetime import date
from typing import Literal

from tristhana.application.policies import Principal
from tristhana.application.ports.practice import PracticeRepository
from tristhana.application.ports.progression import ProgressionRepository, ProgressionView
from tristhana.application.ports.storage import Clock
from tristhana.domain.days import check_loggable, local_today, provisional_zone
from tristhana.domain.practice import RECENT_LIMIT
from tristhana.domain.progression import (
    HISTORY_LIMIT,
    Celebration,
    Change,
    Earlier,
    EventKind,
    Position,
    ProgressionEvent,
    Track,
    celebrations,
    given_change,
    item_change,
    set_change,
    suggest_start,
)

# "read": compare against the state this call reads (the bot); an id or None: against what
# the caller last saw (the Mini App).
type Expected = int | Literal["read"] | None


class ProgressionChanged(Exception):
    """Someone (another tap, another device) changed it first."""


class NotLatest(Exception):
    """Only the latest event can be undone."""


@dataclass(frozen=True, slots=True)
class ProgressionOverview:
    view: ProgressionView
    suggested: Position | None = None  # unset only: from the logged practices
    today: date | None = None


@dataclass(frozen=True, slots=True)
class ChangeResult:
    view: ProgressionView  # after the change
    event: ProgressionEvent | None  # None = nothing changed
    celebrations: tuple[Celebration, ...] = ()


def _today(principal: Principal, clock: Clock) -> date:
    account = principal.account
    return local_today(clock.now(), account.timezone or provisional_zone(account.locale))


class GetProgression:
    def __init__(
        self,
        progression: ProgressionRepository,
        practices: PracticeRepository,
        track: Track,
        clock: Clock,
    ) -> None:
        self._progression = progression
        self._practices = practices
        self._track = track
        self._clock = clock

    async def execute(self, principal: Principal) -> ProgressionOverview:
        """One statement, plus one for the suggestion while unset."""
        view = await self._progression.get(principal.account.id)
        today = _today(principal, self._clock)
        if view.progression is not None:
            return ProgressionOverview(view, today=today)
        return ProgressionOverview(view, await self.suggest(principal), today)

    async def suggest(self, principal: Principal) -> Position | None:
        """A starting position from the logged practices (one statement)."""
        today = _today(principal, self._clock)
        recent = await self._practices.recent(principal.account.id, today, RECENT_LIMIT)
        return suggest_start(self._track.catalog, recent)


class _Write:
    def __init__(self, progression: ProgressionRepository, track: Track, clock: Clock) -> None:
        self._progression = progression
        self._track = track
        self._clock = clock

    def _on(self, principal: Principal, on: date | None) -> date:
        """Raises `DateInFuture` / `DateTooEarly` (dates follow the logging rules)."""
        if on is None:
            return _today(principal, self._clock)
        check_loggable(on, self._clock.now(), principal.account.timezone)
        return on

    async def _apply(
        self, principal: Principal, view: ProgressionView, change: Change | None, expected: Expected
    ) -> ChangeResult:
        current = view.progression.last_event_id if view.progression else None
        if expected != "read" and expected != current:
            raise ProgressionChanged("stale view")
        if change is None:
            return ChangeResult(view, None)
        account = principal.account.id
        event = await self._progression.apply(account, change, current, marked_by=account)
        if event is None:
            raise ProgressionChanged("lost the compare-and-set")
        found = celebrations(self._track, view.earlier, change)
        return ChangeResult(_after(view, change, event), event, found)


def _after(view: ProgressionView, change: Change, event: ProgressionEvent) -> ProgressionView:
    """The view after `change`, built in memory (no second read)."""
    earlier = view.earlier
    if change.kind is EventKind.ITEM_GIVEN and change.item is not None:
        earlier = Earlier(earlier.targets, earlier.items | {change.item})
    elif change.after is not None:
        earlier = Earlier(earlier.targets | {change.after}, earlier.items)
    state = replace(change.state, last_event_id=event.id)
    if view.progression is not None:
        state = replace(
            state, hint=view.progression.hint, hint_event_id=view.progression.hint_event_id
        )
    return ProgressionView(state, earlier, ((event, *view.events))[:HISTORY_LIMIT])


class SetPractice(_Write):
    async def execute(
        self,
        principal: Principal,
        target: Position,
        on: date | None = None,
        expected: Expected = "read",
    ) -> ChangeResult:
        """First time START, then CHANGED (never celebrates); the same position is a no-op.
        Raises `InvalidProgression`, `ProgressionChanged`, `DateInFuture`, `DateTooEarly`."""
        day = self._on(principal, on)
        view = await self._progression.get(principal.account.id)
        change = set_change(self._track, view.progression, target, day)
        return await self._apply(principal, view, change, expected)


class MarkNewAsana(_Write):
    async def execute(
        self,
        principal: Principal,
        target: Position,
        on: date | None = None,
        expected: Expected = "read",
    ) -> ChangeResult:
        """Raises `NotForward`, `ProgressionNotSet`, `InvalidProgression`,
        `ProgressionChanged`, `DateInFuture`, `DateTooEarly`."""
        day = self._on(principal, on)
        view = await self._progression.get(principal.account.id)
        change = given_change(self._track, view.progression, target, day)
        return await self._apply(principal, view, change, expected)


class MarkItem(_Write):
    async def execute(
        self,
        principal: Principal,
        item: str,
        given: bool,
        on: date | None = None,
        expected: Expected = "read",
    ) -> ChangeResult:
        """Already so = a no-op. Raises `InvalidProgression`, `ProgressionNotSet`,
        `ProgressionChanged`, `DateInFuture`, `DateTooEarly`."""
        day = self._on(principal, on)
        view = await self._progression.get(principal.account.id)
        change = item_change(self._track, view.progression, item, given, day)
        return await self._apply(principal, view, change, expected)


class UndoProgression:
    def __init__(self, progression: ProgressionRepository) -> None:
        self._progression = progression

    async def execute(self, principal: Principal, event_id: int) -> ProgressionView:
        """Raises `NotLatest`. Two statements: the undo, then the view."""
        if not await self._progression.undo(principal.account.id, event_id):
            raise NotLatest(str(event_id))
        return await self._progression.get(principal.account.id)


class DismissNewAsanaHint:
    def __init__(self, progression: ProgressionRepository) -> None:
        self._progression = progression

    async def execute(self, principal: Principal, target: Position) -> None:
        """ "Not new" for the current position: one UPDATE, idempotent; it lapses once the
        position changes."""
        await self._progression.dismiss_hint(principal.account.id, target)
