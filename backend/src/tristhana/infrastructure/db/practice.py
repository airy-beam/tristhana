"""`PracticeRepository` on Postgres. Every write is guarded by "the day is Practiced" inside
the same statement, so details never land on a rest day."""

from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import Row, and_, case, delete, exists, func, literal, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from tristhana.application.ports.practice import CopiedPractice, SavedPractice
from tristhana.application.practice_patch import PracticePatch
from tristhana.domain.practice import InvalidPractice, Practice, PracticeContext, PracticeLength
from tristhana.domain.progression import Progression
from tristhana.infrastructure.db.engine import connection, sqlstate
from tristhana.infrastructure.db.progression import state_columns, to_progression
from tristhana.infrastructure.db.tables import check_in, day_log, practice, progression

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


def practiced(account_id: UUID, local_date: date) -> Any:
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
    ) -> SavedPractice | None:
        values = _columns(patch)
        keys = {"account_id": account_id, "local_date": local_date, "slot": SLOT}
        row_values = keys | values
        source = select(
            *(literal(v, practice.c[k].type).label(k) for k, v in row_values.items())
        ).where(practiced(account_id, local_date))
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
        return await self._with_check_in(stmt, account_id, local_date)

    async def copy_latest(
        self, account_id: UUID, local_date: date, timezone: str | None
    ) -> SavedPractice | None:
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
                practiced(account_id, local_date),
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
        return await self._with_check_in(stmt, account_id, local_date)

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
                practiced(account_id, local_date),
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
        async with connection(self._engine) as conn:
            rows = (await conn.execute(_recent(account_id, before, limit))).all()
        return [to_practice(r) for r in rows]

    async def recent_with_progression(
        self, account_id: UUID, before: date, limit: int
    ) -> tuple[list[Practice], Progression | None]:
        recent = _recent(account_id, before, limit).lateral("recent")
        one = select(literal(1).label("one")).subquery("one")
        joined = one.outerjoin(progression, progression.c.account_id == account_id).outerjoin(
            recent, literal(True)
        )
        stmt = (
            select(*state_columns(), *recent.c)
            .select_from(joined)
            .order_by(recent.c.local_date.desc(), recent.c.slot.desc())
        )
        async with connection(self._engine) as conn:
            rows = (await conn.execute(stmt)).all()
        found = [to_practice(r) for r in rows if r.local_date is not None]
        return found, to_progression(rows[0])

    async def _with_check_in(
        self, upsert: Any, account_id: UUID, local_date: date
    ) -> SavedPractice | None:
        """The upsert plus the day's check-in (PR-06), the progression and whether the length
        changed (PR-08), still one statement: the practice screen shows them without a second
        read. The row is the guarded upsert's, so a day that isn't Practiced returns nothing.
        Every CTE sees the snapshot before the upsert, so `before` is the old row."""
        # Imported here: check_in.py imports this module's `practiced` guard.
        from tristhana.infrastructure.db.check_in import to_check_in

        before = (
            select(practice.c.series, practice.c.end_item, practice.c.first_part)
            .where(
                practice.c.account_id == account_id,
                practice.c.local_date == local_date,
                practice.c.slot == SLOT,
            )
            .cte("before")
        )
        saved = upsert.cte("saved")
        changed = or_(
            *(
                saved.c[c].is_distinct_from(before.c[c])
                for c in ("series", "end_item", "first_part")
            )
        )
        stmt = select(
            saved,
            check_in.c.slot.label("check_in_slot"),
            check_in.c.mood,
            check_in.c.energy,
            check_in.c.effort,
            check_in.c.tags,
            *state_columns(),
            changed.label("length_changed"),
        ).select_from(
            saved.outerjoin(
                check_in,
                and_(check_in.c.account_id == account_id, check_in.c.local_date == local_date),
            )
            .outerjoin(before, literal(True))
            .outerjoin(progression, progression.c.account_id == account_id)
        )
        try:
            async with connection(self._engine) as conn:
                row = (await conn.execute(stmt)).one_or_none()
        except IntegrityError as e:
            if sqlstate(e) == "23514":  # check_violation, e.g. online self-practice
                raise InvalidPractice("rejected by the database") from e
            raise
        if row is None:
            return None
        found = to_check_in(row) if row.check_in_slot is not None else None
        return SavedPractice(
            to_practice(row),
            None if found is None or found.is_empty() else found,
            to_progression(row),
            bool(row.length_changed),
        )


def _recent(account_id: UUID, before: date, limit: int) -> Any:
    """Practices with details on Practiced days before `before`, newest first."""
    return (
        select(*_COLUMNS, practice.c.local_date, practice.c.slot)
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
