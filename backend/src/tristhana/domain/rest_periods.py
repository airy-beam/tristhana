"""Rest periods (WH-01 part 2, ADR-0023): a 🌸 / sick / travel statement over a range of
days, stored as a range and derived at read time. Pure: no I/O, no clock.

Read-time precedence for an unlogged date ≤ today: logged > period > moon > day off. Days
are calendar days: a moon day or the day off inside a period is one of its N days.
"""

from collections.abc import Iterable, Mapping, Set
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from tristhana.domain.days import (
    MIN_LOG_DATE,
    DateInFuture,
    DayStatus,
    latest_loggable,
    local_today,
)

PAUSABLE = frozenset({DayStatus.LADIES, DayStatus.SICK, DayStatus.TRAVEL})
# Per kind (owner, 2026-10-26): (first screen, "Other…"). The only allowed day counts.
PAUSE_DAYS: dict[DayStatus, tuple[tuple[int, ...], tuple[int, ...]]] = {
    DayStatus.LADIES: ((2, 3, 5), (4, 6, 7)),
    DayStatus.SICK: ((3, 4, 5), (2, 6, 7, 10, 14)),
    DayStatus.TRAVEL: ((3, 4, 5), (2, 6, 7, 10, 14)),
}
MAX_PERIOD_DAYS = 14  # the DB cap (the kind is sealed, so the per-kind max is ours only)
# The earliest calendar date anywhere on Earth (UTC-12): with no known zone, "yesterday"
# is never refused for someone who is still on an earlier date.
_EARLIEST_ZONE = "Etc/GMT+12"
_DAY = timedelta(days=1)


