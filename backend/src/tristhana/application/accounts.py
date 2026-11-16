"""Account use cases (ID-01). The bot and the API both resolve the caller through
`EnsureAccount`, so an account exists from the first contact on either side."""

from dataclasses import dataclass

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
from tristhana.domain.journey import active


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


@dataclass(frozen=True, slots=True)
class Welcome:
    first: bool  # this call recorded it: the person's first `/start` since UI-06
    # Has a student, a teacher, a shala or (on the first call only: it comes with the write)
    # a logged day.
    active: bool

    @property
    def front_door(self) -> bool:
        """Show the front door: once, and only to someone who has done nothing yet. An
        active person's first call gets Today with the one-time Menu hint instead."""
        return self.first and not self.active


class MarkWelcomed:
    """Record that the person has met the front door (UI-06 §3), so it is shown once.

    Called only while `account.welcomed` is false: by `/start` without a payload, and by an
    invite `/start` (so the front door never shows later). One statement; a call for an
    account already marked writes nothing, and a second call racing the first is not `first`.
    """

    def __init__(self, accounts: AccountRepository, clock: Clock) -> None:
        self._accounts = accounts
        self._clock = clock

    async def execute(self, principal: Principal) -> Welcome:
        account = principal.account
        if account.welcomed:
            return Welcome(first=False, active=active(account, has_days=False))
        has_days = await self._accounts.mark_welcomed(account.id, self._clock.now())
        if has_days is None:  # another request got there first
            return Welcome(first=False, active=active(account, has_days=False))
        return Welcome(first=True, active=active(account, has_days))
