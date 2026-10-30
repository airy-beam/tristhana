"""The daily practice reminder (PR-10): its settings, the one-time offer, and the one-tap
log from the reminder message. Shared by the bot and the API; every call acts on the
caller's own account (`Principal`)."""

from dataclasses import dataclass, replace
from datetime import date
from zoneinfo import ZoneInfo

from tristhana.application.days import count_celebrations
from tristhana.application.policies import Principal
from tristhana.application.ports.days import DayLogRepository
from tristhana.application.ports.notifications import (
    NotificationRepository,
    PracticePause,
    ReminderPatch,
)
from tristhana.application.ports.practice import PracticeRepository
from tristhana.application.ports.storage import Clock
from tristhana.application.settings import PatchNotificationSettings
from tristhana.domain.days import DayLog, DayStatus, check_loggable, provisional_zone
from tristhana.domain.milestones import PracticeCounts
from tristhana.domain.notifications import (
    KEEP,
    NotificationPatch,
    NotificationSettings,
    default_practice_time,
    defaults_for,
)
from tristhana.domain.progression import Celebration
from tristhana.domain.rest_periods import RestPeriod


@dataclass(frozen=True, slots=True)
class QuickLog:
    day: DayLog | None  # None: the day was cleared between the two statements
    copied_from: date | None  # the practice that was copied, if any
    already: bool  # the day was logged before the tap: nothing was written
    cut: RestPeriod | None = None  # a rest period this 🧘 cut, as it was (WH-01 "keep")
    celebrations: tuple[Celebration, ...] = ()  # a practice count reached (GM-01)


class QuickLogSameAsLast:
    """✅ on a reminder: Practiced + the usual practice copied, in one tap. Never overwrites
    a day that is already logged (it might be a private 🌸 record the reminder can't show)."""

    def __init__(
        self,
        days: DayLogRepository,
        practices: PracticeRepository,
        clock: Clock,
        counts: PracticeCounts,
    ) -> None:
        self._days, self._practices, self._clock = days, practices, clock
        self._counts = counts

    async def execute(self, principal: Principal, local_date: date) -> QuickLog:
        """Raises `DateInFuture` / `DateTooEarly`."""
        account = principal.account
        check_loggable(local_date, self._clock.now(), account.timezone)
        day = DayLog(local_date, DayStatus.PRACTICED)
        inserted = await self._days.insert_if_absent(
            account.id, day, account.timezone, self._counts.thresholds
        )
        if not inserted.inserted:
            stored = await self._days.list_range(account.id, local_date, local_date)
            return QuickLog(stored[0] if stored else None, None, already=True)
        copied = await self._practices.copy_usual(account.id, local_date, account.timezone)
        celebrations = count_celebrations(inserted.reached)
        if copied is None:
            return QuickLog(day, None, False, inserted.cut, celebrations)
        practiced = replace(day, practices=(copied.practice,))
        return QuickLog(practiced, copied.source, False, inserted.cut, celebrations)


class LogFromReminder:
    """🧘 / 😌 on a reminder (Q26, WH-01): log the day only if it is still empty, so a day
    logged since (maybe a private 🌸) is never overwritten; then it is shown as stored."""

    _ALLOWED = frozenset({DayStatus.PRACTICED, DayStatus.REST})

    def __init__(self, days: DayLogRepository, clock: Clock, counts: PracticeCounts) -> None:
        self._days, self._clock, self._counts = days, clock, counts

    async def execute(self, principal: Principal, local_date: date, status: DayStatus) -> QuickLog:
        """Raises `DateInFuture` / `DateTooEarly`. Two statements only when already logged."""
        if status not in self._ALLOWED:
            raise ValueError(f"a reminder logs only practiced or rest, not {status}")
        account = principal.account
        check_loggable(local_date, self._clock.now(), account.timezone)
        day = DayLog(local_date, status)
        inserted = await self._days.insert_if_absent(
            account.id, day, account.timezone, self._counts.thresholds
        )
        if not inserted.inserted:
            stored = await self._days.list_range(account.id, local_date, local_date)
            return QuickLog(stored[0] if stored else None, None, already=True)
        celebrations = count_celebrations(inserted.reached)
        return QuickLog(day, None, False, inserted.cut, celebrations)


class UpdatePracticeReminder:
    def __init__(self, notifications: NotificationRepository, clock: Clock | None = None) -> None:
        self._patch = PatchNotificationSettings(notifications, clock)

    async def execute(self, principal: Principal, patch: ReminderPatch) -> NotificationSettings:
        """Raises `InvalidSettings`. A time inside the (stored) quiet hours is refused even
        while the reminder is off: it could never fire once turned on."""
        return await self._patch.execute(principal, _practice(patch), patch.at is not None)

    async def execute_with_pause(
        self, principal: Principal, patch: ReminderPatch
    ) -> tuple[NotificationSettings, PracticePause | None]:
        """`execute` plus the rest period covering today (WH-01), for `/remind`."""
        return await self._patch.execute_with_pause(
            principal, _practice(patch), patch.at is not None
        )


def _practice(patch: ReminderPatch) -> NotificationPatch:
    return NotificationPatch(
        practice_on=KEEP if patch.on is None else patch.on,
        practice_at=KEEP if patch.at is None else patch.at,
    )


class AnswerPracticeOffer:
    """The one-time offer after logging today's practice. Yes picks the time from when it
    was tapped (morning practitioners 10:00, later 20:00); the person can change it."""

    def __init__(self, notifications: NotificationRepository, clock: Clock) -> None:
        self._notifications, self._clock = notifications, clock

    async def execute(self, principal: Principal, yes: bool) -> NotificationSettings:
        """A no-op once a choice exists: an old offer in chat history must not undo
        settings made since (in /remind or the app)."""
        account = principal.account
        defaults = defaults_for(account.day_off.days)
        current = await self._notifications.settings(account.id, defaults)
        if current.practice.on is not None:
            return current
        if not yes:
            patch = ReminderPatch(on=False)
        else:
            # A provisional zone is fine for this guess; sending still waits for a real one.
            zone = account.timezone or provisional_zone(account.locale)
            tapped = self._clock.now().astimezone(ZoneInfo(zone)).time().replace(tzinfo=None)
            patch = ReminderPatch(on=True, at=default_practice_time(tapped))
        return await self._notifications.patch_practice(account.id, patch, defaults)
