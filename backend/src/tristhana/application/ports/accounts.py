from datetime import datetime
from typing import Protocol
from uuid import UUID

from tristhana.domain.accounts import (
    Account,
    IdentityKey,
    NewAccount,
    ProfileChange,
    ProfileUpdate,
)
from tristhana.domain.rest_days import DayOff


class IdentityTaken(Exception):
    """Another request created an account for this identity first (concurrent first contact)."""


class AccountRepository(Protocol):
    """Every method is one atomic statement (one DB round trip); none leaves partial rows.

    Storage failures raise `StorageUnavailable`.
    """

    async def find_by_identity(self, key: IdentityKey) -> Account | None: ...

    async def create_with_identity(self, key: IdentityKey, new: NewAccount) -> Account:
        """Raises `IdentityTaken` if the identity already belongs to an account."""
        ...

    async def update_profile(
        self, account_id: UUID, changes: ProfileUpdate, seen_at: datetime
    ) -> Account:
        """A refresh from the client: never overwrites a name or locale chosen in settings,
        even when a settings change lands between the read and this write."""
        ...

    async def update_settings(self, account_id: UUID, change: ProfileChange) -> Account: ...

    async def set_moon_location(self, account_id: UUID, slug: str | None) -> Account: ...

    async def set_timezone_if_unset(self, account_id: UUID, timezone: str) -> Account:
        """Sets the zone only if the account has none; returns the account either way."""
        ...

    async def set_day_off(self, account_id: UUID, day_off: DayOff) -> Account: ...

    async def dismiss_day_off_question(self, account_id: UUID) -> None:
        """Idempotent: the first "Not now" is kept."""
        ...
