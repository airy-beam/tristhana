"""In-memory `CalendarFeedRepository` and `TokenSource` (SC-06 spec §3, §6; ADR-0036).
`InMemoryStorage.calendar_feed` loads it on first use, so the other suites keep collecting
before SC-06 exists.

The port shapes the spec leaves open are assumed here, and are the ones to adjust with the port
(`tristhana.application.ports.calendar_feed`):

- `FeedLink(token, created_at, fetched_on)`: what `get` and `replace` return (the token
  unsealed);
- `FeedOwner(account, created_at)`: what `account_by_token(token_hash, today)` returns. The
  spec writes `-> Account | None`, but `Feed.stamp` is the link's `created_at` and the poll is
  two statements, so the same statement must return it;
- `token_hash` is `hashlib.sha256(token.encode()).digest()` (32 bytes, the CHECK of 0023).

Rows are keyed by account (one link per account, Q149). `replace` is the create-or-rotate
upsert (the old hash stops matching at once); a row whose account is gone never matches (the
cascade of ST-09); `account_by_token` writes `fetched_on` only when it differs from `today`.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any
from uuid import UUID

from tests.fakes import InMemoryAccounts


@dataclass
class FeedRow:
    token_hash: bytes
    token: str  # the sealed copy, in clear here (sealing is the SQL adapter's)
    created_at: datetime
    fetched_on: date | None = None


@dataclass
class InMemoryCalendarFeed:
    accounts: InMemoryAccounts
    rows: dict[UUID, FeedRow] = field(default_factory=dict[UUID, FeedRow])
    calls: list[str] = field(default_factory=list[str])  # every port call, in order
    fetch_writes: int = 0  # `fetched_on` writes by `account_by_token`

    async def get(self, me: UUID) -> Any:
        from tristhana.application.ports.calendar_feed import FeedLink

        self.calls.append("get")
        row = self._live(me)
        return None if row is None else FeedLink(row.token, row.created_at, row.fetched_on)

    async def replace(self, me: UUID, token_hash: bytes, token: str) -> Any:
        from tristhana.application.ports.calendar_feed import FeedLink

        self.calls.append("replace")
        assert len(token_hash) == 32, "the CHECK (length = 32)"
        assert all(r.token_hash != token_hash for a, r in self.rows.items() if a != me), "UNIQUE"
        row = FeedRow(token_hash, token, self.accounts.clock.now())
        self.rows[me] = row
        return FeedLink(row.token, row.created_at, row.fetched_on)

    async def delete(self, me: UUID) -> None:
        self.calls.append("delete")
        self.rows.pop(me, None)

    async def account_by_token(self, token_hash: bytes, today: date) -> Any:
        from tristhana.application.ports.calendar_feed import FeedOwner

        self.calls.append("account_by_token")
        found = next((a for a, r in self.rows.items() if r.token_hash == token_hash), None)
        if found is None or self._live(found) is None:
            return None
        row = self.rows[found]
        if row.fetched_on != today:
            row.fetched_on = today
            self.fetch_writes += 1
        account = self.accounts.accounts[found]
        inputs = getattr(self.accounts, "inputs", None)  # MD-02's inputs, as the account load
        return FeedOwner(inputs(account) if inputs else account, row.created_at)

    # Seeding and internals (not part of the port).

    def token_of(self, me: UUID) -> str | None:
        row = self._live(me)
        return None if row is None else row.token

    def _live(self, me: UUID) -> FeedRow | None:
        if me not in self.accounts.accounts:  # ON DELETE CASCADE
            self.rows.pop(me, None)
            return None
        return self.rows.get(me)


@dataclass
class FixedTokens:
    """`TokenSource`: hands out the given tokens in order (43 base64url characters each)."""

    tokens: list[str]
    issued: int = 0

    def new(self) -> str:
        token = self.tokens[self.issued]
        self.issued += 1
        return token
