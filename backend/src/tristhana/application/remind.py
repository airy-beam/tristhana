"""The daily practice reminder (PR-10): its settings, the one-time offer, and the one-tap
log from the reminder message. Shared by the bot and the API; every call acts on the
caller's own account (`Principal`)."""

from dataclasses import dataclass, replace
from datetime import date
from zoneinfo import ZoneInfo

from tristhana.application.policies import Principal
from tristhana.application.ports.days import DayLogRepository
from tristhana.application.ports.notifications import NotificationRepository, ReminderPatch
from tristhana.application.ports.practice import PracticeRepository
from tristhana.application.ports.storage import Clock
from tristhana.application.settings import PatchNotificationSettings
from tristhana.domain.days import DayLog, DayStatus, check_loggable, provisional_zone
from tristhana.domain.notifications import (
    KEEP,
    NotificationPatch,
    NotificationSettings,
    default_practice_time,
    defaults_for,
)


@dataclass(frozen=True, slots=True)
class QuickLog:
    day: DayLog | None  # None: the day was cleared between the two statements
    copied_from: date | None  # the practice that was copied, if any
    already: bool  # the day was logged before the tap: nothing was written


class QuickLogSameAsLast:
    """✅ on a reminder: Practiced + the usual practice copied, in one tap. Never overwrites
    a day that is already logged (it might be a private 🌸 record the reminder can't show)."""

    def __init__(self, days: DayLogRepository, practices: PracticeRepository, clock: Clock) -> None:
        self._days, self._practices, self._clock = days, practices, clock

    async def execute(self, principal: Principal, local_date: date) -> QuickLog:
        """Raises `DateInFuture` / `DateTooEarly`."""
        account = principal.account
        check_loggable(local_date, self._clock.now(), account.timezone)
        day = DayLog(local_date, DayStatus.PRACTICED)
        if not await self._days.insert_if_absent(account.id, day, account.timezone):
            stored = await self._days.list_range(account.id, local_date, local_date)
            return QuickLog(stored[0] if stored else None, None, already=True)
        copied = await self._practices.copy_usual(account.id, local_date, account.timezone)
        if copied is None:
            return QuickLog(day, None, already=False)
        return QuickLog(replace(day, practices=(copied.practice,)), copied.source, already=False)


class UpdatePracticeReminder:
    def __init__(self, notifications: NotificationRepository) -> None:
        self._patch = PatchNotificationSettings(notifications)

    async def execute(self, principal: Principal, patch: ReminderPatch) -> NotificationSettings:
        """Raises `InvalidSettings`. A time inside the (stored) quiet hours is refused even
        while the reminder is off: it could never fire once turned on."""
        return await self._patch.execute(
            principal,
            NotificationPatch(
                practice_on=KEEP if patch.on is None else patch.on,
                practice_at=KEEP if patch.at is None else patch.at,
            ),
            practice_as_on=patch.at is not None,
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
