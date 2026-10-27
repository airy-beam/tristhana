"""`CheckInRepository` on Postgres (PR-06, ADR-0024). Like practice details, every write is
guarded by "the day is Practiced" inside the same statement."""

from collections.abc import Iterable
from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import Row, case, delete, func, literal, select
from sqlalchemy.dialects.postgresql import array, insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from tristhana.application.check_in_patch import CheckInPatch
from tristhana.domain.check_in import CheckIn, CheckInTag, InvalidCheckIn
from tristhana.infrastructure.db.engine import connection, sqlstate
from tristhana.infrastructure.db.practice import practiced
from tristhana.infrastructure.db.tables import check_in

SLOT = 1
_COLUMNS = (check_in.c.mood, check_in.c.energy, check_in.c.effort, check_in.c.tags)
_KEY = [check_in.c.account_id, check_in.c.local_date, check_in.c.slot]


def _columns(patch: CheckInPatch) -> dict[str, Any]:
    c = patch.values
    return {
        name: sorted(t.value for t in c.tags) if name == "tags" else getattr(c, name)
        for name in patch.fields
    }


class SqlCheckInRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def save(self, account_id: UUID, local_date: date, patch: CheckInPatch) -> CheckIn | None:
        values = _columns(patch)
        row_values = {"account_id": account_id, "local_date": local_date, "slot": SLOT} | values
        source = select(
            *(literal(v, check_in.c[k].type).label(k) for k, v in row_values.items())
        ).where(practiced(account_id, local_date))
        stmt = insert(check_in).from_select(list(row_values), source)
        stmt = stmt.on_conflict_do_update(
            index_elements=_KEY,
            set_={**{k: stmt.excluded[k] for k in values}, "updated_at": func.now()},
        ).returning(*_COLUMNS)
        return await self._one(stmt)

    async def set_tag(
        self, account_id: UUID, local_date: date, tag: CheckInTag, on: bool
    ) -> CheckIn | None:
        key = literal(tag.value)
        source = select(
            literal(account_id, check_in.c.account_id.type),
            literal(local_date, check_in.c.local_date.type),
            literal(SLOT, check_in.c.slot.type),
            array([key]) if on else literal([], check_in.c.tags.type),
        ).where(practiced(account_id, local_date))
        stmt = insert(check_in).from_select(["account_id", "local_date", "slot", "tags"], source)
        # Absolute and atomic: two quick taps on different tags both land (row lock).
        removed = func.array_remove(check_in.c.tags, key)
        stmt = stmt.on_conflict_do_update(
            index_elements=_KEY,
            set_={
                "tags": case((literal(on), func.array_append(removed, key)), else_=removed),
                "updated_at": func.now(),
            },
        ).returning(*_COLUMNS)
        return await self._one(stmt)

    async def delete(self, account_id: UUID, local_date: date) -> None:
        stmt = delete(check_in).where(
            check_in.c.account_id == account_id, check_in.c.local_date == local_date
        )
        async with connection(self._engine) as conn:
            await conn.execute(stmt)

    async def _one(self, stmt: Any) -> CheckIn | None:
        try:
            async with connection(self._engine) as conn:
                row = (await conn.execute(stmt)).one_or_none()
        except IntegrityError as e:
            if sqlstate(e) == "23514":  # check_violation
                raise InvalidCheckIn("rejected by the database") from e
            raise
        return to_check_in(row) if row else None


def known_tags(keys: Iterable[str]) -> frozenset[CheckInTag]:
    """Stored keys a later release removed are dropped on read (spec §2)."""
    return frozenset(CheckInTag(k) for k in keys if k in CheckInTag._value2member_map_)


def to_check_in(row: Row[*tuple[Any, ...]]) -> CheckIn:
    return CheckIn(
        mood=row.mood, energy=row.energy, effort=row.effort, tags=known_tags(row.tags or ())
    )
