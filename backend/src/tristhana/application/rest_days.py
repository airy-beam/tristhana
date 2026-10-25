"""The weekly day off (PR-09, ADR-0022). Shared by the bot and the API; every call acts on
the caller's own account (`Principal`)."""

from collections.abc import Iterable
from dataclasses import dataclass

from tristhana.application.policies import Principal
from tristhana.application.ports.accounts import AccountRepository
from tristhana.application.ports.notifications import NotificationRepository
from tristhana.application.ports.storage import Clock
from tristhana.domain.accounts import Account
from tristhana.domain.days import local_today, provisional_zone
from tristhana.domain.notifications import NotificationSettings, defaults_for, reminder_days
from tristhana.domain.rest_days import change_day_off, check_day_off


@dataclass(frozen=True, slots=True)
class DayOffSaved:
    account: Account
    settings: NotificationSettings
    reminders_reset: bool  # custom reminder days were replaced: "now follow your day off"


class SetDayOff:
    def __init__(
        self, accounts: AccountRepository, notifications: NotificationRepository, clock: Clock
    ) -> None:
        self._accounts, self._notifications, self._clock = accounts, notifications, clock

    async def execute(self, principal: Principal, days: Iterable[int]) -> DayOffSaved:
        """Raises `InvalidDayOff`. Reminder days follow the new day off. Two statements (one
        read when the day off is already this one)."""
        account = principal.account
        new = check_day_off(days)
        if new == account.day_off.days:  # a re-tap: custom reminder days must survive it
            settings = await self._notifications.settings(account.id, defaults_for(new))
            return DayOffSaved(account, settings, reminders_reset=False)
        zone = account.timezone or provisional_zone(account.locale)
        today = local_today(self._clock.now(), zone)
        changed = change_day_off(account.day_off, new, today)
        saved = await self._accounts.set_day_off(account.id, changed)
        settings, before = await self._notifications.reset_practice_days(
            account.id, defaults_for(new)
        )
        reset = before is not None and before != reminder_days(new)
        return DayOffSaved(saved, settings, reset)


class DismissDayOffQuestion:
    def __init__(self, accounts: AccountRepository) -> None:
        self._accounts = accounts

    async def execute(self, principal: Principal) -> None:
        """ "Not now": the one-time question doesn't come back. One statement."""
        await self._accounts.dismiss_day_off_question(principal.account.id)
