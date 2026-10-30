"""Stored moon calendars (MD-01 storage, ADR-0019)."""

from collections.abc import Sequence
from datetime import date

from sqlalchemy import delete, func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncEngine

from tristhana.domain.moon import MoonDay, MoonDayKind
from tristhana.infrastructure.db.engine import connection
from tristhana.infrastructure.db.tables import moon_calendar, moon_day


class SqlMoonCalendarRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def days(self, location: str, start: date, end: date) -> list[MoonDay]:
        stmt = (
            select(moon_day.c.date, moon_day.c.kind)
            .where(moon_day.c.location == location, moon_day.c.date.between(start, end))
            .order_by(moon_day.c.date)
        )
        async with connection(self._engine) as conn:
            rows = (await conn.execute(stmt)).all()
        return [MoonDay(r.date, MoonDayKind(r.kind)) for r in rows]

    async def days_for(
        self, locations: Sequence[str], start: date, end: date
    ) -> dict[str, list[MoonDay]]:
        unique = list(dict.fromkeys(locations))
        stmt = (
            select(moon_day.c.location, moon_day.c.date, moon_day.c.kind)
            .where(moon_day.c.location.in_(unique), moon_day.c.date.between(start, end))
            .order_by(moon_day.c.location, moon_day.c.date)
        )
        async with connection(self._engine) as conn:
            rows = (await conn.execute(stmt)).all()
        by: dict[str, list[MoonDay]] = {loc: [] for loc in unique}
        for r in rows:
            by[r.location].append(MoonDay(r.date, MoonDayKind(r.kind)))
        return by

    async def coverage(self) -> dict[tuple[str, int], str]:
        stmt = select(moon_calendar.c.location, moon_calendar.c.year, moon_calendar.c.algo_version)
        async with connection(self._engine) as conn:
            rows = (await conn.execute(stmt)).all()
        return {(r.location, r.year): r.algo_version for r in rows}

    async def replace_year(
        self, location: str, year: int, days: list[MoonDay], algo_version: str
    ) -> None:
        start, end = date(year, 1, 1), date(year, 12, 31)
        async with connection(self._engine) as conn:
            # The engine autocommits single statements; this needs a real transaction, so
            # readers never see an empty year and two top-ups of one city-year serialize.
            conn = await conn.execution_options(isolation_level="READ COMMITTED")
            async with conn.begin():
                await conn.execute(
                    text("SELECT pg_advisory_xact_lock(hashtext(:k))"),
                    {"k": f"moon:{location}:{year}"},
                )
                await conn.execute(
                    delete(moon_day).where(
                        moon_day.c.location == location, moon_day.c.date.between(start, end)
                    )
                )
                if days:
                    await conn.execute(
                        insert(moon_day),
                        [
                            {"location": location, "date": d.date, "kind": d.kind.value}
                            for d in days
                        ],
                    )
                ledger = insert(moon_calendar).values(
                    location=location, year=year, algo_version=algo_version
                )
                await conn.execute(
                    ledger.on_conflict_do_update(
                        index_elements=[moon_calendar.c.location, moon_calendar.c.year],
                        set_={"algo_version": algo_version, "computed_at": func.now()},
                    )
                )
