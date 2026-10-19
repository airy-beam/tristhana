"""Practice stats (ST-01..03): heatmap cells, period summaries and runs. Pure: no I/O,
no clock (ADR-0020).

Rules (owner, 2026-10-19; Q18). Rest-like days (rest, moon, ladies' holiday, sick, travel)
are part of the practice: they never count for or against anyone. "Possible days" are
practiced + "No practice". A run counts practice days only; rest-like days are transparent,
"No practice" ends it quietly, and so do more than MAX_UNLOGGED_BRIDGE unmarked days in a
row. Today never ends a run: the day isn't over.
"""

from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import date, timedelta

from tristhana.domain.days import REST_LIKE, DayLog, DayStatus
from tristhana.domain.practice import PracticeContext

# A week: an unlogged ladies' holiday next to a day off and a moon day must not end a run;
# someone back after months must not see an old run continue (ashtanga-expert).
MAX_UNLOGGED_BRIDGE = 7

type SeriesNumber = Callable[[str], int | None]
type Cell = DayStatus | None


@dataclass(frozen=True, slots=True)
class Summary:
    practiced: int = 0
    skipped: int = 0
    unlogged: int = 0  # strictly before today
    rest: dict[DayStatus, int] = field(default_factory=dict[DayStatus, int])
    contexts: dict[PracticeContext, int] = field(default_factory=dict[PracticeContext, int])
    online: int = 0
    series: dict[int, int] = field(default_factory=dict[int, int])  # 0 = short practice
    unspecified: int = 0  # practiced without a length ("No details", e.g. pranayama only)
    duration_total: int = 0
    duration_count: int = 0

    @property
    def possible(self) -> int:
        return self.practiced + self.skipped


@dataclass(frozen=True, slots=True)
class Run:
    first: date
    last: date
    practices: int


@dataclass(frozen=True, slots=True)
class Runs:
    runs: list[Run]
    current: Run | None  # still open at today


@dataclass(frozen=True, slots=True)
class YearStats:
    cells: list[Cell]  # Jan 1 … min(Dec 31, today)
    months: list[Summary]  # 12
    year_total: Summary
    current_run: int | None  # only for the current year
    longest_run: int  # the longest run touching the year (counted whole)


def _days_between(start: date, end: date) -> list[date]:
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


def _series_bucket(series: tuple[str, ...], number: SeriesNumber) -> int | None:
    """The furthest series of a length (0 = short); None when it can't be placed."""
    if not series:
        return 0
    numbers = [n for n in (number(s) for s in series) if n is not None]
    return max(numbers) if numbers and len(numbers) == len(series) else None


def summarize(
    days: Mapping[date, DayLog], start: date, end: date, today: date, number: SeriesNumber
) -> Summary:
    """The period [start, end]; days after today are ignored."""
    rest: Counter[DayStatus] = Counter()
    contexts: Counter[PracticeContext] = Counter()
    series: Counter[int] = Counter()
    practiced = skipped = unlogged = online = unspecified = total = count = 0
    for d in _days_between(start, min(end, today)):
        day = days.get(d)
        if day is None:
            unlogged += d < today
            continue
        if day.status in REST_LIKE:
            rest[day.status] += 1
        elif day.status is DayStatus.SKIPPED:
            skipped += 1
        elif day.status is DayStatus.PRACTICED:
            practiced += 1
            # Slot 1 only for now (one practice per day; ADR-0005 keeps room for more).
            p = day.practices[0] if day.practices else None
            if p is not None and p.context is not None:
                contexts[p.context] += 1
                online += p.online
            bucket = (
                _series_bucket(p.length.series, number)
                if p is not None and p.length is not None
                else None
            )
            if bucket is None:
                unspecified += 1
            else:
                series[bucket] += 1
            if p is not None and p.duration_min:
                total += p.duration_min
                count += 1
    return Summary(
        practiced=practiced,
        skipped=skipped,
        unlogged=unlogged,
        rest=dict(rest),
        contexts=dict(contexts),
        online=online,
        series=dict(series),
        unspecified=unspecified,
        duration_total=total,
        duration_count=count,
    )


def find_runs(days: Mapping[date, DayLog], start: date, today: date) -> Runs:
    """Runs from `start` up to today (today counts only when logged)."""
    runs: list[Run] = []
    first: date | None = None
    last: date | None = None
    practices = gap = 0

    def close() -> None:
        nonlocal first, last, practices
        if first is not None and last is not None:
            runs.append(Run(first, last, practices))
        first, last, practices = None, None, 0

    for d in _days_between(start, today):
        day = days.get(d)
        if day is None:
            if d == today:
                continue
            gap += 1
            if gap > MAX_UNLOGGED_BRIDGE:
                close()
            continue
        gap = 0
        if day.status is DayStatus.PRACTICED:
            first = first or d
            last = d
            practices += 1
        elif day.status is DayStatus.SKIPPED:
            close()
    current = Run(first, last, practices) if first is not None and last is not None else None
    if current is not None:
        runs.append(current)
    return Runs(runs, current)


def year_stats(
    days: Mapping[date, DayLog], year: int, today: date, number: SeriesNumber
) -> YearStats:
    """`days` should cover the previous and the next year (up to today), so a run crossing
    New Year is counted whole."""
    start, end = date(year, 1, 1), date(year, 12, 31)
    shown = _days_between(start, min(end, today)) if start <= today else []
    cells: list[Cell] = [days[d].status if d in days else None for d in shown]
    months = [
        summarize(days, date(year, m, 1), _month_end(year, m), today, number) for m in range(1, 13)
    ]
    found = find_runs(days, date(year - 1, 1, 1), min(date(year + 1, 12, 31), today))
    touching = [r for r in found.runs if r.first.year <= year <= r.last.year]
    current = found.current.practices if year == today.year and found.current else None
    return YearStats(
        cells=cells,
        months=months,
        year_total=summarize(days, start, end, today, number),
        current_run=current,
        longest_run=max((r.practices for r in touching), default=0),
    )


def _month_end(year: int, month: int) -> date:
    following = date(year + month // 12, month % 12 + 1, 1)
    return following - timedelta(days=1)
