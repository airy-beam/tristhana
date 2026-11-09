"""Announcements from a teacher to their students, or to a shala (NT-03, ADR-0038). The API
uses all of these; the bot uses the feed and the mute (composing is in the Mini App, Q176).

Sending writes one row in one guarded statement and calls nothing outside: the tick delivers
it (`RunTick`) from the live audience. Built with the announcement port and a clock only, so
no log, diary or check-in is in reach. Non-members get `NotFound`, never `NotAllowed`.
"""

from dataclasses import dataclass
from uuid import UUID

from tristhana.application.policies import (
    NotAllowed,
    NotFound,
    Principal,
    can_announce_to_shala,
    can_announce_to_students,
    can_manage_announcement,
    can_pin_announcement,
)
from tristhana.application.ports.announcements import (
    AnnouncementRepository,
    Feed,
    Managed,
    NewAnnouncement,
    SentItem,
)
from tristhana.application.ports.storage import Clock
from tristhana.domain.accounts import Account
from tristhana.domain.announcements import (
    FEED_WINDOW,
    PER_SOURCE_PER_DAY,
    RATE_WINDOW,
    AnnouncementLimit,
    InvalidAnnouncement,
    Source,
    SourceKind,
    normalize_text,
    pin_until,
)

FEED_PAGE_MAX = 20


@dataclass(frozen=True, slots=True)
class Target:
    """What the sender picks: their students (None), or one shala."""

    shala_id: UUID | None = None


class SendAnnouncement:
    def __init__(self, repo: AnnouncementRepository, clock: Clock) -> None:
        self._repo = repo
        self._clock = clock

    async def execute(
        self, principal: Principal, target: Target, raw_text: str, pin_days: int
    ) -> SentItem:
        """Raises `InvalidAnnouncement` (text, pin length, no one to send to), `NotFound`
        (not a member of the shala), `NotAllowed` (a member without the role) or
        `AnnouncementLimit`. Nothing is sent here: the tick delivers it."""
        me = principal.account
        text = normalize_text(raw_text)
        if text is None:
            raise InvalidAnnouncement("blank or too long")
        now = self._clock.now()
        pinned_until = pin_until(now, pin_days)
        if target.shala_id is None:
            source = Source(SourceKind.TEACHER, me.id)
            if not can_announce_to_students(me, source.id):  # always: the caller's own
                raise NotAllowed
        else:
            source = Source(SourceKind.SHALA, target.shala_id)
        posted = await self._repo.create(
            NewAnnouncement(
                author_id=me.id,
                source=source,
                text=text,
                pinned_until=pinned_until,
                since=now - RATE_WINDOW,
                limit=PER_SOURCE_PER_DAY,
            )
        )
        if source.kind is SourceKind.SHALA:
            if posted.me is None:
                raise NotFound
            # The SQL guard first, the policy second: both must agree.
            if not posted.allowed or not can_announce_to_shala(posted.me):
                raise NotAllowed
        if posted.limited:
            raise AnnouncementLimit
        if posted.item is None:
            raise InvalidAnnouncement("no one to send it to")
        return posted.item


class GetAnnouncements:
    def __init__(self, repo: AnnouncementRepository, clock: Clock) -> None:
        self._repo = repo
        self._clock = clock

    async def execute(
        self, principal: Principal, source: Source | None = None, offset: int = 0, limit: int = 5
    ) -> Feed:
        """The caller's current sources: the last 30 days plus live pins (Q171). Raises
        `NotFound` for a source that isn't the caller's."""
        now = self._clock.now()
        limit = max(1, min(limit, FEED_PAGE_MAX))
        feed = await self._repo.feed(
            principal.account.id, source, now - FEED_WINDOW, now, max(0, offset), limit
        )
        if feed is None:
            raise NotFound
        return feed


class GetSentAnnouncements:
    def __init__(self, repo: AnnouncementRepository, clock: Clock) -> None:
        self._repo = repo
        self._clock = clock

    async def execute(self, principal: Principal) -> tuple[SentItem, ...]:
        return await self._repo.sent(principal.account.id, self._clock.now() - FEED_WINDOW)


def _allowed(managed: Managed, actor: Account, *, pin: bool) -> bool:
    """The SQL guard first, the policy second: both must agree."""
    if not managed.allowed or managed.author_id is None:
        return False
    if pin:
        return can_pin_announcement(actor, managed.author_id, managed.shala, managed.me)
    return can_manage_announcement(actor, managed.author_id, managed.me)


def _managed(managed: Managed, actor: Account) -> SentItem | None:
    if not managed.found:
        raise NotFound
    if not _allowed(managed, actor, pin=True):
        raise NotAllowed
    return managed.item


class PinAnnouncement:
    def __init__(self, repo: AnnouncementRepository, clock: Clock) -> None:
        self._repo = repo
        self._clock = clock

    async def execute(self, principal: Principal, id: UUID, days: int) -> SentItem:
        """0 unpins. Raises `InvalidAnnouncement`, `NotFound` or `NotAllowed`."""
        until = pin_until(self._clock.now(), days)
        managed = await self._repo.set_pin(principal.account.id, id, until)
        item = _managed(managed, principal.account)
        if item is None:  # deleted in the same instant
            raise NotFound
        return item


class DeleteAnnouncement:
    def __init__(self, repo: AnnouncementRepository) -> None:
        self._repo = repo

    async def execute(self, principal: Principal, id: UUID) -> None:
        """Idempotent: gone already is done. Raises `NotAllowed` for someone else's item the
        caller can see but not manage. Messages already delivered stay in people's chats."""
        managed = await self._repo.delete(principal.account.id, id)
        if managed.found and not _allowed(managed, principal.account, pin=False):
            raise NotAllowed


class MuteAnnouncements:
    def __init__(self, repo: AnnouncementRepository) -> None:
        self._repo = repo

    async def execute(self, principal: Principal, source: Source, muted: bool) -> None:
        """Push only: the feed still shows them, and the sender is never told (Q167).
        Keyed on the caller, so a forged id matches nothing (`NotFound`)."""
        if not await self._repo.set_mute(principal.account.id, source, muted):
            raise NotFound


@dataclass(frozen=True, slots=True)
class AnnouncementUseCases:
    send: SendAnnouncement
    feed: GetAnnouncements
    sent: GetSentAnnouncements
    pin: PinAnnouncement
    delete: DeleteAnnouncement
    mute: MuteAnnouncements
