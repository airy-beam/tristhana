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
from tristhana.domain.journey import JourneyFacts
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

    async def set_moon_location_if_unset(self, account_id: UUID, slug: str) -> Account | None:
        """One statement, only while `moon_location IS NULL` (MD-02 Keep). None: already set."""
        ...

    async def set_timezone_if_unset(self, account_id: UUID, timezone: str) -> Account:
        """Sets the zone only if the account has none; returns the account either way."""
        ...

    async def set_day_off(self, account_id: UUID, day_off: DayOff) -> Account: ...

    async def dismiss_day_off_question(self, account_id: UUID) -> None:
        """Idempotent: the first "Not now" is kept."""
        ...

    async def mark_welcomed(self, account_id: UUID, at: datetime) -> bool | None:
        """UI-06: record that the person has met the front door (or their first Today), only
        while it is not recorded. One statement. Returns whether the account has any logged
        day; None = already recorded (a second `/start` racing the first), nothing written."""
        ...

    async def journey_facts(self, account_id: UUID) -> JourneyFacts:
        """UI-06 stage 2: what the next step is derived from, in one statement. Only this
        account's own rows: whether a day is logged, whether the practice reminder was ever
        chosen, whether a position is set, the date (UTC) of their teacher invite link, and
        the shalas they own (oldest first) with each one's class and student counts. A shala
        they only teach at or study in is never read."""
        ...

    async def delete(self, account_id: UUID) -> bool:
        """One statement; every per-account row cascades (ST-09). False = already gone."""
        ...
