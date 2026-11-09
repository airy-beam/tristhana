"""Badges (GM-02, ADR-0041): a quiet collection to look back at, derived on every read from
data already stored. Nothing is written; a badge follows the data it comes from.

The definitions are data (`data/seed/badges.yaml`), each over one of a closed set of rule
kinds. A practice is a Practiced day, once per day (GM-01). Every rest kind is one set of
dates (logged rest/🌙/🌸/sick/travel, rest-period dates, PR-09 auto-rest), so a 🌸 day can
never be told from 😌: the plain status stores both as REST, and period kinds are never read.
"""

import re
from bisect import bisect_right
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, time, timedelta
from enum import StrEnum
from itertools import pairwise

from tristhana.domain.days import REST_LIKE, DayStatus
from tristhana.domain.practice import PracticeContext
from tristhana.domain.progression import EventKind, Position, ProgressionEvent, Track
from tristhana.domain.rest_days import DayOff, auto_days

MAX_BADGES = 40
MAX_COUNT = 100_000
KEY_RE = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")
_DAY = timedelta(days=1)
_POSITION_KINDS = frozenset({EventKind.START, EventKind.GIVEN, EventKind.CHANGED})


class RuleKind(StrEnum):
    PRACTICES = "practices"
    RUN = "run"
    CONTEXT = "context"
    EARLY_START = "early_start"
    MOON_REST = "moon_rest"
    RETURN = "return"
    SERIES_COMPLETE = "series_complete"
    SERIES_BEGINS = "series_begins"
    STOP = "stop"
    ITEM = "item"


class Group(StrEnum):
    PRACTICE = "practice"
    ASANAS = "asanas"


class InvalidBadges(ValueError):
    """The definitions don't fit the rule kinds or the catalog (raised by the seed loader)."""


@dataclass(frozen=True, slots=True)
class BadgeDef:
    key: str
    group: Group
    icon: str
    rule: RuleKind
    count: int | None = None
    days: int | None = None
    before: time | None = None  # wall clock, compared with each practice's own start time
    context: PracticeContext | None = None
    target: Position | None = None  # series_*: the series alone; stop: series + stop key
    item: str | None = None


# The parameters each rule kind takes; every other one must be None.
_PARAMS: dict[RuleKind, frozenset[str]] = {
    RuleKind.PRACTICES: frozenset({"count"}),
    RuleKind.RUN: frozenset({"count"}),
    RuleKind.CONTEXT: frozenset({"count", "context"}),
    RuleKind.EARLY_START: frozenset({"count", "before"}),
    RuleKind.MOON_REST: frozenset({"count"}),
    RuleKind.RETURN: frozenset({"days"}),
    RuleKind.SERIES_COMPLETE: frozenset({"target"}),
    RuleKind.SERIES_BEGINS: frozenset({"target"}),
    RuleKind.STOP: frozenset({"target"}),
    RuleKind.ITEM: frozenset({"item"}),
}
_ALL_PARAMS = ("count", "days", "before", "context", "target", "item")
# The practice details the facts carry per context (slot 1).
CONTEXTS = frozenset({PracticeContext.LED, PracticeContext.SELF})


@dataclass(frozen=True, slots=True)
class BadgeFacts:
    """What one account's badges are read from (one statement, plain columns only)."""

    logged: Mapping[date, DayStatus]  # the plain status: 🌸 is stored as REST
    covered: frozenset[date] = frozenset()  # dates inside a rest period (its kind never read)
    moon: frozenset[date] = frozenset()  # the effective calendar, first logged date .. today
    led: tuple[date, ...] = ()  # slot 1, oldest first
    self_: tuple[date, ...] = ()
    starts: tuple[tuple[date, time], ...] = ()  # slot 1 start times (own wall clock)
    kept_counts: frozenset[int] = frozenset()  # GM-01 ledger thresholds
    events: tuple[ProgressionEvent, ...] = ()  # position and item events, oldest first


@dataclass(frozen=True, slots=True)
class Earned:
    badge: BadgeDef
    on: date | None  # None: a GM-01 ledger count whose days were cleared since
    at_record_start: bool = False  # an asana held when the record began (a START)

    @property
    def key(self) -> str:
        return self.badge.key


