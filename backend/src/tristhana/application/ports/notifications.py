from dataclasses import dataclass
from datetime import date, datetime, time
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from tristhana.domain.locale import Locale
from tristhana.domain.moon import City, MoonDay
from tristhana.domain.notifications import NotificationSettings, PracticeReminders, StoredSettings


@dataclass(frozen=True, slots=True)
class Delivery:
    key: str
    local_date: date
    final: bool  # sent/blocked, a fresh claim, or failed for good: never retried
    counts_today: bool = True  # toward the daily cap: sent or in flight, not failed


@dataclass(frozen=True, slots=True)
class ReminderCandidate:
    """An account that may get reminders (zone known, moon or practice on, reachable)."""

    account_id: UUID
    telegram_id: str
    locale: Locale
    zone: str
    location: str | None  # None = the default city
    settings: NotificationSettings
    deliveries: tuple[Delivery, ...]  # recent ones, for dedupe and the daily cap
    had_moon_reminder: bool  # False: the next one carries the intro
    logged: frozenset[date] = frozenset()  # logged days in the window (practice skips them)
    paused: frozenset[date] = frozenset()  # unlogged days covered by a rest period (WH-01)


@dataclass(frozen=True, slots=True)
class MoonPatch:
    """Moon-reminder fields to change; None = keep."""

    offsets: frozenset[int] | None = None
    at: time | None = None


@dataclass(frozen=True, slots=True)
class ReminderPatch:
    """Practice-reminder fields to change; None = keep."""

    on: bool | None = None
    at: time | None = None

    def apply(self, current: PracticeReminders) -> PracticeReminders:
        return PracticeReminders(
            self.on if self.on is not None else current.on, self.at or current.at, current.days
        )


@dataclass(frozen=True, slots=True)
class PracticePause:
    """The rest period covering today (WH-01): practice reminders skip [start, until]."""

    start: date
    until: date


class NotificationRepository(Protocol):
    async def settings(
        self, account_id: UUID, defaults: NotificationSettings
    ) -> NotificationSettings: ...

    async def settings_with_pause(
        self, account_id: UUID, defaults: NotificationSettings, today: date
    ) -> tuple[NotificationSettings, PracticePause | None]:
        """`settings` plus the rest period covering `today`, in one statement (WH-01)."""
        ...

    async def save(
        self, account_id: UUID, settings: NotificationSettings, with_practice: bool = True
    ) -> NotificationSettings:
        """Replace the settings; `with_practice=False` leaves the practice columns alone."""
        ...

    async def stored_row(self, account_id: UUID) -> StoredSettings:
        """The row as stored (None = default), for partial writes (ADR-0021)."""
        ...

    async def patch(
        self, account_id: UUID, columns: dict[str, object], defaults: NotificationSettings
    ) -> NotificationSettings:
        """Upsert only these stored columns; returns the effective settings."""
        ...

    async def patch_with_pause(
        self,
        account_id: UUID,
        columns: dict[str, object],
        defaults: NotificationSettings,
        today: date,
    ) -> tuple[NotificationSettings, PracticePause | None]:
        """`patch` plus the rest period covering `today` in its RETURNING (WH-01)."""
        ...

    async def mark_intro_sent(self, account_id: UUID, at: datetime) -> None:
        """The first moon reminder (with the intro) arrived: never again (Q24)."""
        ...

    async def patch_practice(
        self, account_id: UUID, patch: ReminderPatch, defaults: NotificationSettings
    ) -> NotificationSettings: ...

    async def candidates(
        self, since: datetime, logged_from: date, defaults: NotificationSettings
    ) -> list[ReminderCandidate]:
        """Deliveries created since `since`; for practice-reminder accounts, logged days from
        `logged_from` on (one statement for all accounts, never one per account). Each
        account's reminder days are its practice days (`defaults_for` its day off)."""
        ...

    async def claim(self, account_id: UUID, key: str, category: str, local_date: date) -> bool:
        """True when this run may send it (new, or a failed one under its retry limit)."""
        ...

    async def finish(self, account_id: UUID, key: str, status: str) -> None: ...

    async def mark_unreachable(self, account_id: UUID, at: datetime) -> None: ...

    async def prune(self, before: datetime) -> int: ...


class DeliveryStatus(StrEnum):
    SENT = "sent"
    BLOCKED = "blocked"  # the person blocked the bot: pause until they write again
    RETRY_AFTER = "retry_after"  # rate limited: stop this run
    FAILED = "failed"  # transient: a later tick retries (limited)


@dataclass(frozen=True, slots=True)
class DeliveryResult:
    status: DeliveryStatus
    retry_after_s: float = 0.0


@dataclass(frozen=True, slots=True)
class Recipient:
    telegram_id: str
    locale: Locale


@dataclass(frozen=True, slots=True)
class MoonReminder:
    """What to say, not how: the adapter renders text and buttons."""

    moon_day: MoonDay
    days_before: int
    city: City
    intro: bool  # the first moon reminder explains the tradition once
    offsets: frozenset[int]  # the recipient's choice, named in the intro
    today: date  # the recipient's local date (whether a date shows its year)


@dataclass(frozen=True, slots=True)
class PracticeReminder:
    """The daily "practice or rest?" prompt for `day` with quick-log buttons, or (pause) the
    one gentle note after a long silence that turns the reminder off."""

    day: date
    pause: bool = False


type Notification = MoonReminder | PracticeReminder


@dataclass(frozen=True, slots=True)
class ExportFile:
    """The ST-09 export, sent to the person's own chat as a document."""

    name: str
    content: bytes
    local_date: date  # named in the caption


class Notifier(Protocol):
    async def deliver(self, recipient: Recipient, notification: Notification) -> DeliveryResult: ...

    async def send_export(self, recipient: Recipient, file: ExportFile) -> DeliveryResult: ...
