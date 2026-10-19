"""Stats rules (ST-01..03, Q18): runs, possible days, month summaries, cells."""

from datetime import date, timedelta

import pytest

from tristhana.domain.days import DayLog, DayStatus
from tristhana.domain.practice import Practice, PracticeContext, PracticeLength
from tristhana.domain.stats import (
    MAX_UNLOGGED_BRIDGE,
    find_runs,
    summarize,
    year_stats,
)

SERIES = {"primary": 1, "intermediate": 2, "advanced-a": 3}
START = date(2026, 10, 1)  # a Thursday
P, R, N, M = DayStatus.PRACTICED, DayStatus.REST, DayStatus.SKIPPED, DayStatus.MOON
L, S, T = DayStatus.LADIES, DayStatus.SICK, DayStatus.TRAVEL


def _number(slug: str) -> int | None:
    return SERIES.get(slug)


def _days(pattern: str, start: date = START) -> dict[date, DayLog]:
    """'P' practiced, 'R' rest, 'N' no practice, 'M' moon, 'L' ladies, 'S' sick,
    'T' travel, '.' not logged."""
    codes = {"P": P, "R": R, "N": N, "M": M, "L": L, "S": S, "T": T}
    return {
        start + timedelta(days=i): DayLog(start + timedelta(days=i), codes[c])
        for i, c in enumerate(pattern)
        if c != "."
    }


def _runs(pattern: str, today_offset: int | None = None) -> tuple[int | None, int]:
    """(current, longest) with today = the day after the pattern unless given."""
    today = START + timedelta(days=len(pattern) if today_offset is None else today_offset)
    found = find_runs(_days(pattern), START, today)
    current = found.current.practices if found.current else None
    return current, max((r.practices for r in found.runs), default=0)


@pytest.mark.parametrize(
    ("pattern", "current", "longest"),
    [
        ("PPRP", 3, 3),  # rest is transparent
        ("PPNP", 1, 2),  # "No practice" ends a run quietly
        ("PMLSTP", 2, 2),  # every rest-like kind is transparent
        ("P.P", 2, 2),  # an unlogged Saturday off never inflates or ends it
        ("P" + "." * MAX_UNLOGGED_BRIDGE + "P", 2, 2),  # a week unmarked still bridges
        ("P" + "." * (MAX_UNLOGGED_BRIDGE + 1) + "P", 1, 1),  # more than a week ends it
        ("PP", 2, 2),
        ("PPN", None, 2),
        ("", None, 0),
    ],
)
def test_runs(pattern: str, current: int | None, longest: int) -> None:
    assert _runs(pattern) == (current, longest)


def test_today_unlogged_never_ends_a_run() -> None:
    # Today is the last pattern day and has no mark yet.
    assert _runs("PP.", today_offset=2) == (2, 2)


def test_rest_days_reset_the_unmarked_count() -> None:
    gap = "." * MAX_UNLOGGED_BRIDGE
    assert _runs(f"P{gap}R{gap}P") == (2, 2)


def test_bridge_is_seven() -> None:
    assert MAX_UNLOGGED_BRIDGE == 7


def test_unmarked_days_before_today_end_a_current_run() -> None:
    today_offset = 1 + MAX_UNLOGGED_BRIDGE + 1
    assert _runs("P", today_offset=today_offset) == (None, 1)


def _practice(
    series: tuple[str, ...] = (),
    context: PracticeContext | None = None,
    duration: int | None = None,
    online: bool = False,
    first_part: str | None = None,
    end: str | None = None,
    length: bool = True,
) -> Practice:
    return Practice(
        context=context,
        online=online,
        length=PracticeLength(series, end, first_part) if length else None,  # type: ignore[arg-type]
        duration_min=duration,
    )


def test_month_summary() -> None:
    days = _days("PPNRMLST..")
    days[START] = DayLog(START, P, (_practice(("primary",), PracticeContext.LED, 90, online=True),))
    days[START + timedelta(days=1)] = DayLog(
        START + timedelta(days=1),
        P,
        (
            _practice(
                ("primary", "intermediate"), PracticeContext.MYSORE, 120, first_part="second_half"
            ),
        ),
    )
    today = START + timedelta(days=9)  # the last '.' is today

    s = summarize(days, START, START + timedelta(days=30), today, _number)

    assert (s.practiced, s.skipped, s.possible, s.unlogged) == (2, 1, 3, 1)
    assert s.rest == {R: 1, M: 1, L: 1, S: 1, T: 1}
    assert s.contexts == {PracticeContext.LED: 1, PracticeContext.MYSORE: 1}
    assert s.online == 1
    assert s.series == {1: 1, 2: 1}  # the furthest series of each length
    assert s.unspecified == 0
    assert (s.duration_total, s.duration_count) == (210, 2)


def test_series_buckets() -> None:
    lengths = [
        _practice(()),  # short
        _practice(("primary",), first_part="first_half", length=True),
        _practice(("advanced-a",), end="x"),
        _practice(length=False),  # pranayama-only or no details
        _practice(("retired-series",)),  # a stale catalog key
    ]
    days = {
        START + timedelta(days=i): DayLog(START + timedelta(days=i), P, (p,))
        for i, p in enumerate(lengths)
    }
    days[START + timedelta(days=9)] = DayLog(START + timedelta(days=9), P)  # no details row

    s = summarize(days, START, START + timedelta(days=30), START + timedelta(days=10), _number)

    assert s.practiced == 6
    assert s.series == {0: 1, 1: 1, 3: 1}
    assert s.unspecified == 3


def test_year_stats_cells_and_moon_practice() -> None:
    year_start = date(2026, 1, 1)
    days = _days("PMN", year_start)
    today = date(2026, 1, 5)

    y = year_stats(days, 2026, today, _number)

    assert y.cells[:5] == [P, M, N, None, None]
    assert len(y.cells) == 5  # Jan 1 … today
    assert y.year_total.practiced == 1
    assert len(y.months) == 12
    assert y.months[0].possible == 2
    assert y.months[1].practiced == 0


def test_a_past_year_has_all_its_days_and_no_current_run() -> None:
    days = _days("PP", date(2024, 12, 30))

    y = year_stats(days, 2024, date(2026, 10, 19), _number)

    assert len(y.cells) == 366  # leap year
    assert y.current_run is None
    assert y.longest_run == 2


def test_a_run_across_new_year_counts_whole() -> None:
    days = _days("PPPP", date(2025, 12, 30))

    y = year_stats(days, 2026, date(2026, 1, 3), _number)

    assert y.current_run == 4
    assert y.longest_run == 4


def test_a_past_year_counts_a_run_into_january_whole() -> None:
    days = _days("PPPP", date(2025, 12, 30))

    y = year_stats(days, 2025, date(2026, 10, 19), _number)

    assert y.longest_run == 4
    assert y.current_run is None


def test_a_no_practice_today_ends_the_current_run() -> None:
    assert _runs("PPN", today_offset=2) == (None, 2)
