"""`Storage` for the app. Imports SQLAlchemy only in `start()` (cold start: the module is
imported by the composition root, the engine is built in the lifespan under CPU boost)."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, NoReturn
from uuid import UUID

from tristhana.application.ports.accounts import AccountRepository
from tristhana.application.ports.days import DayLogRepository
from tristhana.application.ports.practice import PracticeRepository
from tristhana.application.ports.storage import StorageUnavailable
from tristhana.application.practice_patch import PracticePatch
from tristhana.domain.accounts import IdentityKey, NewAccount, ProfileUpdate
from tristhana.domain.days import DayLog
from tristhana.domain.practice import Practice

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

    from tristhana.infrastructure.db.days import Cipher

log = logging.getLogger(__name__)

WARMUP_TIMEOUT_S = 2.0


class PostgresStorage:
    def __init__(
        self,
        url: str,
        *,
        ca_file: Path | None,
        pool_size: int,
        max_overflow: int,
        cipher: Cipher,
    ) -> None:
        self._url = url
        self._cipher = cipher
        self._ca_file = ca_file
        self._pool_size = pool_size
        self._max_overflow = max_overflow
        self._engine: AsyncEngine | None = None
        self._accounts: AccountRepository | None = None
        self._days: DayLogRepository | None = None
        self._practices: PracticeRepository | None = None

    async def start(self) -> None:
        from tristhana.infrastructure.db.accounts import SqlAccountRepository
        from tristhana.infrastructure.db.days import SqlDayLogRepository
        from tristhana.infrastructure.db.engine import build_engine
        from tristhana.infrastructure.db.practice import SqlPracticeRepository

        self._engine = build_engine(
            self._url,
            ca_file=self._ca_file,
            pool_size=self._pool_size,
            max_overflow=self._max_overflow,
        )
        self._accounts = SqlAccountRepository(self._engine)
        self._days = SqlDayLogRepository(self._engine, self._cipher)
        self._practices = SqlPracticeRepository(self._engine)
        # One warm connection, so the first tap doesn't pay for TCP + TLS + auth.
        started = time.perf_counter()
        try:
            await asyncio.wait_for(self.ping(), WARMUP_TIMEOUT_S)
        except (StorageUnavailable, TimeoutError) as e:
            log.warning("database warm-up failed: %s", type(e).__name__)
        else:
            log.info("database ready in %.0f ms", (time.perf_counter() - started) * 1000)

    async def stop(self) -> None:
        if self._engine is not None:
            await self._engine.dispose()

    async def ping(self) -> None:
        from sqlalchemy import text

        from tristhana.infrastructure.db.engine import connection

        # Touches our schema, so a missing grant (roles.sql not run) fails the health check.
        async with connection(self._require_engine()) as conn:
            await conn.execute(text("SELECT 1 FROM tristhana.account LIMIT 0"))

    @property
    def accounts(self) -> AccountRepository:
        if self._accounts is None:
            raise RuntimeError("storage not started")
        return self._accounts

    @property
    def days(self) -> DayLogRepository:
        if self._days is None:
            raise RuntimeError("storage not started")
        return self._days

    @property
    def practices(self) -> PracticeRepository:
        if self._practices is None:
            raise RuntimeError("storage not started")
        return self._practices

    def _require_engine(self) -> AsyncEngine:
        if self._engine is None:
            raise RuntimeError("storage not started")
        return self._engine


class UnconfiguredStorage:
    """No DATABASE_URL: the app still starts (OpenAPI dump, container smoke test), and every
    DB-backed feature answers "temporarily unavailable"."""

    async def start(self) -> None:
        log.warning("DATABASE_URL is not set: accounts are unavailable")

    async def stop(self) -> None:
        pass

    async def ping(self) -> None:
        raise StorageUnavailable("not configured")

    @property
    def accounts(self) -> AccountRepository:
        return _UnavailableAccounts()

    @property
    def days(self) -> DayLogRepository:
        return _UnavailableDays()

    @property
    def practices(self) -> PracticeRepository:
        return _UnavailablePractices()


class _UnavailableAccounts:
    async def find_by_identity(self, key: IdentityKey) -> NoReturn:
        raise StorageUnavailable("not configured")

    async def create_with_identity(self, key: IdentityKey, new: NewAccount) -> NoReturn:
        raise StorageUnavailable("not configured")

    async def update_profile(
        self, account_id: UUID, changes: ProfileUpdate, seen_at: datetime
    ) -> NoReturn:
        raise StorageUnavailable("not configured")

    async def set_timezone_if_unset(self, account_id: UUID, timezone: str) -> NoReturn:
        raise StorageUnavailable("not configured")


class _UnavailableDays:
    async def upsert(self, account_id: UUID, day: DayLog, timezone: str | None) -> NoReturn:
        raise StorageUnavailable("not configured")

    async def delete(self, account_id: UUID, local_date: date) -> NoReturn:
        raise StorageUnavailable("not configured")

    async def list_range(self, account_id: UUID, start: date, end: date) -> NoReturn:
        raise StorageUnavailable("not configured")


class _UnavailablePractices:
    async def save(self, account_id: UUID, local_date: date, patch: PracticePatch) -> NoReturn:
        raise StorageUnavailable("not configured")

    async def copy_latest(
        self, account_id: UUID, local_date: date, timezone: str | None
    ) -> NoReturn:
        raise StorageUnavailable("not configured")

    async def delete(self, account_id: UUID, local_date: date) -> NoReturn:
        raise StorageUnavailable("not configured")

    async def recent(self, account_id: UUID, before: date, limit: int) -> list[Practice]:
        raise StorageUnavailable("not configured")
