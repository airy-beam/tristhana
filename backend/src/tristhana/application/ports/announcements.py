"""Announcements (NT-03, ADR-0038). Every write reads the caller's right in the same statement;
the SQL guard mirrors `application/policies.py`. The text is broadcast, not sealed (Q174)."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from tristhana.domain.announcements import Source
from tristhana.domain.locale import Locale
from tristhana.domain.notifications import QuietHours
from tristhana.domain.shalas import Membership


@dataclass(frozen=True, slots=True)
class NewAnnouncement:
    author_id: UUID
    source: Source  # a teacher source is always the author's own
    text: str  # normalized
    pinned_until: datetime | None
    since: datetime  # the rate window's start
    limit: int


@dataclass(frozen=True, slots=True)
class SentItem:
    """The author's view: `audience` is the size at send time, muted people included."""

    id: UUID
    source: Source
    shala_name: str | None  # None for a teacher source
    text: str
    created_at: datetime
    pinned_until: datetime | None
    audience: int


@dataclass(frozen=True, slots=True)
class Posted:
    """`me` is the caller's shala membership (None for a teacher source, or not a member).
    `allowed` is the SQL guard (mirrors `can_announce_to_shala`), `limited` the rate limit;
    `item` None with both passing = no one to send it to. Nothing is written unless `item`."""

    me: Membership | None
    allowed: bool
    limited: bool
    item: SentItem | None


@dataclass(frozen=True, slots=True)
class FeedItem:
    id: UUID
    source: Source
    source_name: str | None  # the shala's name, or the teacher's display name
    author_name: str | None  # None once the author is no longer the teacher or on staff
    text: str
    created_at: datetime
    pinned_until: datetime | None
    can_manage: bool  # the author, or a shala owner/manager (moderation)


@dataclass(frozen=True, slots=True)
class FeedSource:
    source: Source
    name: str | None
    muted: bool


@dataclass(frozen=True, slots=True)
class Feed:
    """The caller's current sources and their items (pins first, then newest first)."""

    items: tuple[FeedItem, ...]
    sources: tuple[FeedSource, ...]
    more: bool = False


@dataclass(frozen=True, slots=True)
class Managed:
    """`found` False: no such item, or not one the caller may see (as not existing).
    `allowed` mirrors `can_manage_announcement`; the write happened only when allowed."""

    found: bool
    allowed: bool
    item: SentItem | None = None
    author_id: UUID | None = None  # set when found, for the policy re-check
    me: Membership | None = None  # the caller's membership of the item's shala
    shala: bool = False  # a shala's item (else a teacher's)


@dataclass(frozen=True, slots=True)
class DueAnnouncement:
    """One recipient of one announcement, from the live audience."""

    id: UUID
    source: Source
    source_name: str | None
    author_name: str | None
    text: str
    created_at: datetime
    account_id: UUID
    telegram_id: str
    locale: Locale
    zone: str | None  # None: no known zone (sent at once, silently)
    quiet: QuietHours


class AnnouncementRepository(Protocol):
    async def create(self, new: NewAnnouncement) -> Posted:
        """One statement: the guard, the rate limit (rows of this source since `since`),
        the live audience count (the author excluded), the earlier pin cleared when this one
        pins, and the insert."""
        ...

    async def feed(
        self,
        me: UUID,
        source: Source | None,
        since: datetime,
        now: datetime,
        offset: int,
        limit: int,
    ) -> Feed | None:
        """The caller's current sources' items created since `since`, plus live pins.
        None: `source` is not one of the caller's."""
        ...

    async def sent(self, me: UUID, since: datetime) -> tuple[SentItem, ...]:
        """The caller's own, newest first."""
        ...

    async def set_pin(self, me: UUID, id: UUID, pinned_until: datetime | None) -> Managed:
        """Pinning clears the source's other pin in the same statement."""
        ...

    async def delete(self, me: UUID, id: UUID) -> Managed:
        """A hard delete; gone already = found False (the use case treats it as done)."""
        ...

    async def set_mute(self, me: UUID, source: Source, muted: bool) -> bool:
        """False: not the caller's teacher or shala."""
        ...

    async def due(self, since: datetime, now: datetime, limit: int) -> list[DueAnnouncement]:
        """One statement: announcements created after `since`, joined to their live audience
        who were in it when it was sent, not muted, with the global switch on, reachable on
        Telegram, and not yet delivered (final ledger rows). Ordered by (created_at, account)."""
        ...

    async def prune(self, before: datetime) -> int: ...
