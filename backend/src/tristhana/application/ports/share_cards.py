"""Ports for shareable cards (ST-07, ADR-0040)."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from tristhana.domain.locale import Locale
from tristhana.domain.share_cards import Card, CardFormat


@dataclass(frozen=True, slots=True)
class NewShareCard:
    account_id: UUID
    token_hash: bytes  # SHA-256 of the capability token; the token itself is never stored
    kind: str
    format: CardFormat
    png: bytes
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class SendClaim:
    """`png` and `telegram_id` are set only when this call took the one send."""

    found: bool
    png: bytes | None = None
    telegram_id: str | None = None


class ShareCardRepository(Protocol):
    """One statement per method."""

    async def insert(self, card: NewShareCard, since: datetime, limit: int) -> bool:
        """Store the card unless the account made `limit` cards since `since` (the check is
        in the same statement). False = rate limited. A soft limit: taps racing each other
        can each pass the count (READ COMMITTED), so it may overshoot by a few; it exists
        to stop a runaway client, not to count exactly (ADR-0040)."""
        ...

    async def recent(self, account_id: UUID, since: datetime) -> int:
        """Cards the account made since `since`: a cheap check before rendering."""
        ...

    async def image(self, token_hash: bytes, now: datetime) -> bytes | None:
        """The PNG while it hasn't expired; None otherwise (unknown and expired alike)."""
        ...

    async def claim_send(self, account_id: UUID, token_hash: bytes, now: datetime) -> SendClaim:
        """Take the card's one "Send to my chat" (sets `sent_at`) and read the PNG with the
        owner's Telegram id. `found` is False for someone else's, an unknown or an expired
        card; found with no `png` = already sent."""
        ...

    async def release_send(self, account_id: UUID, token_hash: bytes) -> None:
        """Give the send back after a failed delivery, so a retry works."""
        ...

    async def milestone_seen(self, account_id: UUID, threshold: int) -> bool:
        """Whether the GM-01 ledger holds this practice count for the account."""
        ...

    async def prune(self, now: datetime) -> int:
        """Delete expired cards (the tick)."""
        ...


class CardRenderer(Protocol):
    async def render(self, card: Card, format: CardFormat, locale: Locale) -> bytes:
        """A PNG of exactly `format.size`. Draws only what the card holds."""
        ...


class ShareTokens(Protocol):
    def new(self) -> str:
        """A fresh unguessable URL-safe token (128 bits)."""
        ...
