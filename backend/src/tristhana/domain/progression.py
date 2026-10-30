"""Progression (PR-08, ADR-0026): where the practice ends now, plus the history of changes.

One current position per account: a series and its last given **stop point**; every earlier
series counts as full (in the SYC line Pasasana comes only after full Primary, and Primary
with incomplete binds still counts as full). The optional milestone items of the blocks
(drop-backs, standing up, tic-tacs) are independent flags, read from the catalog.

Celebrations (GM-01 part 1) are derived from the history when a change is written: a step
celebrates only when it goes past everything held before, so an asana given again after a
change (injury, pregnancy, a teacher's call) gets a quiet line, never a 🎉.
"""

from collections import Counter
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from tristhana.domain.practice import (
    STATIC_PRESETS,
    InvalidLength,
    Practice,
    PracticeCatalog,
    PracticeContext,
    PracticeLength,
    Series,
    StopPoint,
    check_length,
)

MAX_ITEMS = 8
HISTORY_LIMIT = 20
# The current series alone ("Intermediate → X", Primary on Fridays) is offered once the
# position reaches this stop (SYC splits around Pincha Mayurasana / Karandavasana).
SPLIT_FROM: dict[str, str] = {"intermediate": "pincha-mayurasana"}
# Advanced A-D share one traditional name (Sthira Bhaga), so it is shown up to Intermediate.
TRADITIONAL_UP_TO = 2
# Contexts that ask "New asana?" after a length past the last asana: not self-practice
# (people try the next asana at home before it is given), not Led (the teacher counts).
ASK_CONTEXTS = frozenset({PracticeContext.MYSORE, PracticeContext.PRIVATE})


class EventKind(StrEnum):
    START = "start"  # first set: never celebrates
    GIVEN = "given"  # 🎉 a new asana (forward only)
    CHANGED = "changed"  # a correction, either way: never celebrates
    ITEM_GIVEN = "item_given"
    ITEM_REMOVED = "item_removed"


class CelebrationKind(StrEnum):
    NEW_ASANA = "new_asana"
    SERIES_COMPLETE = "series_complete"
    SERIES_BEGINS = "series_begins"
    ITEM = "item"
    PRACTICE_COUNT = "practice_count"  # GM-01 part 2 (domain/milestones.py)


class InvalidProgression(ValueError):
    """Not a stop of a confirmed series, not a milestone item, or not forward."""


class NotForward(InvalidProgression):
    """A "new asana" must go past the current position (a stale keyboard, or a double tap)."""


class ProgressionNotSet(InvalidProgression):
    """Giving or marking an item needs a position first."""


@dataclass(frozen=True, slots=True)
class Position:
    """Both None = sun salutations and standing only."""

    series: str | None = None
    key: str | None = None


STANDING_ONLY = Position()


@dataclass(frozen=True, slots=True)
class Progression:
    position: Position
    items: frozenset[str] = frozenset()
    last_event_id: int | None = None
    hint: Position | None = None  # the last "Not new" target …
    hint_event_id: int | None = None  # … and the event it was answered at

    @property
    def dismissed(self) -> Position | None:
        """The "Not new" answer counts only until the position changes."""
        return self.hint if self.hint_event_id == self.last_event_id else None


@dataclass(frozen=True, slots=True)
class ProgressionEvent:
    id: int
    kind: EventKind
    occurred_on: date
    before: Position | None = None
    after: Position | None = None
    item: str | None = None
    marked_by_self: bool = True


@dataclass(frozen=True, slots=True)
class Earlier:
    """What the history held before: every position reached (set, given or changed to) and
    every item given. A correction counts too: after a mis-tapped start fixed by ✏️ Change,
    stepping back to an asana held before is not a first time."""

    targets: frozenset[Position] = frozenset()
    items: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class Change:
    """One event to append and the state it leads to."""

    kind: EventKind
    occurred_on: date
    state: Progression  # position and items after the change
    before: Position | None = None
    after: Position | None = None
    item: str | None = None


@dataclass(frozen=True, slots=True)
class Celebration:
    kind: CelebrationKind
    series: str | None = None
    key: str | None = None  # the new stop, or the item
    first: Position | None = None  # a jump over several stops: the first new one
    count: int | None = None  # PRACTICE_COUNT: the threshold reached


