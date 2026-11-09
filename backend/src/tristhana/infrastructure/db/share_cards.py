"""`ShareCardRepository` on Postgres (ST-07, ADR-0040). Each method is one statement.

Rows are keyed by the SHA-256 of the card's token; the token itself is never stored or
logged. The rate limit is checked inside the insert (`INSERT … SELECT … WHERE count < n`),
and the one "Send to my chat" is a conditional update that re-checks `sent_at` on the row,
so two taps can't both send.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, delete, exists, func, literal, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncEngine

from tristhana.application.ports.share_cards import NewShareCard, SendClaim
from tristhana.domain.accounts import IdentityProvider
from tristhana.infrastructure.db.engine import connection
from tristhana.infrastructure.db.tables import identity, practice_milestone, share_card

_S = share_card


class SqlShareCardRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def insert(self, card: NewShareCard, since: datetime, limit: int) -> bool:
        recent = (
            select(func.count())
            .select_from(_S)
            .where(_S.c.account_id == card.account_id, _S.c.created_at > since)
            .scalar_subquery()
        )
        values = select(
            literal(card.token_hash).label("token_hash"),
            literal(card.account_id).label("account_id"),
            literal(card.kind).label("kind"),
            literal(card.format.value).label("format"),
            literal(card.png).label("png"),
            literal(card.expires_at).label("expires_at"),
        ).where(recent < limit)
        stmt = (
            insert(_S)
            .from_select(
                ["token_hash", "account_id", "kind", "format", "png", "expires_at"], values
            )
            .returning(_S.c.token_hash)
        )
        async with connection(self._engine) as conn:
            return (await conn.execute(stmt)).first() is not None

    async def recent(self, account_id: UUID, since: datetime) -> int:
        stmt = (
            select(func.count())
            .select_from(_S)
            .where(_S.c.account_id == account_id, _S.c.created_at > since)
        )
        async with connection(self._engine) as conn:
            return int((await conn.execute(stmt)).scalar_one())

    async def image(self, token_hash: bytes, now: datetime) -> bytes | None:
        stmt = select(_S.c.png).where(_S.c.token_hash == token_hash, _S.c.expires_at > now)
        async with connection(self._engine) as conn:
            png = (await conn.execute(stmt)).scalar_one_or_none()
        return bytes(png) if png is not None else None

    async def claim_send(self, account_id: UUID, token_hash: bytes, now: datetime) -> SendClaim:
        mine = and_(
            _S.c.token_hash == token_hash, _S.c.account_id == account_id, _S.c.expires_at > now
        )
        claimed = (
            update(_S)
            .where(mine, _S.c.sent_at.is_(None))  # re-checked on the locked row
            .values(sent_at=now)
            .returning(_S.c.png)
            .cte("claimed")
        )
        telegram = (
            select(identity.c.provider_user_id)
            .where(
                identity.c.account_id == account_id,
                identity.c.provider == IdentityProvider.TELEGRAM.value,
            )
            .limit(1)
            .scalar_subquery()
        )
        stmt = select(
            exists().where(mine).label("found"),
            select(claimed.c.png).scalar_subquery().label("png"),
            telegram.label("telegram_id"),
        )
        async with connection(self._engine) as conn:
            row = (await conn.execute(stmt)).one()
        png = bytes(row.png) if row.png is not None else None
        return SendClaim(bool(row.found) or png is not None, png, row.telegram_id)

    async def release_send(self, account_id: UUID, token_hash: bytes) -> None:
        stmt = (
            update(_S)
            .where(_S.c.token_hash == token_hash, _S.c.account_id == account_id)
            .values(sent_at=None)
        )
        async with connection(self._engine) as conn:
            await conn.execute(stmt)

    async def milestone_seen(self, account_id: UUID, threshold: int) -> bool:
        stmt = select(
            exists().where(
                practice_milestone.c.account_id == account_id,
                practice_milestone.c.threshold == threshold,
            )
        )
        async with connection(self._engine) as conn:
            return bool((await conn.execute(stmt)).scalar())

    async def prune(self, now: datetime) -> int:
        stmt = delete(_S).where(_S.c.expires_at <= now)
        async with connection(self._engine) as conn:
            return (await conn.execute(stmt)).rowcount
