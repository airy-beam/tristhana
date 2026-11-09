"""Shareable cards (ST-07, ADR-0040): build a public card from the caller's own data,
render it once, keep the PNG for 24 h behind a capability URL, and send it to the caller's
own chat on request.

Privacy: every day is projected to two tones (`card_tone`) here, before a domain builder
runs, so the renderer never sees a status (Q209). Moon rings come from the account's own
effective calendar (MD-02 via `GetYearStats`), never computed or defaulted here.
"""

import hashlib
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from tristhana.application.policies import Principal
from tristhana.application.ports.notifications import DeliveryStatus, Notifier, Recipient
from tristhana.application.ports.progression import ProgressionRepository
from tristhana.application.ports.share_cards import (
    CardRenderer,
    NewShareCard,
    ShareCardRepository,
    ShareTokens,
)
from tristhana.application.ports.storage import Clock
from tristhana.application.stats import GetYearStats, InvalidYear, YearStatsView
from tristhana.domain.progression import Track
from tristhana.domain.share_cards import (
    Card,
    CardFormat,
    asana_card,
    card_tone,
    count_card,
    is_empty,
    month_card,
    year_card,
)

KEEP = timedelta(hours=24)  # Q205
DAILY_LIMIT = 50  # cards per person per rolling 24 h (Q205)
TOKEN_RE = re.compile(r"[A-Za-z0-9_-]{22}")


class CardNotFound(Exception):
    """Not the caller's, not shareable (a start, a correction, an item), unknown or expired."""


class InvalidPeriod(ValueError):
    """A month or year in the future, before 2000, or not a month."""


class NothingToShare(Exception):
    """No practice in that period."""


class RateLimited(Exception):
    pass


class AlreadySent(Exception):
    pass


class BotUnreachable(Exception):
    """The person blocked the bot, never started it, or has no Telegram identity."""


class SendFailed(Exception):
    """A transient Telegram failure: the send is given back, so a retry works."""


@dataclass(frozen=True, slots=True)
class MonthSubject:
    year: int
    month: int


@dataclass(frozen=True, slots=True)
class YearSubject:
    year: int


@dataclass(frozen=True, slots=True)
class AsanaSubject:
    event_id: int


@dataclass(frozen=True, slots=True)
class CountSubject:
    count: int


type Subject = MonthSubject | YearSubject | AsanaSubject | CountSubject


@dataclass(frozen=True, slots=True)
class CreatedCard:
    token: str
    width: int
    height: int
    file_name: str
    expires_at: datetime


def card_token_hash(token: str) -> bytes:
    return hashlib.sha256(token.encode()).digest()


def _kind(subject: Subject) -> str:
    match subject:
        case MonthSubject():
            return "month"
        case YearSubject():
            return "year"
        case AsanaSubject():
            return "asana"
        case CountSubject():
            return "count"


def _file_name(subject: Subject, format: CardFormat) -> str:
    match subject:
        case MonthSubject(year, month):
            name = f"{year}-{month:02d}"
        case YearSubject(year):
            name = str(year)
        case AsanaSubject():
            name = "asana"
        case CountSubject(count):
            name = str(count)
    return f"tristhana-{name}-{format.value}.png"


