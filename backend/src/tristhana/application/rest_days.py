"""The weekly day off (PR-09, ADR-0022). Shared by the bot and the API; every call acts on
the caller's own account (`Principal`)."""

from collections.abc import Iterable
from dataclasses import dataclass

from tristhana.application.policies import Principal
from tristhana.application.ports.accounts import AccountRepository
from tristhana.application.ports.storage import Clock
from tristhana.domain.accounts import Account
from tristhana.domain.days import local_today, provisional_zone
from tristhana.domain.notifications import reminder_days
from tristhana.domain.rest_days import change_day_off, check_day_off


@dataclass(frozen=True, slots=True)
class DayOffSaved:
    account: Account
    practice_days: frozenset[int]  # the reminder days that follow it


class SetDayOff:
    def __init__(self, accounts: AccountRepository, clock: Clock) -> None:
        self._accounts, self._clock = accounts, clock

    async def execute(self, principal: Principal, days: Iterable[int]) -> DayOffSaved:
        """Raises `InvalidDayOff`. Reminder days follow the day off. One statement (none
        when the day off is already this one)."""
        account = principal.account
        new = check_day_off(days)
        if new != account.day_off.days:
            zone = account.timezone or provisional_zone(account.locale)
            today = local_today(self._clock.now(), zone)
            changed = change_day_off(account.day_off, new, today)
            account = await self._accounts.set_day_off(account.id, changed)
        return DayOffSaved(account, reminder_days(new))


class DismissDayOffQuestion:
    def __init__(self, accounts: AccountRepository) -> None:
        self._accounts = accounts

    async def execute(self, principal: Principal) -> None:
        """ "Not now": the one-time question doesn't come back. One statement."""
        await self._accounts.dismiss_day_off_question(principal.account.id)
