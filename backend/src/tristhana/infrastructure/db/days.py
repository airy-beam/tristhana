"""`DayLogRepository` on Postgres. A ladies' holiday is stored as 'rest' plus a sealed true
status on every rest row (ADR-0016); this adapter is the only place that knows."""

import logging
from datetime import date
from typing import Protocol
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncEngine

from tristhana.domain.days import DayLog, DayStatus, public_status
from tristhana.infrastructure.crypto import UnreadableSeal
from tristhana.infrastructure.db.engine import connection
from tristhana.infrastructure.db.tables import day_log

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
        async with connection(self._engine) as conn:
            await conn.execute(stmt)
        return day

    async def delete(self, account_id: UUID, local_date: date) -> None:
        stmt = delete(day_log).where(
            day_log.c.account_id == account_id, day_log.c.local_date == local_date
        )
        async with connection(self._engine) as conn:
            await conn.execute(stmt)

    async def list_range(self, account_id: UUID, start: date, end: date) -> list[DayLog]:
        stmt = (
            select(day_log.c.local_date, day_log.c.status, day_log.c.sealed_status)
            .where(
                day_log.c.account_id == account_id,
                day_log.c.local_date.between(start, end),
            )
            .order_by(day_log.c.local_date)
        )
        async with connection(self._engine) as conn:
            rows = (await conn.execute(stmt)).all()
        return [
            DayLog(
                row.local_date,
                self._status(account_id, row.local_date, row.status, row.sealed_status),
            )
            for row in rows
        ]

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
