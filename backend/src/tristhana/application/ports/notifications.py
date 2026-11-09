from dataclasses import dataclass
from datetime import date, datetime, time
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from tristhana.domain.announcements import Source
from tristhana.domain.locale import Locale
from tristhana.domain.moon import City, MoonDay, ShalaMoon, TeacherMoon
from tristhana.domain.notifications import NotificationSettings, PracticeReminders, StoredSettings
from tristhana.domain.progression import Celebration, Position
from tristhana.domain.shalas import ShalaRole


@dataclass(frozen=True, slots=True)
class Delivery:
    key: str
    local_date: date
    final: bool  # sent/blocked, a fresh claim, or failed for good: never retried
    counts_today: bool = True  # toward the daily cap: sent or in flight, not failed


@dataclass(frozen=True, slots=True)
class KeepOffer:
    """MD-02 decision 3: a never-chose teacher's first student ends their inheritance."""

    kept: City  # the city they stop inheriting, offered as `[Keep 📍 …]`
    now: City  # their own setting from now on (the default)
    teacher: str | None  # their own main teacher, who had that city


_NO_ID = UUID(int=0)  # the tick never names or contacts the teacher


@dataclass(frozen=True, slots=True)
class ReminderCandidate:
    """An account that may get reminders (zone known, moon or practice on, reachable)."""

    account_id: UUID
    telegram_id: str
    locale: Locale
    zone: str
    location: str | None  # the account's own `moon_location`
    settings: NotificationSettings
    deliveries: tuple[Delivery, ...]  # recent ones, for dedupe and the daily cap
    had_moon_reminder: bool  # False: the next one carries the intro
    logged: frozenset[date] = frozenset()  # logged days in the window (practice skips them)
    paused: frozenset[date] = frozenset()  # unlogged days covered by a rest period (WH-01)
    teaches: bool = False  # MD-02 inputs, as the account load carries them
    teacher_location: str | None = None  # the main teacher's own `moon_location`
    # SC-01 inputs, as the account load carries them: the main shala's moon city, if any.
    shala_location: str | None = None
    shala_staff: bool = False
    shala_teacher_on_staff: bool = False
    shala_city: str | None = None  # Q111: the fallback for a removed moon city

    @property
    def teacher(self) -> TeacherMoon | None:
        """Enough of the main teacher for `moon_follow`: only the stored value is read."""
        if self.teacher_location is None:
            return None
        return TeacherMoon(_NO_ID, None, self.teacher_location)

    @property
    def shala(self) -> ShalaMoon | None:
        """Enough of the main shala for `moon_follow`: its city and the two flags."""
        if self.shala_location is None:
            return None
        return ShalaMoon(
            _NO_ID,
            "",
            self.shala_location,
            self.shala_staff,
            self.shala_teacher_on_staff,
            self.shala_city,
        )


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

    async def save(self, account_id: UUID, settings: NotificationSettings) -> NotificationSettings:
        """Replace the settings."""
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


@dataclass(frozen=True, slots=True)
class Announcement:
    """NT-03: a teacher's or a shala's text, relayed as written (plain, no preview), with
    Mute and the feed. `silent` in the recipient's quiet hours (Q165: never held)."""

    id: UUID
    source: Source
    source_name: str | None  # the shala's name, or the teacher's display name
    author_name: str | None
    text: str
    silent: bool
    local_date: date


type Notification = MoonReminder | PracticeReminder | Announcement


@dataclass(frozen=True, slots=True)
class ExportFile:
    """The ST-09 export, sent to the person's own chat as a document."""

    name: str
    content: bytes
    local_date: date  # named in the caption


@dataclass(frozen=True, slots=True)
class AsanaMarked:
    """PR-08 Phase 3: a teacher's mark, as the student is told it. No celebration = held
    before (the quiet line); `event_id` is for the note's Undo."""

    event_id: int
    celebrations: tuple[Celebration, ...]
    target: Position


class Notifier(Protocol):
    async def deliver(self, recipient: Recipient, notification: Notification) -> DeliveryResult: ...

    async def send_export(self, recipient: Recipient, file: ExportFile) -> DeliveryResult: ...

    async def tell_student_joined(
        self, recipient: Recipient, name: str | None, keep: KeepOffer | None = None
    ) -> DeliveryResult:
        """ID-04: one silent direct note, outside the ledger and the cap; no retry. `keep`:
        the MD-02 first-student offer."""
        ...

    async def tell_staff_joined(
        self, recipient: Recipient, name: str | None, shala: str, role: ShalaRole
    ) -> DeliveryResult:
        """SC-01 (Q105): the inviter's one silent note when their staff link is used."""
        ...

    async def tell_asana_marked(
        self, recipient: Recipient, teacher: str | None, mark: AsanaMarked
    ) -> DeliveryResult:
        """PR-08 Phase 3: the student's one silent note about a teacher's mark, with Undo;
        outside the ledger and the cap, no retry (as `tell_student_joined`)."""
        ...
