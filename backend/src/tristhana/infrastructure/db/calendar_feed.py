"""`CalendarFeedRepository` on Postgres (SC-06, ADR-0036). Each method is one statement.

The token is sealed with the field cipher (ADR-0016); the AAD binds it to its account, so a
sealed copy moved to another row doesn't open. The lookup is by the token's SHA-256 (unique)
and loads the account as the account repository does, stamping `fetched_on` in a
data-modifying CTE only when the date changed (a calendar polls many times a day). The token
itself is never logged.
"""

import logging
from datetime import date
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncEngine

from tristhana.application.ports.calendar_feed import FeedLink, FeedOwner
from tristhana.infrastructure.crypto import UnreadableSeal
from tristhana.infrastructure.db.accounts import ACCOUNT_COLUMNS, to_account
from tristhana.infrastructure.db.diary import Cipher
from tristhana.infrastructure.db.engine import connection
from tristhana.infrastructure.db.tables import account, calendar_feed

log = logging.getLogger(__name__)
_F = calendar_feed


def _aad(account_id: UUID) -> bytes:
    return b"calendar_feed.sealed_token|" + account_id.bytes


class SqlCalendarFeedRepository:
    def __init__(self, engine: AsyncEngine, cipher: Cipher) -> None:
        self._engine, self._cipher = engine, cipher

    async def get(self, me: UUID) -> FeedLink | None:
        stmt = select(_F.c.sealed_token, _F.c.created_at, _F.c.fetched_on).where(
            _F.c.account_id == me
        )
        async with connection(self._engine) as conn:
            row = (await conn.execute(stmt)).one_or_none()
        if row is None:
            return None
        try:
            token = self._cipher.open(bytes(row.sealed_token), _aad(me)).decode()
        except (UnreadableSeal, UnicodeDecodeError):
            log.warning("unreadable calendar_feed seal for account %s", me)  # never the token
            return None
        return FeedLink(token, row.created_at, row.fetched_on)

    async def replace(self, me: UUID, token_hash: bytes, token: str) -> FeedLink:
        """Create or rotate: the new hash replaces the old in the same row and statement."""
        sealed = self._cipher.seal(token.encode(), _aad(me))
        stmt = insert(_F).values(account_id=me, token_hash=token_hash, sealed_token=sealed)
        stmt = stmt.on_conflict_do_update(
            index_elements=[_F.c.account_id],
            set_={
                "token_hash": stmt.excluded.token_hash,
                "sealed_token": stmt.excluded.sealed_token,
                "created_at": stmt.excluded.created_at,
                "fetched_on": None,
            },
        ).returning(_F.c.created_at, _F.c.fetched_on)
        async with connection(self._engine) as conn:
            row = (await conn.execute(stmt)).one()
        return FeedLink(token, row.created_at, row.fetched_on)

    async def delete(self, me: UUID) -> None:
        async with connection(self._engine) as conn:
            await conn.execute(delete(_F).where(_F.c.account_id == me))

    async def account_by_token(self, token_hash: bytes, today: date) -> FeedOwner | None:
        touched = (
            update(_F)
            .where(_F.c.token_hash == token_hash, _F.c.fetched_on.is_distinct_from(today))
            .values(fetched_on=today)
            .returning(_F.c.account_id)
            .cte("touched")
        )  # Postgres runs a data-modifying CTE even when nothing reads it
        stmt = (
            select(*ACCOUNT_COLUMNS, _F.c.created_at.label("feed_created_at"))
            .select_from(account.join(_F, _F.c.account_id == account.c.id))
            .where(_F.c.token_hash == token_hash)
            .add_cte(touched)
        )
        async with connection(self._engine) as conn:
            row = (await conn.execute(stmt)).one_or_none()
        if row is None:
            return None
        return FeedOwner(to_account(row), row.feed_created_at)
