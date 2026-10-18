"""In-memory adapters for tests above the infrastructure layer."""

from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime
from uuid import UUID, uuid4

from tristhana.application.days import ClearDayStatus, GetDays, SetDayStatus
from tristhana.application.ports.accounts import IdentityTaken
from tristhana.application.ports.storage import StorageUnavailable
from tristhana.bots.telegram.runtime import DayUseCases
from tristhana.domain.accounts import Account, IdentityKey, NewAccount, ProfileUpdate
from tristhana.domain.days import DayLog

NOW = datetime(2026, 10, 18, 6, 0, tzinfo=UTC)


@dataclass
class FixedClock:
    instant: datetime = NOW

    def now(self) -> datetime:
        return self.instant


@dataclass
class InMemoryAccounts:
    accounts: dict[UUID, Account] = field(default_factory=dict[UUID, Account])
    identities: dict[IdentityKey, UUID] = field(default_factory=dict[IdentityKey, UUID])
    clock: FixedClock = field(default_factory=FixedClock)
    down: bool = False
    writes: int = 0
    # Simulates a concurrent first contact: the next create finds the identity taken.
    steal_next_create: bool = False

    async def find_by_identity(self, key: IdentityKey) -> Account | None:
        self._check()
        account_id = self.identities.get(key)
        return self.accounts[account_id] if account_id else None

    async def create_with_identity(self, key: IdentityKey, new: NewAccount) -> Account:
        self._check()
        if self.steal_next_create:
            self.steal_next_create = False
            self._insert(key, NewAccount(display_name="Winner", locale=new.locale))
        if key in self.identities:
            raise IdentityTaken
        return self._insert(key, new)

    async def update_profile(
        self, account_id: UUID, changes: ProfileUpdate, seen_at: datetime
    ) -> Account:
        self._check()
        account = replace(
            self.accounts[account_id],
            display_name=changes.display_name,
            locale=changes.locale,
            last_seen_at=seen_at,
        )
        return self._save(account)

    async def set_timezone_if_unset(self, account_id: UUID, timezone: str) -> Account:
        self._check()
        account = self.accounts[account_id]
        if account.timezone is not None:
            return account
        return self._save(replace(account, timezone=timezone))

    def _insert(self, key: IdentityKey, new: NewAccount) -> Account:
        account = Account(
            id=uuid4(),
            display_name=new.display_name,
            locale=new.locale,
            timezone=None,
            last_seen_at=self.clock.now(),
        )
        self.identities[key] = account.id
        return self._save(account)

    def _save(self, account: Account) -> Account:
        self.writes += 1
        self.accounts[account.id] = account
        return account

    def _check(self) -> None:
        if self.down:
            raise StorageUnavailable


@dataclass
class InMemoryDays:
    rows: dict[tuple[UUID, date], tuple[DayLog, str | None]] = field(
        default_factory=dict[tuple[UUID, date], tuple[DayLog, str | None]]
    )
    down: bool = False

    async def upsert(self, account_id: UUID, day: DayLog, timezone: str | None) -> DayLog:
        self._check()
        self.rows[(account_id, day.local_date)] = (day, timezone)
        return day

    async def delete(self, account_id: UUID, local_date: date) -> None:
        self._check()
        self.rows.pop((account_id, local_date), None)

    async def list_range(self, account_id: UUID, start: date, end: date) -> list[DayLog]:
        self._check()
        found = [
            d for (a, when), (d, _) in self.rows.items() if a == account_id and start <= when <= end
        ]
        return sorted(found, key=lambda d: d.local_date)

    def _check(self) -> None:
        if self.down:
            raise StorageUnavailable


@dataclass
class InMemoryStorage:
    repo: InMemoryAccounts = field(default_factory=InMemoryAccounts)
    day_repo: InMemoryDays = field(default_factory=InMemoryDays)
    started: bool = False

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.started = False

    async def ping(self) -> None:
        if self.repo.down:
            raise StorageUnavailable

    @property
    def accounts(self) -> InMemoryAccounts:
        return self.repo

    @property
    def days(self) -> InMemoryDays:
        return self.day_repo


def day_use_cases(repo: InMemoryDays | None = None, clock: FixedClock | None = None) -> DayUseCases:
    repo, clock = repo or InMemoryDays(), clock or FixedClock()
    return DayUseCases(
        get=GetDays(repo, clock), set=SetDayStatus(repo, clock), clear=ClearDayStatus(repo)
    )
