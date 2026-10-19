"""`PracticeRepository` on Postgres. Every write is guarded by "the day is Practiced" inside
the same statement, so details never land on a rest day."""

from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import Row, and_, case, delete, exists, func, literal, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from tristhana.application.ports.practice import CopiedPractice
from tristhana.application.practice_patch import PracticePatch
from tristhana.domain.practice import InvalidPractice, Practice, PracticeContext, PracticeLength
from tristhana.infrastructure.db.engine import connection, sqlstate
from tristhana.infrastructure.db.tables import day_log, practice

SLOT = 1
_COLUMNS = (
    practice.c.context,
    practice.c.online,
    practice.c.series,
    practice.c.end_item,
    practice.c.first_part,
    practice.c.duration_min,
    practice.c.start_time,
    practice.c.timezone,
)


def _practiced(account_id: UUID, local_date: date) -> Any:
    # FOR SHARE: a status change committed after this statement's snapshot is re-checked
    # on the locked row, so details never land on a day that just became a rest day.
    return exists(
        select(literal(1))
        .where(
            day_log.c.account_id == account_id,
            day_log.c.local_date == local_date,
            day_log.c.status == "practiced",
        )
        .with_for_update(read=True)
    )


def has_details(table: Any) -> Any:
    """A practice row with something in it (empty rows never count as "last time")."""
    return or_(
        table.c.context.is_not(None),
        table.c.series.is_not(None),
        table.c.duration_min.is_not(None),
        table.c.start_time.is_not(None),
    )


def _previous_practiced(prev: Any) -> Any:
    return exists().where(
        day_log.c.account_id == prev.c.account_id,
        day_log.c.local_date == prev.c.local_date,
        day_log.c.status == "practiced",
    )


def _columns(patch: PracticePatch) -> dict[str, Any]:
    """Column values for the patched fields."""
    p = patch.values
    out: dict[str, Any] = {}
    for name in patch.fields:
        match name:
            case "context":
                out["context"] = p.context.value if p.context else None
            case "length":
                length = p.length
                out["series"] = list(length.series) if length else None
                out["end_item"] = length.end if length else None
                out["first_part"] = length.first_part if length else None
            case _:
                out[name] = getattr(p, name)
    return out


class SqlPracticeRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def save(
        self, account_id: UUID, local_date: date, patch: PracticePatch
    ) -> Practice | None:
        values = _columns(patch)
        keys = {"account_id": account_id, "local_date": local_date, "slot": SLOT}
        row_values = keys | values
        source = select(
            *(literal(v, practice.c[k].type).label(k) for k, v in row_values.items())
        ).where(_practiced(account_id, local_date))
        stmt = insert(practice).from_select(list(row_values), source)
        updates: dict[str, Any] = {k: stmt.excluded[k] for k in values}
        if "timezone" in updates:
            # Re-sending the same start time (the Mini App PUTs every field) keeps its zone.
            updates["timezone"] = case(
                (
                    practice.c.start_time.is_not_distinct_from(stmt.excluded.start_time),
                    practice.c.timezone,
                ),
                else_=stmt.excluded.timezone,
            )
        stmt = stmt.on_conflict_do_update(
            index_elements=[practice.c.account_id, practice.c.local_date, practice.c.slot],
            set_={**updates, "updated_at": func.now()},
        ).returning(*_COLUMNS)
        return await self._one(stmt)

    async def copy_latest(
        self, account_id: UUID, local_date: date, timezone: str | None
    ) -> Practice | None:
        prev = practice.alias("prev")
        copied = ("context", "online", "series", "end_item", "first_part", "duration_min")
        source = (
            select(
                literal(account_id, practice.c.account_id.type),
                literal(local_date, practice.c.local_date.type),
                literal(SLOT, practice.c.slot.type),
                *(prev.c[c] for c in copied),
                literal(timezone, practice.c.timezone.type),
            )
            .where(
                prev.c.account_id == account_id,
                prev.c.local_date < local_date,
                has_details(prev),
                _previous_practiced(prev),
                _practiced(account_id, local_date),
            )
            .order_by(prev.c.local_date.desc(), prev.c.slot.desc())
            .limit(1)
        )
        stmt = insert(practice).from_select(
            ["account_id", "local_date", "slot", *copied, "timezone"], source
        )
        # The start time (and its zone) is not copied; an existing one on this day is kept.
        stmt = stmt.on_conflict_do_update(
            index_elements=[practice.c.account_id, practice.c.local_date, practice.c.slot],
            set_={**{c: stmt.excluded[c] for c in copied}, "updated_at": func.now()},
        ).returning(*_COLUMNS)
        return await self._one(stmt)

    async def copy_usual(
        self, account_id: UUID, local_date: date, timezone: str | None
    ) -> CopiedPractice | None:
        prev = practice.alias("prev")
        copied = ("context", "online", "series", "end_item", "first_part", "duration_min")
        source = (
            select(*(prev.c[c] for c in copied), prev.c.local_date.label("source"))
            .where(
                prev.c.account_id == account_id,
                prev.c.local_date < local_date,
                has_details(prev),
                _previous_practiced(prev),
                _practiced(account_id, local_date),
            )
            # Non-Led first (NULL context counts as non-Led), then the newest.
            .order_by(
                prev.c.context.is_not_distinct_from("led"),
                prev.c.local_date.desc(),
                prev.c.slot.desc(),
            )
            .limit(1)
            .cte("source")
        )
        inserted = insert(practice).from_select(
            ["account_id", "local_date", "slot", *copied, "timezone"],
            select(
                literal(account_id, practice.c.account_id.type),
                literal(local_date, practice.c.local_date.type),
                literal(SLOT, practice.c.slot.type),
                *(source.c[c] for c in copied),
                literal(timezone, practice.c.timezone.type),
            ),
        )
        inserted = (
            inserted.on_conflict_do_update(
                index_elements=[practice.c.account_id, practice.c.local_date, practice.c.slot],
                set_={**{c: inserted.excluded[c] for c in copied}, "updated_at": func.now()},
            )
            .returning(*_COLUMNS)
            .cte("inserted")
        )
        stmt = (
            select(*inserted.c, source.c.source).select_from(inserted).join(source, literal(True))
        )
        try:
            async with connection(self._engine) as conn:
                row = (await conn.execute(stmt)).one_or_none()
        except IntegrityError as e:
            if sqlstate(e) == "23514":
                raise InvalidPractice("rejected by the database") from e
            raise
        return CopiedPractice(to_practice(row), row.source) if row else None

    async def delete(self, account_id: UUID, local_date: date) -> None:
        stmt = delete(practice).where(
            practice.c.account_id == account_id, practice.c.local_date == local_date
        )
        async with connection(self._engine) as conn:
            await conn.execute(stmt)

    async def recent(self, account_id: UUID, before: date, limit: int) -> list[Practice]:
        stmt = (
            select(*_COLUMNS)
            .join(
                day_log,
                and_(
                    day_log.c.account_id == practice.c.account_id,
                    day_log.c.local_date == practice.c.local_date,
                    day_log.c.status == "practiced",
                ),
            )
            .where(
                practice.c.account_id == account_id,
                practice.c.local_date < before,
                has_details(practice),
            )
            .order_by(practice.c.local_date.desc(), practice.c.slot.desc())
            .limit(limit)
        )
        async with connection(self._engine) as conn:
            rows = (await conn.execute(stmt)).all()
        return [to_practice(r) for r in rows]

    async def _one(self, stmt: Any) -> Practice | None:
        try:
            async with connection(self._engine) as conn:
                row = (await conn.execute(stmt)).one_or_none()
        except IntegrityError as e:
            if sqlstate(e) == "23514":  # check_violation, e.g. online self-practice
                raise InvalidPractice("rejected by the database") from e
            raise
        return to_practice(row) if row else None


def to_practice(row: Row[*tuple[Any, ...]]) -> Practice:
    length = None
    if row.series is not None:
        length = PracticeLength(tuple(row.series), row.end_item, row.first_part)
    return Practice(
        context=PracticeContext(row.context) if row.context else None,
        online=row.online,
        length=length,
        duration_min=row.duration_min,
        start_time=row.start_time,
        timezone=row.timezone,
    )