class CreateShareCard:
    def __init__(
        self,
        stats: GetYearStats,
        progression: ProgressionRepository,
        cards: ShareCardRepository,
        renderer: CardRenderer,
        tokens: ShareTokens,
        track: Track,
        clock: Clock,
    ) -> None:
        self._stats, self._progression, self._cards = stats, progression, cards
        self._renderer, self._tokens, self._track, self._clock = renderer, tokens, track, clock

    async def execute(
        self, principal: Principal, subject: Subject, format: CardFormat
    ) -> CreatedCard:
        """Raises `InvalidPeriod`, `CardNotFound`, `NothingToShare`, `RateLimited`."""
        since = self._clock.now() - KEEP
        if await self._cards.recent(principal.account.id, since) >= DAILY_LIMIT:
            raise RateLimited  # before the render: a runaway client costs one read
        card = await self._card(principal, subject)
        if is_empty(card):
            raise NothingToShare
        png = await self._renderer.render(card, format, principal.account.locale)
        token = self._tokens.new()
        now = self._clock.now()
        expires_at = now + KEEP
        stored = await self._cards.insert(
            NewShareCard(
                principal.account.id,
                card_token_hash(token),
                _kind(subject),
                format,
                png,
                expires_at,
            ),
            now - KEEP,
            DAILY_LIMIT,
        )
        if not stored:
            raise RateLimited
        width, height = format.size
        return CreatedCard(token, width, height, _file_name(subject, format), expires_at)

    async def _card(self, principal: Principal, subject: Subject) -> Card:
        match subject:
            case MonthSubject(year, month):
                if not 1 <= month <= 12:
                    raise InvalidPeriod
                view = await self._year(principal, year)
                if (year, month) > (view.today.year, view.today.month):
                    raise InvalidPeriod
                first = date(year, month, 1)
                start = (first - date(year, 1, 1)).days
                end = _month_end(year, month)
                cells = view.stats.cells[start : start + (end - first).days + 1]
                return month_card(
                    year,
                    month,
                    view.today,
                    [card_tone(c) for c in cells],
                    [d.date for d in view.moon_days],
                    view.stats.months[month - 1],
                )
            case YearSubject(year):
                view = await self._year(principal, year)
                return year_card(
                    year,
                    view.today,
                    [card_tone(c) for c in view.stats.cells],
                    [d.date for d in view.moon_days],
                    view.stats.year_total.practiced,
                )
            case AsanaSubject(event_id):
                found = await self._progression.get(principal.account.id)
                event = next((e for e in found.events if e.id == event_id), None)
                card = asana_card(self._track, event) if event is not None else None
                if card is None:
                    raise CardNotFound
                return card
            case CountSubject(count):
                seen = await self._cards.milestone_seen(principal.account.id, count)
                card = count_card(count, seen)
                if card is None:
                    raise CardNotFound
                return card

    async def _year(self, principal: Principal, year: int) -> YearStatsView:
        try:
            return await self._stats.execute(principal, year)
        except InvalidYear:
            raise InvalidPeriod from None


def _month_end(year: int, month: int) -> date:
    following = date(year + month // 12, month % 12 + 1, 1)
    return following - timedelta(days=1)


class GetShareCardImage:
    """The capability read: no principal, the token is the access (ADR-0040)."""

    def __init__(self, cards: ShareCardRepository, clock: Clock) -> None:
        self._cards, self._clock = cards, clock

    async def execute(self, token: str) -> bytes | None:
        if TOKEN_RE.fullmatch(token) is None:
            return None  # malformed: no read
        return await self._cards.image(card_token_hash(token), self._clock.now())


class SendShareCard:
    """The card as a photo in the caller's own chat, once per card (Q205)."""

    def __init__(self, cards: ShareCardRepository, notifier: Notifier, clock: Clock) -> None:
        self._cards, self._notifier, self._clock = cards, notifier, clock

    async def execute(self, principal: Principal, token: str) -> None:
        """Raises `CardNotFound`, `AlreadySent`, `BotUnreachable`, `SendFailed`."""
        if TOKEN_RE.fullmatch(token) is None:
            raise CardNotFound
        me, hashed = principal.account.id, card_token_hash(token)
        claim = await self._cards.claim_send(me, hashed, self._clock.now())
        if not claim.found:
            raise CardNotFound
        if claim.png is None:
            raise AlreadySent
        if claim.telegram_id is None:
            await self._cards.release_send(me, hashed)
            raise BotUnreachable
        result = await self._notifier.send_card_photo(
            Recipient(claim.telegram_id, principal.account.locale), claim.png
        )
        if result.status is DeliveryStatus.SENT:
            return
        await self._cards.release_send(me, hashed)
        if result.status is DeliveryStatus.BLOCKED:
            raise BotUnreachable
        raise SendFailed


@dataclass(frozen=True, slots=True)
class ShareCardUseCases:
    create: CreateShareCard
    image: GetShareCardImage
    send: SendShareCard
    public_url: str | None  # PUBLIC_API_URL; None = the feature is off (no links to give)

    @property
    def available(self) -> bool:
        return bool(self.public_url)

    def image_url(self, token: str) -> str:
        return f"{(self.public_url or '').rstrip('/')}/share/v1/{token}.png"
