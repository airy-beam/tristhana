"""Shared case table for the rest-period overlap and cut rules (WH-01 part 2, ADR-0023).

The domain (`domain/rest_periods.py`) and the SQL (CTEs in `db/rest_periods.py` and
`db/days.py`) must agree: `tests/domain/test_rest_periods.py` and
`tests/infrastructure/test_db_rest_periods.py` both run these cases. Dates are offsets from
a fixed Monday; `expected` is every period of the account afterwards, oldest first.
"""

from dataclasses import dataclass
from datetime import date, timedelta

from tristhana.domain.days import DayStatus
from tristhana.domain.rest_periods import RestPeriod

BASE = date(2026, 10, 26)
L, K, T = DayStatus.LADIES, DayStatus.SICK, DayStatus.TRAVEL


def d(offset: int) -> date:
    return BASE + timedelta(days=offset)


def p(start: int, end: int, kind: DayStatus = L) -> RestPeriod:
    return RestPeriod(d(start), d(end), kind)


@dataclass(frozen=True, slots=True)
class PlaceCase:
    id: str
    existing: tuple[RestPeriod, ...]
    new: RestPeriod
    expected: tuple[RestPeriod, ...]


@dataclass(frozen=True, slots=True)
class CutCase:
    id: str
    period: RestPeriod
    day: int  # offset of the logged / cleared day
    status: DayStatus | None  # None = the day is cleared
    expected: tuple[RestPeriod, ...]


PLACE_CASES = (
    PlaceCase("ends-earlier", (p(-4, 2, K),), p(0, 2, L), (p(-4, -1, K), p(0, 2, L))),
    PlaceCase("removes-earlier-left-with-its-start", (p(-1, 3, K),), p(0, 4, L), (p(0, 4, L),)),
    PlaceCase(
        "removes-later-starts-inside",
        (p(2, 5, T), p(6, 9, T)),
        p(0, 3, K),
        (p(0, 3, K), p(6, 9, T)),
    ),
    PlaceCase("adjacent-untouched", (p(-3, -1, L),), p(0, 2, L), (p(-3, -1, L), p(0, 2, L))),
    PlaceCase("same-start-replaced", (p(0, 4, L),), p(0, 1, K), (p(0, 1, K),)),
    PlaceCase(
        "earlier-and-later-at-once",
        (p(-4, 1, K), p(2, 5, T)),
        p(0, 2, L),
        (p(-4, -1, K), p(0, 2, L)),
    ),
    PlaceCase("max-length", (), p(-1, 12, K), (p(-1, 12, K),)),
)

CUT_CASES = (
    CutCase("practiced-on-start", p(0, 4), 0, DayStatus.PRACTICED, ()),
    CutCase("practiced-in-middle", p(-3, 3), 0, DayStatus.PRACTICED, (p(-3, -1),)),
    CutCase("practiced-on-last", p(-3, 0), 0, DayStatus.PRACTICED, (p(-3, -1),)),
    CutCase("practiced-on-second", p(-1, 3), 0, DayStatus.PRACTICED, ()),
    CutCase("practiced-outside", p(-3, -1), 0, DayStatus.PRACTICED, (p(-3, -1),)),
    CutCase("skipped-in-middle", p(-3, 3, K), 0, DayStatus.SKIPPED, (p(-3, 3, K),)),
    CutCase("rest-in-middle", p(-3, 3, K), 0, DayStatus.REST, (p(-3, 3, K),)),
    CutCase("moon-on-start", p(0, 3, T), 0, DayStatus.MOON, (p(0, 3, T),)),
    CutCase("other-kind-in-middle", p(-3, 3, K), 0, DayStatus.LADIES, (p(-3, 3, K),)),
    CutCase("clear-start", p(0, 4), 0, None, ()),
    CutCase("clear-middle", p(-2, 4), 1, None, (p(-2, 4),)),
)
