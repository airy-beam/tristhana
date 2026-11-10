"""The directory listing's storage (ID-05, ADR-0042). One row per account. No exception here
carries a name, a region or a note: they must never reach a log."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol
from uuid import UUID

from tristhana.application.ports.notifications import Recipient
from tristhana.domain.directory_listing import Details, Listing, Outcome, Step

PAGE = 10


@dataclass(frozen=True, slots=True)
class Saved:
    listing: Listing
    step: Step


@dataclass(frozen=True, slots=True)
class RequestRow:
    account_id: UUID
    name_as_listed: str
    at: date  # the request's UTC date (waiting), or the last check (listed)


@dataclass(frozen=True, slots=True)
class RequestsPage:
    rows: tuple[RequestRow, ...]
    waiting: int
    listed: int
    oldest_check: date | None


@dataclass(frozen=True, slots=True)
class RequestCard:
    """What the checker reads: the account's display name and the request. Never a Telegram
    id, practice data or students."""

    account_id: UUID
    display_name: str | None
    listing: Listing


@dataclass(frozen=True, slots=True)
class Decided:
    teacher: Recipient | None  # None: no Telegram identity to tell
    name_as_listed: str
    was_listed: bool  # a re-check, not a first answer


class ListingRepository(Protocol):
    async def get(self, me: UUID) -> Listing | None: ...

    async def save(
        self,
        me: UUID,
        details: Details,
        plan: Callable[[Listing | None], Step],
        now: datetime,
    ) -> Saved:
        """One transaction: the row is locked, `plan` decides the step from what is stored
        (its exceptions pass through and nothing is written), then the row is written."""
        ...

    async def withdraw(self, me: UUID) -> None:
        """Clears the details, keeps the timestamps. Idempotent; no row stays no row."""
        ...

    async def recipients(self, accounts: frozenset[UUID]) -> tuple[Recipient, ...]:
        """The Telegram identities of these accounts (the admins' notes)."""
        ...

    async def requests(self, listed: bool, page: int) -> RequestsPage:
        """Waiting rows oldest first, or listed rows oldest check first, plus both counts."""
        ...

    async def request(self, account_id: UUID) -> RequestCard | None: ...

    async def decide(
        self,
        account_id: UUID,
        revision: int,
        outcome: Outcome,
        checked_on: date,
        by: UUID,
    ) -> Decided | None:
        """None: the row changed since the card (another revision), or it can't be decided.
        Clears the note and moves the revision on, so an old button decides nothing."""
        ...
