"""`BadgeFactsRepository` on Postgres (GM-02, ADR-0041): one statement, plain columns only.

Single-row aggregates over each table (by PK or `(account_id, id)`), cross-joined into one
row. `day_log.sealed_status` and `rest_period.sealed_kind` are never selected: a 🌸 day reads
as `rest`, and a period is its dates alone, so the badges can't tell 🌸 from 😌.
"""

from datetime import date, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import Select, func, select, true
from sqlalchemy.dialects.postgresql import aggregate_order_by
from sqlalchemy.ext.asyncio import AsyncEngine

from tristhana.domain.badges import BadgeFacts
from tristhana.domain.days import DayStatus
from tristhana.domain.progression import EventKind, Position, ProgressionEvent
from tristhana.infrastructure.db.engine import connection
from tristhana.infrastructure.db.tables import (
    day_log,
    moon_day,
    practice,
    practice_milestone,
    progression_event,
    rest_period,
)

_DAY = timedelta(days=1)


def _agg(column: Any, order: Any) -> Any:
    return func.array_agg(aggregate_order_by(column, order))


def facts_statement(account_id: UUID, moon_location: str, today: date) -> Select[Any]:
    d, p, r, e = day_log, practice, rest_period, progression_event
    days = (
        select(
            _agg(d.c.local_date, d.c.local_date).label("dates"),
            _agg(d.c.status, d.c.local_date).label("statuses"),
        )
        .where(d.c.account_id == account_id)
        .subquery("days")
    )
    by_date = p.c.local_date
    details = (
        select(
            _agg(by_date, by_date).filter(p.c.context == "led").label("led"),
            _agg(by_date, by_date).filter(p.c.context == "self").label("own"),
            _agg(by_date, by_date).filter(p.c.start_time.is_not(None)).label("start_dates"),
            _agg(p.c.start_time, by_date).filter(p.c.start_time.is_not(None)).label("starts"),
        )
        .where(p.c.account_id == account_id, p.c.slot == 1)
        .subquery("details")
    )
    periods = (
        select(
            _agg(r.c.start_date, r.c.start_date).label("period_starts"),
            _agg(r.c.end_date, r.c.start_date).label("period_ends"),
        )
        .where(r.c.account_id == account_id)
        .subquery("periods")
    )
    first = select(func.min(d.c.local_date)).where(d.c.account_id == account_id).scalar_subquery()
    moon = (
        select(_agg(moon_day.c.date, moon_day.c.date).label("moon"))
        .where(moon_day.c.location == moon_location, moon_day.c.date.between(first, today))
        .subquery("moon")
    )
    kept = (
        select(func.array_agg(practice_milestone.c.threshold).label("kept"))
        .where(practice_milestone.c.account_id == account_id)
        .subquery("kept")
    )
    events = (
        select(
            _agg(e.c.id, e.c.id).label("event_ids"),
            _agg(e.c.kind, e.c.id).label("event_kinds"),
            _agg(e.c.to_series, e.c.id).label("event_series"),
            _agg(e.c.to_key, e.c.id).label("event_keys"),
            _agg(e.c.item, e.c.id).label("event_items"),
            _agg(e.c.occurred_on, e.c.id).label("event_dates"),
        )
        .where(e.c.account_id == account_id)
        .subquery("events")
    )
    return (
        select(days, details, periods, moon, kept, events)
        .select_from(days)
        .join(details, true())
        .join(periods, true())
        .join(moon, true())
        .join(kept, true())
        .join(events, true())
    )


class SqlBadgeFactsRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def facts(self, account_id: UUID, moon_location: str, today: date) -> BadgeFacts:
        async with connection(self._engine) as conn:
            row = (await conn.execute(facts_statement(account_id, moon_location, today))).one()
        return _facts(row._mapping)  # pyright: ignore[reportPrivateUsage]


def _list(value: list[Any] | None) -> list[Any]:
    return value or []


def _facts(m: Any) -> BadgeFacts:
    logged = dict(zip(_list(m["dates"]), map(DayStatus, _list(m["statuses"])), strict=True))
    covered: set[date] = set()
    for start, end in zip(_list(m["period_starts"]), _list(m["period_ends"]), strict=True):
        day = start
        while day <= end:
            covered.add(day)
            day += _DAY
    events = tuple(
        ProgressionEvent(
            i,
            EventKind(kind),
            on,
            after=Position(series, key) if item is None else None,
            item=item,
        )
        for i, kind, series, key, item, on in zip(
            _list(m["event_ids"]),
            _list(m["event_kinds"]),
            _list(m["event_series"]),
            _list(m["event_keys"]),
            _list(m["event_items"]),
            _list(m["event_dates"]),
            strict=True,
        )
    )
    return BadgeFacts(
        logged=logged,
        covered=frozenset(covered),
        moon=frozenset(_list(m["moon"])),
        led=tuple(_list(m["led"])),
        self_=tuple(_list(m["own"])),
        starts=tuple(zip(_list(m["start_dates"]), _list(m["starts"]), strict=True)),
        kept_counts=frozenset(_list(m["kept"])),
        events=events,
    )
