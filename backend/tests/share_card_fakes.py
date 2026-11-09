"""ST-07 fakes: an in-memory share-card store that behaves like the SQL (rate limit at
insert, expiry on read, one send per card), a spy renderer and fixed tokens."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from tristhana.application.ports.share_cards import NewShareCard, SendClaim
from tristhana.domain.locale import Locale
from tristhana.domain.share_cards import Card, CardFormat


@dataclass
class _Row:
    card: NewShareCard
    created_at: datetime
    sent: bool = False


@dataclass
class InMemoryShareCards:
    now: datetime = field(default_factory=lambda: datetime.now(UTC))
    accounts: Any = None  # InMemoryAccounts: Telegram ids from its identities
    rows: dict[bytes, _Row] = field(default_factory=dict[bytes, _Row])
    milestones: set[tuple[UUID, int]] = field(default_factory=set[tuple[UUID, int]])
    telegram: dict[UUID, str] = field(default_factory=dict[UUID, str])
    released: list[bytes] = field(default_factory=list[bytes])

    async def insert(self, card: NewShareCard, since: datetime, limit: int) -> bool:
        recent = sum(
            1
            for r in self.rows.values()
            if r.card.account_id == card.account_id and r.created_at > since
        )
        if recent >= limit:
            return False
        self.rows[card.token_hash] = _Row(card, self.now)
        return True

    async def recent(self, account_id: UUID, since: datetime) -> int:
        mine = [r for r in self.rows.values() if r.card.account_id == account_id]
        return sum(1 for r in mine if r.created_at > since)

    async def image(self, token_hash: bytes, now: datetime) -> bytes | None:
        row = self.rows.get(token_hash)
        return row.card.png if row is not None and row.card.expires_at > now else None

    async def claim_send(self, account_id: UUID, token_hash: bytes, now: datetime) -> SendClaim:
        row = self.rows.get(token_hash)
        if row is None or row.card.account_id != account_id or row.card.expires_at <= now:
            return SendClaim(found=False)
        if row.sent:
            return SendClaim(found=True)
        row.sent = True
        return SendClaim(True, row.card.png, self._telegram(account_id))

    def _telegram(self, account_id: UUID) -> str | None:
        if account_id in self.telegram:
            return self.telegram[account_id]
        identities: dict[Any, UUID] = getattr(self.accounts, "identities", {})
        return next((k.provider_user_id for k, a in identities.items() if a == account_id), None)

    async def release_send(self, account_id: UUID, token_hash: bytes) -> None:
        self.released.append(token_hash)
        row = self.rows.get(token_hash)
        if row is not None and row.card.account_id == account_id:
            row.sent = False

    async def milestone_seen(self, account_id: UUID, threshold: int) -> bool:
        return (account_id, threshold) in self.milestones

    async def prune(self, now: datetime) -> int:
        gone = [h for h, r in self.rows.items() if r.card.expires_at <= now]
        for h in gone:
            del self.rows[h]
        return len(gone)


@dataclass
class SpyRenderer:
    calls: list[tuple[Card, CardFormat, Locale]] = field(
        default_factory=list[tuple[Card, CardFormat, Locale]]
    )

    async def render(self, card: Card, format: CardFormat, locale: Locale) -> bytes:
        self.calls.append((card, format, locale))
        return b"\x89PNG fake " + format.value.encode()


@dataclass
class CountingTokens:
    n: int = 0

    def new(self) -> str:
        self.n += 1
        return f"tok{self.n:019d}"  # 22 URL-safe characters
