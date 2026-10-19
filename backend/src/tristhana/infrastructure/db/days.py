"""`DayLogRepository` on Postgres. A ladies' holiday is stored as 'rest' plus a sealed true
status on every rest row (ADR-0016); this adapter is the only place that knows."""

import logging
from datetime import date
from typing import Protocol
from uuid import UUID

from sqlalchemy import and_, delete, exists, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncEngine

from tristhana.domain.days import DayLog, DayStatus, public_status
from tristhana.infrastructure.crypto import UnreadableSeal
from tristhana.infrastructure.db.engine import connection
from tristhana.infrastructure.db.practice import to_practice
from tristhana.infrastructure.db.tables import day_log, practice

log = logging.getLogger(__name__)

# The sealed payload of a rest row: one byte, so rest and ladies seals have equal length.
_SEALED = {DayStatus.REST: b"r", DayStatus.LADIES: b"l"}
_UNSEALED = {v: k for k, v in _SEALED.items()}


class Cipher(Protocol):
    def seal(self, plaintext: bytes, aad: bytes) -> bytes: ...
    def open(self, sealed: bytes, aad: bytes) -> bytes: ...


def _aad(account_id: UUID, local_date: date) -> bytes:
    return b"day_log.sealed_status|" + account_id.bytes + local_date.isoformat().encode()


class SqlDayLogRepository:
    def __init__(self, engine: AsyncEngine, cipher: Cipher) -> None:
        self._engine = engine
        self._cipher = cipher

    async def upsert(self, account_id: UUID, day: DayLog, timezone: str | None) -> DayLog:
        public = public_status(day.status)
        sealed = (
            self._cipher.seal(_SEALED[day.status], _aad(account_id, day.local_date))
            if public is DayStatus.REST
            else None
        )
        values = {"status": public.value, "sealed_status": sealed, "timezone": timezone}
        stmt = insert(day_log).values(account_id=account_id, local_date=day.local_date, **values)
        stmt = stmt.on_conflict_do_update(
            index_elements=[day_log.c.account_id, day_log.c.local_date],
            set_={**values, "updated_at": func.now()},
        )
        stale = delete(practice).where(
            practice.c.account_id == account_id, practice.c.local_date == day.local_date
        )
        if day.status is DayStatus.PRACTICED:
            # Details left over from a status change racing a save (or an old revision) go
            # when the day becomes practiced again; this snapshot still sees the old status.
            stale = stale.where(
                exists().where(
                    day_log.c.account_id == account_id,
                    day_log.c.local_date == day.local_date,
                    day_log.c.status != "practiced",
                )
            )
        # Same statement: a day that is no longer practiced loses its details (PR-02).
        stmt = stmt.add_cte(stale.cte("gone"))
        async with connection(self._engine) as conn:
            await conn.execute(stmt)
        return day

    async def insert_if_absent(self, account_id: UUID, day: DayLog, timezone: str | None) -> bool:
        if public_status(day.status) is DayStatus.REST:
            raise ValueError("reminder taps only log non-private statuses")  # nothing to seal
        stmt = (
            insert(day_log)
            .values(
                account_id=account_id,
                local_date=day.local_date,
                status=day.status.value,
                timezone=timezone,
            )
            .on_conflict_do_nothing(index_elements=[day_log.c.account_id, day_log.c.local_date])
            .returning(day_log.c.local_date)
        )
        async with connection(self._engine) as conn:
            return (await conn.execute(stmt)).one_or_none() is not None

    async def delete(self, account_id: UUID, local_date: date) -> None:
        stmt = delete(day_log).where(
            day_log.c.account_id == account_id, day_log.c.local_date == local_date
        )
        async with connection(self._engine) as conn:
            await conn.execute(stmt)

    async def list_range(self, account_id: UUID, start: date, end: date) -> list[DayLog]:
        stmt = (
            select(
                day_log.c.local_date,
                day_log.c.status,
                day_log.c.sealed_status,
                practice.c.slot,
                practice.c.context,
                practice.c.online,
                practice.c.series,
                practice.c.end_item,
                practice.c.first_part,
                practice.c.duration_min,
                practice.c.start_time,
                practice.c.timezone,
            )
            .select_from(
                day_log.outerjoin(
                    practice,
                    and_(
                        practice.c.account_id == day_log.c.account_id,
                        practice.c.local_date == day_log.c.local_date,
                        # Also hides a row left by a rare status/details race.
                        day_log.c.status == "practiced",
                    ),
                )
            )
            .where(
                day_log.c.account_id == account_id,
                day_log.c.local_date.between(start, end),
            )
            .order_by(day_log.c.local_date, practice.c.slot)
        )
        async with connection(self._engine) as conn:
            rows = (await conn.execute(stmt)).all()
        days: dict[date, DayLog] = {}
        for row in rows:
            day = days.get(row.local_date) or DayLog(
                row.local_date,
                self._status(account_id, row.local_date, row.status, row.sealed_status),
            )
            if row.slot is not None:
                day = DayLog(day.local_date, day.status, (*day.practices, to_practice(row)))
            days[row.local_date] = day
        return list(days.values())

    def _status(
        self, account_id: UUID, local_date: date, status: str, sealed: bytes | None
    ) -> DayStatus:
        if sealed is None:
            return DayStatus(status)
        try:
            return _UNSEALED.get(
                self._cipher.open(sealed, _aad(account_id, local_date)), DayStatus.REST
            )
        except UnreadableSeal:
            # Lost or retired key: only the rest/ladies distinction is lost, never the day.
            log.warning("unreadable day_log seal for account %s", account_id)
            return DayStatus.REST
