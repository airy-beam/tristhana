"""The calendar feed's link (SC-06, ADR-0036). Every call is one statement.

The token is a capability: stored as its SHA-256 (the lookup key) and a sealed copy (ADR-0016,
so the link can be shown again). One link per account; `replace` creates or rotates it (the
old hash stops matching in the same statement); `delete` turns it off. A row goes with its
account (ON DELETE CASCADE).
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol
from uuid import UUID

from tristhana.domain.accounts import Account


@dataclass(frozen=True, slots=True)
class FeedLink:
    token: str
    created_at: datetime
    fetched_on: date | None  # the UTC date a calendar last fetched it (Q156)


@dataclass(frozen=True, slots=True)
class FeedOwner:
    """What a poll's lookup returns: the account (loaded as for a principal) and the link's
    creation, the feed's stable `DTSTAMP`."""

    account: Account
    created_at: datetime


class CalendarFeedRepository(Protocol):
    async def get(self, me: UUID) -> FeedLink | None: ...

    async def replace(self, me: UUID, token_hash: bytes, token: str) -> FeedLink: ...

    async def delete(self, me: UUID) -> None:
        """Idempotent."""
        ...

    async def account_by_token(self, token_hash: bytes, today: date) -> FeedOwner | None:
        """The owner of the link, writing `fetched_on = today` when it differs (≤ once a day)."""
        ...


class TokenSource(Protocol):
    def new(self) -> str:
        """43 base64url characters (256 bits)."""
        ...
