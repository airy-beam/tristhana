"""Account use cases (ID-01). The bot and the API both resolve the caller through
`EnsureAccount`, so an account exists from the first contact on either side."""

from tristhana.application.policies import Principal
from tristhana.application.ports.accounts import AccountRepository, IdentityTaken
from tristhana.application.ports.storage import Clock
from tristhana.domain.accounts import (
    Account,
    ExternalProfile,
    device_timezone,
    new_account,
    profile_refresh,
)


class EnsureAccount:
    """Find the account for this identity, or create it silently (no forms).

    Warm path: one SELECT. A write happens on first contact, when the name or language
    changed, or about once a day to keep `last_seen_at` fresh.
    """

    def __init__(self, accounts: AccountRepository, clock: Clock) -> None:
        self._accounts = accounts
        self._clock = clock

    async def execute(self, profile: ExternalProfile) -> Account:
        account = await self._accounts.find_by_identity(profile.key)
        if account is None:
            try:
                return await self._accounts.create_with_identity(profile.key, new_account(profile))
            except IdentityTaken:
                # A concurrent first contact (e.g. /start and the Mini App at once) won.
                account = await self._accounts.find_by_identity(profile.key)
                if account is None:
                    raise RuntimeError("identity taken but not found") from None
                return account
        now = self._clock.now()
        update = profile_refresh(account, profile, now)
        if update is None:
            return account
        return await self._accounts.update_profile(account.id, update, now)


class RecordDeviceTimezone:
    """The Mini App reports the device zone; it's stored only if the account has none.

    Changing a zone that is already set is a deliberate choice (ID-06 settings, travel prompt),
    never a silent overwrite. Raises `InvalidTimezone` for fixed offsets and unknown names.
    """

    def __init__(self, accounts: AccountRepository) -> None:
        self._accounts = accounts

    async def execute(self, principal: Principal, timezone: str) -> Account:
        zone = device_timezone(timezone)
        account = principal.account
        if zone is None or account.timezone is not None:
            return account
        return await self._accounts.set_timezone_if_unset(account.id, zone)
