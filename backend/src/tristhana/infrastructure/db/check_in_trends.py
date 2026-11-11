"""`CheckInTrendsRepository` on Postgres (ST-05): one statement, plain columns only.

Two single-row aggregates cross-joined into one row (the `db/badges.py` pattern). The
check-ins are joined to `day_log` on `status = 'practiced'` (ADR-0024): a stray row left on a
day that is no longer Practiced, possibly a 🌸 day stored as `rest`, is never read.
`day_log.sealed_status` and `check_in.tags` are never selected.
"""

from datetime import date, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import Select, and_, func, or_, select, true
from sqlalchemy.dialects.postgresql import aggregate_order_by
from sqlalchemy.ext.asyncio import AsyncEngine

from tristhana.domain.check_in_trends import NEAR_DAYS, ScaleDay, TrendFacts
from tristhana.domain.days import DayStatus
from tristhana.domain.moon import MoonDay, MoonDayKind
from tristhana.infrastructure.db.engine import connection
from tristhana.infrastructure.db.tables import check_in, day_log, moon_day

_NEAR = timedelta(days=NEAR_DAYS)


def _agg(column: Any, order: Any) -> Any:
    return func.array_agg(aggregate_order_by(column, order))


def facts_statement(account_id: UUID, moon_location: str, start: date, end: date) -> Select[Any]:
    c, d, m = check_in, day_log, moon_day
    on = c.c.local_date
    scales = (
        select(
            _agg(on, on).label("dates"),
            _agg(c.c.mood, on).label("moods"),
            _agg(c.c.energy, on).label("energies"),
            _agg(c.c.effort, on).label("efforts"),
        )
        .select_from(
            c.join(d, and_(d.c.account_id == c.c.account_id, d.c.local_date == c.c.local_date))
        )
        .where(
            c.c.account_id == account_id,
            c.c.slot == 1,
            d.c.status == DayStatus.PRACTICED.value,
            on.between(start, end),
            or_(c.c.mood.is_not(None), c.c.energy.is_not(None), c.c.effort.is_not(None)),
        )
        .subquery("scales")
    )
    moon = (
        select(
            _agg(m.c.date, m.c.date).label("moon_dates"),
            _agg(m.c.kind, m.c.date).label("moon_kinds"),
        )
        .where(m.c.location == moon_location, m.c.date.between(start - _NEAR, end + _NEAR))
        .subquery("moon")
    )
    return select(scales, moon).select_from(scales).join(moon, true())


class SqlCheckInTrendsRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def facts(
        self, account_id: UUID, moon_location: str, start: date, end: date
    ) -> TrendFacts:
        statement = facts_statement(account_id, moon_location, start, end)
        async with connection(self._engine) as conn:
            m = (await conn.execute(statement)).one()._mapping  # pyright: ignore[reportPrivateUsage]
        days = tuple(
            ScaleDay(on, mood, energy, effort)
            for on, mood, energy, effort in zip(
                m["dates"] or [],
                m["moods"] or [],
                m["energies"] or [],
                m["efforts"] or [],
                strict=True,
            )
        )
        moon = tuple(
            MoonDay(on, MoonDayKind(kind))
            for on, kind in zip(m["moon_dates"] or [], m["moon_kinds"] or [], strict=True)
        )
        return TrendFacts(days, moon)
