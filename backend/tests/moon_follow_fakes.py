"""In-memory fakes that load MD-02's inputs with the account (spec §3, ADR-0032).

In production one statement fills `Account.teaches` and `Account.main_teacher`; here every
account the fake repository returns is enriched from the link rows the same way: `teaches` =
has a student, the main teacher = `ORDER BY is_primary DESC, created_at, teacher_id LIMIT 1`,
with that teacher's own stored `moon_location`. Rows store only what was chosen; the inputs
are derived on every read, as in SQL.

Its own module (like `teacher_link_fakes.py`) so the existing suites keep collecting before
MD-02 exists. The port shapes the spec leaves open are assumed here, and are the ones to
adjust with the port (`Accepted`, `set_primary` and `unlink` live in
`teacher_link_fakes.py`):

- `Notifier.tell_student_joined(recipient, name, keep: City | None)`;
- `AccountRepository.set_moon_location_if_unset(account_id, slug) -> Account | None`;
- `ReminderCandidate` += `teaches: bool`, `teacher_location: str | None`.
"""

import asyncio
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any
from uuid import UUID

from tests.fakes import (
    FakeNotifier,
    InMemoryAccounts,
    InMemoryDays,
    InMemoryExport,
    InMemoryNotifications,
    InMemoryStorage,
)
from tests.teacher_link_fakes import InMemoryTeacherLinks, add_person
from tristhana.application.ports.export import Owned
from tristhana.application.ports.notifications import (
    DeliveryResult,
    DeliveryStatus,
    KeepOffer,
    Recipient,
    ReminderCandidate,
)
from tristhana.domain.accounts import (
    Account,
    IdentityKey,
    NewAccount,
    ProfileChange,
    ProfileUpdate,
)
from tristhana.domain.locale import Locale
from tristhana.domain.moon import City
from tristhana.domain.notifications import NotificationSettings
from tristhana.domain.rest_days import DayOff

__all__ = [
    "FollowingAccounts",
    "FollowingLinks",
    "KeepNotifier",
    "add_person",
    "following_storage",
]


@dataclass
class FollowingAccounts(InMemoryAccounts):
    links: "FollowingLinks | None" = None
    conditional_writes: int = 0  # `set_moon_location_if_unset` calls that wrote

    def inputs(self, account: Account) -> Account:
        """The account as the middleware's statement returns it."""
        if self.links is None:
            return account
        return replace(
            account,
            teaches=bool(self.links.students_of(account.id)),
            main_teacher=self.links.main_of(account.id),
        )

    def stored(self, account_id: UUID) -> Account:
        """What the row holds (no derived inputs)."""
        return self.accounts[account_id]

    async def find_by_identity(self, key: IdentityKey) -> Account | None:
        found = await super().find_by_identity(key)
        return None if found is None else self.inputs(found)

    async def create_with_identity(self, key: IdentityKey, new: NewAccount) -> Account:
        return self.inputs(await super().create_with_identity(key, new))

    async def update_profile(
        self, account_id: UUID, changes: ProfileUpdate, seen_at: datetime
    ) -> Account:
        return self.inputs(await super().update_profile(account_id, changes, seen_at))

    async def update_settings(self, account_id: UUID, change: ProfileChange) -> Account:
        return self.inputs(await super().update_settings(account_id, change))

    async def set_moon_location(self, account_id: UUID, slug: str | None) -> Account:
        return self.inputs(await super().set_moon_location(account_id, slug))

    async def set_timezone_if_unset(self, account_id: UUID, timezone: str) -> Account:
        return self.inputs(await super().set_timezone_if_unset(account_id, timezone))

    async def set_day_off(self, account_id: UUID, day_off: DayOff) -> Account:
        return self.inputs(await super().set_day_off(account_id, day_off))

    async def set_moon_location_if_unset(self, account_id: UUID, slug: str) -> Account | None:
        """`UPDATE … WHERE moon_location IS NULL RETURNING`: the check and the write are one
        step, so two taps at once write once."""
        self._check()
        await asyncio.sleep(0)  # the round trip
        current = self.accounts[account_id]
        if current.moon_location is not None:
            return None
        self.conditional_writes += 1
        return self.inputs(self._save(replace(current, moon_location=slug)))


@dataclass
class FollowingLinks(InMemoryTeacherLinks):
    """The base fake already fills MD-02's `Accepted`, `set_primary` and `unlink` shapes."""


@dataclass
class FollowingNotifications(InMemoryNotifications):
    """The tick's candidates with the same inputs (`DISTINCT ON (student_id)` CTE)."""

    async def candidates(
        self, since: datetime, logged_from: Any, defaults: NotificationSettings
    ) -> list[ReminderCandidate]:
        out: list[ReminderCandidate] = []
        accounts = self.accounts
        for c in await super().candidates(since, logged_from, defaults):
            enriched = (
                accounts.inputs(accounts.accounts[c.account_id])
                if isinstance(accounts, FollowingAccounts)
                else accounts.accounts[c.account_id]
            )
            main = enriched.main_teacher
            out.append(
                replace(
                    c,
                    teaches=enriched.teaches,
                    teacher_location=main.moon_location if main else None,
                )
            )
        return out


@dataclass
class FollowingExport(InMemoryExport):
    async def snapshot(self, account_id: UUID, defaults: Any, reminders_from: Any) -> Owned | None:
        owned = await super().snapshot(account_id, defaults, reminders_from)
        accounts = self.accounts
        if owned is None or not isinstance(accounts, FollowingAccounts):
            return owned
        return replace(owned, account=accounts.inputs(owned.account))


@dataclass
class KeepNotifier(FakeNotifier):
    """Records the city a join note offers to keep (`[Keep 📍 …]`), None = no offer, and the
    whole offer."""

    keeps: list[City | None] = field(default_factory=list[City | None])
    offers: list[KeepOffer | None] = field(default_factory=list[KeepOffer | None])

    async def tell_student_joined(
        self, recipient: Recipient, name: str | None, keep: KeepOffer | None = None
    ) -> DeliveryResult:
        self.joined.append((recipient, name))
        self.keeps.append(keep.kept if keep else None)
        self.offers.append(keep)
        return DeliveryResult(DeliveryStatus.SENT)


def following_storage() -> InMemoryStorage:
    accounts = FollowingAccounts()
    days = InMemoryDays()
    storage = InMemoryStorage(
        repo=accounts,
        day_repo=days,
        notification_repo=FollowingNotifications(accounts, days=days),
        export_repo=FollowingExport(accounts),
    )
    links = FollowingLinks(accounts)
    storage.link_repo = links
    accounts.links = links
    return storage


def person(
    storage_or_accounts: InMemoryStorage | FollowingAccounts,
    telegram_id: str,
    name: str | None = "Person",
    *,
    moon: str | None = None,
    locale: Locale = "en",
    zone: str | None = "Asia/Almaty",
) -> Account:
    """Someone with a stored moon choice (None = never chose)."""
    accounts = (
        storage_or_accounts.repo
        if isinstance(storage_or_accounts, InMemoryStorage)
        else storage_or_accounts
    )
    created = add_person(accounts, telegram_id, name, locale, zone)
    # No join-date bound, so the fictional 4 to 6 Nov moon days show as auto days.
    accounts.accounts[created.id] = replace(created, moon_location=moon, created_at=None)
    return accounts.accounts[created.id]
