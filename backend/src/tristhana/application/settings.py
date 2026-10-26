"""Settings (ID-06, ADR-0021): profile fields and partial notification settings. Shared by
the bot and the API; every call acts on the caller's own account (`Principal`)."""

from dataclasses import replace
from datetime import date

from tristhana.application.policies import Principal
from tristhana.application.ports.accounts import AccountRepository
from tristhana.application.ports.notifications import NotificationRepository, PracticePause
from tristhana.application.ports.storage import Clock
from tristhana.domain.accounts import Account, ExternalProfile, ProfilePatch, resolve_profile
from tristhana.domain.days import local_today, provisional_zone
from tristhana.domain.notifications import (
    NotificationPatch,
    NotificationSettings,
    apply_patch,
    check_settings,
    defaults_for,
    effective,
)


class UpdateProfile:
    def __init__(self, accounts: AccountRepository) -> None:
        self._accounts = accounts

    async def execute(
        self, principal: Principal, patch: ProfilePatch, client: ExternalProfile
    ) -> Account:
        """`client` = what Telegram says now (for "back to Telegram's"). Raises
        `InvalidDisplayName`, `InvalidTimezone`. One statement."""
        change = resolve_profile(principal.account, patch, client)
        return await self._accounts.update_settings(principal.account.id, change)


class PatchNotificationSettings:
    """Only the sent fields change; the merged result is validated (so quiet hours are
    checked against the stored reminders). Two statements."""

    def __init__(self, notifications: NotificationRepository, clock: Clock | None = None) -> None:
        self._notifications = notifications
        self._clock = clock  # only `execute_with_pause` needs "today"

    async def execute(
        self, principal: Principal, patch: NotificationPatch, practice_as_on: bool = False
    ) -> NotificationSettings:
        """Raises `InvalidSettings`. `practice_as_on`: check the practice time as if the
        reminder were on (a time in quiet hours could never fire once it's turned on)."""
        defaults = await self._check(principal, patch, practice_as_on)
        return await self._notifications.patch(principal.account.id, patch.columns(), defaults)

    async def execute_with_pause(
        self, principal: Principal, patch: NotificationPatch, practice_as_on: bool = False
    ) -> tuple[NotificationSettings, PracticePause | None]:
        """`execute` plus the rest period covering today (WH-01), from the same write."""
        if self._clock is None:
            raise RuntimeError("PatchNotificationSettings needs a clock for the pause")
        defaults = await self._check(principal, patch, practice_as_on)
        today = caller_today(principal, self._clock)
        return await self._notifications.patch_with_pause(
            principal.account.id, patch.columns(), defaults, today
        )

    async def _check(
        self, principal: Principal, patch: NotificationPatch, practice_as_on: bool
    ) -> NotificationSettings:
        stored = await self._notifications.stored_row(principal.account.id)
        merged = apply_patch(stored, patch)
        if practice_as_on:
            merged = replace(merged, practice_on=True)
        defaults = defaults_for(principal.account.day_off.days)
        check_settings(effective(merged, defaults))
        return defaults


def caller_today(principal: Principal, clock: Clock) -> date:
    """The caller's local date (a provisional zone is fine: display only)."""
    account = principal.account
    zone = account.timezone or provisional_zone(account.locale)
    return local_today(clock.now(), zone)