def validate(defs: Sequence[BadgeDef], track: Track) -> None:
    """Unique well-formed keys, the right parameters per kind, confirmed series, a stop as a
    target, a milestone item, at most `MAX_BADGES`. Raises `InvalidBadges`."""
    if len(defs) > MAX_BADGES:
        raise InvalidBadges(f"at most {MAX_BADGES} badges")
    seen: set[str] = set()
    for d in defs:
        if KEY_RE.fullmatch(d.key) is None:
            raise InvalidBadges(f"{d.key!r}: keys are lowercase words joined by '-'")
        if d.key in seen:
            raise InvalidBadges(f"{d.key}: duplicate key")
        seen.add(d.key)
        _check(d, track)


def _check(d: BadgeDef, track: Track) -> None:
    wanted = _PARAMS[d.rule]
    given = frozenset(f for f in _ALL_PARAMS if getattr(d, f) is not None)
    if given != wanted:
        raise InvalidBadges(f"{d.key}: {d.rule} takes {sorted(wanted)}, got {sorted(given)}")
    for n in (d.count, d.days):
        if n is not None and not 1 <= n <= MAX_COUNT:
            raise InvalidBadges(f"{d.key}: numbers must be 1..{MAX_COUNT}")
    if d.context is not None and d.context not in CONTEXTS:
        raise InvalidBadges(f"{d.key}: context must be one of {sorted(CONTEXTS)}")
    if d.rule in (RuleKind.SERIES_COMPLETE, RuleKind.SERIES_BEGINS):
        assert d.target is not None  # noqa: S101 - checked above
        series = track.catalog.get(d.target.series) if d.target.series else None
        if d.target.key is not None or series is None or not series.stops:
            raise InvalidBadges(f"{d.key}: not a confirmed series")
    if d.rule is RuleKind.STOP and (d.target is None or track.rank(d.target) is None):
        raise InvalidBadges(f"{d.key}: not a stop of a confirmed series")
    if d.rule is RuleKind.ITEM and (d.item is None or not track.is_item(d.item)):
        raise InvalidBadges(f"{d.key}: not a milestone item")


def earned(
    defs: Sequence[BadgeDef],
    facts: BadgeFacts,
    track: Track,
    *,
    off: DayOff,
    joined: date,
    today: date,
) -> tuple[Earned, ...]:
    """The badges the facts give, in definition order, each with the date it came from."""
    practiced = sorted(d for d, s in facts.logged.items() if s is DayStatus.PRACTICED)
    rest: frozenset[date] | None = None

    def rest_dates() -> frozenset[date]:
        nonlocal rest
        if rest is None:
            rest = _rest_dates(facts, off, joined, today)
        return rest

    out: list[Earned] = []
    for d in defs:
        found = _one(d, facts, track, practiced, rest_dates, today)
        if found is not None:
            out.append(found)
    return tuple(out)


def _one(
    d: BadgeDef,
    facts: BadgeFacts,
    track: Track,
    practiced: list[date],
    rest_dates: Callable[[], frozenset[date]],
    today: date,
) -> Earned | None:
    n = d.count or 0
    match d.rule:
        case RuleKind.PRACTICES:
            if len(practiced) >= n:
                return Earned(d, practiced[n - 1])
            return Earned(d, None) if n in facts.kept_counts else None
        case RuleKind.RUN:
            return _dated(d, _run(n, practiced, facts.logged, rest_dates(), today))
        case RuleKind.CONTEXT:
            # Details count only on a Practiced day (a stale practice row never does).
            dates = facts.led if d.context is PracticeContext.LED else facts.self_
            return _dated(d, _nth(sorted(on for on in dates if _practised(facts, on)), n))
        case RuleKind.EARLY_START:
            before = d.before or time()
            early = (on for on, at in facts.starts if at < before and _practised(facts, on))
            return _dated(d, _nth(sorted(early), n))
        case RuleKind.MOON_REST:
            return _dated(d, _nth(sorted(facts.moon & rest_dates()), n))
        case RuleKind.RETURN:
            # At least `days` dates with no practice before this one: b - a - 1 >= days.
            gap = d.days or 0
            back = next((b for a, b in pairwise(practiced) if (b - a).days > gap), None)
            return _dated(d, back)
        case RuleKind.SERIES_COMPLETE | RuleKind.SERIES_BEGINS | RuleKind.STOP:
            return _reached(d, track, facts.events, practiced)
        case RuleKind.ITEM:
            return _item(d, facts.events, practiced)