class Track:
    """Every stop of the confirmed series in practice order, after "standing only"."""

    def __init__(self, catalog: PracticeCatalog) -> None:
        self.catalog = catalog
        order = [STANDING_ONLY]
        for series in catalog.series:
            order += (Position(series.slug, stop.key) for stop in series.stops)
        self._order = tuple(order)
        self._rank = {p: i - 1 for i, p in enumerate(order)}  # standing only = -1
        self.items: tuple[StopPoint, ...] = catalog.milestones
        self._items = {i.key for i in self.items}

    def rank(self, p: Position) -> int | None:
        """None = a stale key (the catalog changed)."""
        return self._rank.get(p)

    def next(self, p: Position) -> Position | None:
        rank = self.rank(p)
        if rank is None or rank + 2 >= len(self._order):
            return None
        return self._order[rank + 2]

    def after(self, p: Position) -> tuple[Position, ...]:
        """Later stops of the current and the next series (for "Another new asana…");
        from standing only or a series' end, the next series alone."""
        rank = self.rank(p)
        if rank is None:
            return ()
        later = self._order[rank + 2 :]
        series = list(dict.fromkeys(q.series for q in later))[:2]
        if later and later[0].series != p.series:
            series = series[:1]
        return tuple(q for q in later if q.series in series)

    def between(self, first: int, last: int) -> tuple[Position, ...]:
        """The stops ranked `first` … `last`."""
        return self._order[first + 1 : last + 2]

    def series(self, p: Position) -> Series | None:
        return self.catalog.get(p.series) if p.series else None

    def stop(self, p: Position) -> StopPoint | None:
        return self.catalog.stop(p.series, p.key) if p.series and p.key else None

    def is_item(self, key: str) -> bool:
        return key in self._items


def check_position(track: Track, target: Position) -> Position:
    if track.rank(target) is None:
        raise InvalidProgression("not a stop of a confirmed series")
    return target


def check_given(track: Track, current: Position, target: Position) -> Position:
    """Raises `InvalidProgression`, or `NotForward` unless `target` is past `current`."""
    rank = track.rank(check_position(track, target))
    now = track.rank(current)
    if now is None or rank is None or rank <= now:
        raise NotForward("not past the current position")
    return target


def last_asana(track: Track, progression: Progression, slug: str) -> str | None:
    """The per-series view: earlier series end at their last stop, later ones aren't begun."""
    position = progression.position
    series, current = track.catalog.get(slug), track.series(position)
    if series is None or current is None or not series.stops:
        return None
    if series.number < current.number:
        return series.stops[-1].key
    return position.key if series.number == current.number else None


def from_length(catalog: PracticeCatalog, length: PracticeLength) -> Position:
    """Where a logged length ends (the last series; a full one ends at its last stop)."""
    if not length.series:
        return STANDING_ONLY
    slug = length.series[-1]
    if length.end is not None:
        return Position(slug, length.end)
    series = catalog.get(slug)
    return Position(slug, series.stops[-1].key) if series and series.stops else Position(slug)


def set_change(
    track: Track, progression: Progression | None, target: Position, on: date
) -> Change | None:
    """START the first time, then CHANGED; None when nothing changes."""
    check_position(track, target)
    if progression is None:
        return Change(EventKind.START, on, Progression(target), after=target)
    if progression.position == target:
        return None
    state = Progression(target, progression.items)
    return Change(EventKind.CHANGED, on, state, progression.position, target)


def given_change(
    track: Track, progression: Progression | None, target: Position, on: date
) -> Change:
    if progression is None:
        raise ProgressionNotSet("set the practice first")
    check_given(track, progression.position, target)
    state = Progression(target, progression.items)
    return Change(EventKind.GIVEN, on, state, progression.position, target)


def item_change(
    track: Track, progression: Progression | None, item: str, given: bool, on: date
) -> Change | None:
    if not track.is_item(item):
        raise InvalidProgression("not a milestone item")
    if progression is None:
        raise ProgressionNotSet("set the practice first")
    if (item in progression.items) == given:
        return None
    items = progression.items | {item} if given else progression.items - {item}
    kind = EventKind.ITEM_GIVEN if given else EventKind.ITEM_REMOVED
    return Change(kind, on, Progression(progression.position, items), item=item)