class InvalidRestPeriod(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class RestPeriod:
    start: date
    end: date  # inclusive, end > start
    kind: DayStatus  # LADIES, SICK or TRAVEL

    def covers(self, day: date) -> bool:
        return self.start <= day <= self.end


@dataclass(frozen=True, slots=True)
class PauseOffer:
    start: date
    kind: DayStatus
    reminders_on: bool


@dataclass(frozen=True, slots=True)
class Placement:
    """What a new period does to the existing ones (start dates)."""

    removed: frozenset[date] = frozenset()
    ended: dict[date, date] = field(default_factory=dict[date, date])  # start -> new end


class _Unchanged:
    def __repr__(self) -> str:
        return "UNCHANGED"


UNCHANGED = _Unchanged()


def allowed_days(kind: DayStatus) -> frozenset[int]:
    first, other = PAUSE_DAYS.get(kind, ((), ()))
    return frozenset(first) | frozenset(other)


def max_days(kind: DayStatus) -> int:
    return max(allowed_days(kind), default=0)


def _today_bounds(now: datetime, zone: str | None) -> tuple[date, date]:
    """(earliest, latest) "today": one date for a known zone; with a provisional zone,
    any date that is today somewhere on Earth (as for logging)."""
    if zone is not None:
        today = local_today(now, zone)
        return today, today
    return now.astimezone(ZoneInfo(_EARLIEST_ZONE)).date(), latest_loggable(now, None)


def offer_today(day: date, now: datetime, zone: str | None) -> date:
    """ "Today" for `pause_offer`: the local date, or with a provisional zone the date
    closest to `day` that is today somewhere on Earth (as for logging)."""
    earliest, latest = _today_bounds(now, zone)
    return min(max(day, earliest), latest)


def check_period(
    start: date, days: int, kind: DayStatus, now: datetime, zone: str | None
) -> RestPeriod:
    """A new period of `days` days from `start` (today or yesterday), inclusive. Raises
    `InvalidRestPeriod` (kind, day count, a backfilled start) and `DateInFuture`."""
    if kind not in PAUSABLE:
        raise InvalidRestPeriod(f"kind {kind}")
    if days not in allowed_days(kind):
        raise InvalidRestPeriod(f"{days} days")
    earliest, latest = _today_bounds(now, zone)
    if start > latest:
        raise DateInFuture(start.isoformat())
    if start < earliest - _DAY or start < MIN_LOG_DATE:
        raise InvalidRestPeriod(f"start {start.isoformat()}")
    return RestPeriod(start, start + timedelta(days=days - 1), kind)


def check_restore(period: RestPeriod, now: datetime, zone: str | None) -> RestPeriod | None:
    """ "Keep the pause": the period as it was, re-checked (it came from callback data).
    None once it is over (`end` < today): nothing left to keep."""
    length = (period.end - period.start).days + 1
    if period.kind not in PAUSABLE or length < 2 or length > max_days(period.kind):
        raise InvalidRestPeriod(f"{length} days of {period.kind}")
    earliest, latest = _today_bounds(now, zone)
    if period.start > latest or period.start < MIN_LOG_DATE:
        raise InvalidRestPeriod(f"start {period.start.isoformat()}")
    if period.end < earliest:
        return None
    return period


def pause_offer(
    day: date,
    today: date,
    status: DayStatus,
    prev: DayStatus | None,
    covering: RestPeriod | None,
    before: RestPeriod | None,
    reminders_on: bool,
) -> PauseOffer | None:
    """Whether "for how many days?" follows a tap on 🌸/🤒/✈️ for `day` (spec §2).

    `prev` = the logged status of the day before, `covering` = the period covering `day`,
    `before` = the period covering the day before (both as before this tap)."""
    if status not in PAUSABLE or day not in (today, today - _DAY):
        return None
    if covering is not None and covering.start != day:
        return None  # inside a pause: not its statement
    offer = PauseOffer(day, status, reminders_on)
    yesterday = day - _DAY
    if before is not None and not before.covers(yesterday):
        before = None
    if before is not None and before.end == yesterday and before.kind is status:
        return offer  # the pause ran out: ask again
    shown = prev if prev is not None else (before.kind if before is not None else None)
    return None if shown is status else offer


def place(new: RestPeriod, existing: Iterable[RestPeriod]) -> Placement:
    """The overlap rule: an earlier period covering `new.start` ends the day before (removed
    when only its start day is left), periods starting inside `new` are removed. One on
    `new.start` itself is replaced by `new` (not listed). Never merges."""
    removed: set[date] = set()
    ended: dict[date, date] = {}
    for q in existing:
        if q.start == new.start:
            continue
        if new.start < q.start <= new.end:
            removed.add(q.start)
        elif q.start < new.start <= q.end:
            end = new.start - _DAY
            if end > q.start:
                ended[q.start] = end
            else:
                removed.add(q.start)
    return Placement(frozenset(removed), ended)


def cut_by_log(
    p: RestPeriod, day: date, status: DayStatus | None
) -> RestPeriod | _Unchanged | None:
    """What a log (or a clear, `status` None) on `day` does to `p`: 🧘 Practiced ends it
    the day before (None: removed); clearing its start day removes it; anything else
    changes only that day (UNCHANGED). Kind-agnostic."""
    if not p.covers(day):
        return UNCHANGED
    if status is None:
        return None if day == p.start else UNCHANGED
    if status is not DayStatus.PRACTICED:
        return UNCHANGED
    end = day - _DAY
    return replace(p, end=end) if end > p.start else None


def end_from(p: RestPeriod, today: date) -> RestPeriod | None:
    """End early: `p` stops covering today and later (None: removed, ≤ 1 day left)."""
    if p.end < today:
        return p
    end = today - _DAY
    return replace(p, end=end) if end > p.start else None


def covered_days(
    periods: Iterable[RestPeriod],
    start: date,
    end: date,
    today: date,
    logged: Set[date] | Mapping[date, object],
) -> dict[date, DayStatus]:
    """The unlogged dates of [start, end] up to `today` that a period covers, by kind."""
    found: dict[date, DayStatus] = {}
    for p in periods:
        day, last = max(p.start, start), min(p.end, end, today)
        while day <= last:
            if day not in logged:
                found[day] = p.kind
            day += _DAY
    return found