def _practised(facts: BadgeFacts, on: date) -> bool:
    return facts.logged.get(on) is DayStatus.PRACTICED


def _dated(d: BadgeDef, on: date | None) -> Earned | None:
    return Earned(d, on) if on is not None else None


def _nth(dates: Sequence[date], n: int) -> date | None:
    return dates[n - 1] if len(dates) >= n else None


def _rest_dates(facts: BadgeFacts, off: DayOff, joined: date, today: date) -> frozenset[date]:
    """Every rest kind as one set: logged rest-like, unlogged period dates, auto-rest."""
    if not facts.logged:
        return frozenset()
    logged = facts.logged
    start = min(logged)
    found = {d for d, s in logged.items() if s in REST_LIKE}
    found |= {d for d in facts.covered if d not in logged and start <= d <= today}
    found |= auto_days(
        start, today, today, joined, logged.keys(), off, facts.moon, facts.covered
    ).keys()
    return frozenset(found)


def _run(
    n: int,
    practiced: Sequence[date],
    logged: Mapping[date, DayStatus],
    rest: frozenset[date],
    today: date,
) -> date | None:
    """The date the first run of `n` practices in a row reaches `n`. Rest dates are
    transparent; "No practice", or an unlogged non-rest date before today, ends a run (no
    bridge, unlike ST-01's runs; an unlogged today never ends one)."""
    if len(practiced) < n:
        return None
    count, day = 0, practiced[0]
    while day <= today:
        status = logged.get(day)
        if status is DayStatus.PRACTICED:
            count += 1
            if count == n:
                return day
        elif status is DayStatus.SKIPPED or (day not in rest and day < today):
            count = 0
        day += _DAY
    return None


def _quick(e: ProgressionEvent, f: ProgressionEvent, practiced: Sequence[date]) -> bool:
    """`f` takes `e` back as a quick correction (owner, 2026-11-09): the same local day, or
    before any practice was logged after `e` (no Practiced day strictly between them). A step
    back after a practised day is real, and keeps what `e` gave."""
    if f.occurred_on <= e.occurred_on:
        return True
    return bisect_right(practiced, e.occurred_on) == bisect_right(practiced, f.occurred_on - _DAY)


def _reached(
    d: BadgeDef, track: Track, events: Sequence[ProgressionEvent], practiced: Sequence[date]
) -> Earned | None:
    """The first position event at or past the badge's stop (stale keys ignored), unless a
    quick ✏️ Change below the stop took it back (a mis-tap, ADR-0041)."""
    need = _need_rank(d, track)
    if need is None:
        return None
    moves = [e for e in events if e.kind in _POSITION_KINDS and e.after is not None]
    for i, e in enumerate(moves):
        assert e.after is not None  # noqa: S101 - filtered above
        rank = track.rank(e.after)
        if rank is None or rank < need:
            continue
        nxt = moves[i + 1] if i + 1 < len(moves) else None
        if nxt is not None and nxt.kind is EventKind.CHANGED and nxt.after is not None:
            below = track.rank(nxt.after)
            if below is not None and below < need and _quick(e, nxt, practiced):
                continue
        return Earned(d, e.occurred_on, at_record_start=e.kind is EventKind.START)
    return None


def _item(
    d: BadgeDef, events: Sequence[ProgressionEvent], practiced: Sequence[date]
) -> Earned | None:
    """The first time the item was given, unless taken back quickly (as `_reached`)."""
    mine = [e for e in events if e.item == d.item]
    for i, e in enumerate(mine):
        if e.kind is not EventKind.ITEM_GIVEN:
            continue
        nxt = mine[i + 1] if i + 1 < len(mine) else None
        if nxt is not None and nxt.kind is EventKind.ITEM_REMOVED and _quick(e, nxt, practiced):
            continue
        return Earned(d, e.occurred_on)
    return None


def _need_rank(d: BadgeDef, track: Track) -> int | None:
    target = d.target
    if target is None or target.series is None:
        return None
    if d.rule is RuleKind.STOP:
        return track.rank(target)
    series = track.catalog.get(target.series)
    if series is None or not series.stops:
        return None
    stop = series.stops[-1] if d.rule is RuleKind.SERIES_COMPLETE else series.stops[0]
    return track.rank(Position(series.slug, stop.key))