def celebrations(track: Track, earlier: Earlier, change: Change) -> tuple[Celebration, ...]:
    """First times only; START and CHANGED never celebrate. An empty result for a GIVEN
    means it was held before (the quiet line)."""
    if change.kind is EventKind.ITEM_GIVEN:
        new = change.item is not None and change.item not in earlier.items
        return (Celebration(CelebrationKind.ITEM, key=change.item),) if new else ()
    if change.kind is not EventKind.GIVEN or change.after is None or change.before is None:
        return ()
    ranks = [r for r in (track.rank(p) for p in earlier.targets) if r is not None]
    peak = max(ranks, default=-1)
    start, end = track.rank(change.before), track.rank(change.after)
    if start is None or end is None or end <= peak:
        return ()
    stops = track.between(max(start, peak) + 1, end)
    target = change.after
    out = [
        Celebration(
            CelebrationKind.NEW_ASANA,
            target.series,
            target.key,
            stops[0] if len(stops) > 1 else None,
        )
    ]
    for p in stops:
        series = track.series(p)
        if series is None:
            continue
        if series.stops[0].key == p.key:
            out.append(Celebration(CelebrationKind.SERIES_BEGINS, series.slug))
        if series.stops[-1].key == p.key:
            out.append(Celebration(CelebrationKind.SERIES_COMPLETE, series.slug))
    return tuple(out)


def position_length(track: Track, position: Position) -> PracticeLength | None:
    """How the position reads as a practice: the series just below in full + the current
    series to the last stop (Primary alone for Primary); None = standing only or stale."""
    series = track.series(position)
    if series is None or track.rank(position) is None:
        return None
    end = None if series.stops[-1].key == position.key else position.key
    below = track.catalog.by_number(series.number - 1)
    return PracticeLength((below.slug, series.slug) if below else (series.slug,), end)


def my_presets(
    track: Track, progression: Progression | None, recent: list[Practice]
) -> tuple[PracticeLength, ...]:
    """ "🧘 My practice": `position_length` (never every lower series), plus the current
    series alone from Intermediate on (Intermediate: once at Pincha Mayurasana, or after a
    recent Intermediate-alone practice). Lengths equal to a static preset are dropped."""
    if progression is None:
        return ()
    position = progression.position
    main = position_length(track, position)
    series = track.series(position)
    if main is None or series is None:
        return ()  # standing only (= Short), or stale
    out = [main]
    if len(main.series) > 1 and _split(track, series, position, recent):
        out.append(PracticeLength((series.slug,), main.end))
    static = {length for _, length in STATIC_PRESETS}
    return tuple(length for length in out if length not in static)


def _split(track: Track, series: Series, position: Position, recent: list[Practice]) -> bool:
    gate = SPLIT_FROM.get(series.slug)
    if gate is None:
        return True  # Advanced A and later: always
    gate_rank, rank = track.rank(Position(series.slug, gate)), track.rank(position)
    if gate_rank is not None and rank is not None and rank >= gate_rank:
        return True
    return any(
        p.length is not None and p.length.series == (series.slug,) and not p.length.first_part
        for p in recent
    )


def past_last(
    track: Track,
    progression: Progression | None,
    length: PracticeLength | None,
    context: PracticeContext | None,
) -> Position | None:
    """The stop to ask "New asana? 🎉" about: a Mysore or 1:1 practice that ends past the
    stored position, unless that target was answered "Not new" at this position."""
    if progression is None or length is None or context not in ASK_CONTEXTS:
        return None
    target = from_length(track.catalog, length)
    rank, now = track.rank(target), track.rank(progression.position)
    if rank is None or now is None or rank <= now or target == progression.dismissed:
        return None
    return target


def suggest_start(catalog: PracticeCatalog, recent: list[Practice]) -> Position | None:
    """The most-used non-Led length of the recent practices (ties: the newest), as a
    starting position; None when there is none."""
    counts: Counter[PracticeLength] = Counter()
    first_seen: dict[PracticeLength, int] = {}
    for i, practice in enumerate(recent):
        if practice.length is None or practice.context is PracticeContext.LED:
            continue
        try:
            length = check_length(catalog, practice.length)
        except InvalidLength:
            continue
        counts[length] += 1
        first_seen.setdefault(length, i)
    if not counts:
        return None
    best = min(counts, key=lambda length: (-counts[length], first_seen[length]))
    return from_length(catalog, best)


def shows_traditional(series: Series) -> bool:
    return series.traditional is not None and series.number <= TRADITIONAL_UP_TO
