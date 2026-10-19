"""Settings (ID-06, ADR-0021): profile fields and partial notification settings. Shared by
the bot and the API; every call acts on the caller's own account (`Principal`)."""

from dataclasses import replace

from tristhana.application.policies import Principal
from tristhana.application.ports.accounts import AccountRepository
from tristhana.application.ports.notifications import NotificationRepository
from tristhana.domain.accounts import Account, ExternalProfile, ProfilePatch, resolve_profile
from tristhana.domain.notifications import (
    DEFAULTS,
    NotificationPatch,
    NotificationSettings,
    apply_patch,
    check_settings,
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

    def __init__(self, notifications: NotificationRepository) -> None:
        self._notifications = notifications

    async def execute(
        self, principal: Principal, patch: NotificationPatch, practice_as_on: bool = False
    ) -> NotificationSettings:
        """Raises `InvalidSettings`. `practice_as_on`: check the practice time as if the
        reminder were on (a time in quiet hours could never fire once it's turned on)."""
        account_id = principal.account.id
        stored = await self._notifications.stored_row(account_id)
        merged = apply_patch(stored, patch)
        if practice_as_on:
            merged = replace(merged, practice_on=True)
        check_settings(effective(merged, DEFAULTS))
        return await self._notifications.patch(account_id, patch.columns(), DEFAULTS)
