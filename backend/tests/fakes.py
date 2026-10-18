"""In-memory adapters for tests above the infrastructure layer."""

from dataclasses import dataclass, field, fields, replace
from datetime import UTC, date, datetime
from uuid import UUID, uuid4

from tristhana.application.days import ClearDayStatus, GetDays, SetDayStatus
from tristhana.application.ports.accounts import IdentityTaken
from tristhana.application.ports.storage import StorageUnavailable
from tristhana.application.practice import (
    ClearPractice,
    CopyLastPractice,
    GetPracticePresets,
    SavePractice,
)
from tristhana.application.practice_patch import PracticePatch
from tristhana.bots.telegram.runtime import DayUseCases, PracticeUseCases
from tristhana.domain.accounts import Account, IdentityKey, NewAccount, ProfileUpdate
from tristhana.domain.days import DayLog, DayStatus
from tristhana.domain.practice import Practice

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
    practice_rows: dict[tuple[UUID, date], Practice] = field(
        default_factory=dict[tuple[UUID, date], Practice]
    )
    down: bool = False

    async def upsert(self, account_id: UUID, day: DayLog, timezone: str | None) -> DayLog:
        self._check()
        self.rows[(account_id, day.local_date)] = (day, timezone)
        if day.status is not DayStatus.PRACTICED:
            self.practice_rows.pop((account_id, day.local_date), None)
        return day

    async def delete(self, account_id: UUID, local_date: date) -> None:
        self._check()
        self.rows.pop((account_id, local_date), None)
        self.practice_rows.pop((account_id, local_date), None)

    async def list_range(self, account_id: UUID, start: date, end: date) -> list[DayLog]:
        self._check()
        found = [
            replace(d, practices=self._practices_of(a, when, d))
            for (a, when), (d, _) in self.rows.items()
            if a == account_id and start <= when <= end
        ]
        return sorted(found, key=lambda d: d.local_date)

    def _practices_of(self, account_id: UUID, when: date, day: DayLog) -> tuple[Practice, ...]:
        practice = self.practice_rows.get((account_id, when))
        return (practice,) if practice and day.status is DayStatus.PRACTICED else ()

    def _check(self) -> None:
        if self.down:
            raise StorageUnavailable


@dataclass
class InMemoryPractices:
    """Shares the day log's rows, so the "only on a practiced day" rule holds."""

    days: InMemoryDays

    def _practiced(self, account_id: UUID, local_date: date) -> bool:
        row = self.days.rows.get((account_id, local_date))
        return row is not None and row[0].status is DayStatus.PRACTICED

    async def save(
        self, account_id: UUID, local_date: date, patch: PracticePatch
    ) -> Practice | None:
        self.days._check()  # pyright: ignore[reportPrivateUsage]
        if not self._practiced(account_id, local_date):
            return None
        current = self.days.practice_rows.get((account_id, local_date), Practice())
        changes = {
            f.name: getattr(patch.values, f.name)
            for f in fields(Practice)
            if f.name in patch.fields
        }
        saved = replace(current, **changes)
        self.days.practice_rows[(account_id, local_date)] = saved
        return saved

    async def copy_latest(
        self, account_id: UUID, local_date: date, timezone: str | None
    ) -> Practice | None:
        self.days._check()  # pyright: ignore[reportPrivateUsage]
        if not self._practiced(account_id, local_date):
            return None
        previous = await self.recent(account_id, local_date, 1)
        if not previous:
            return None
        copied = replace(previous[0], start_time=None, timezone=timezone)
        self.days.practice_rows[(account_id, local_date)] = copied
        return copied

    async def delete(self, account_id: UUID, local_date: date) -> None:
        self.days._check()  # pyright: ignore[reportPrivateUsage]
        self.days.practice_rows.pop((account_id, local_date), None)

    async def recent(self, account_id: UUID, before: date, limit: int) -> list[Practice]:
        self.days._check()  # pyright: ignore[reportPrivateUsage]
        rows = sorted(
            (
                (when, p)
                for (a, when), p in self.days.practice_rows.items()
                if a == account_id and when < before
            ),
            key=lambda r: r[0],
            reverse=True,
        )
        return [p for _, p in rows[:limit]]


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

    @property
    def practices(self) -> InMemoryPractices:
        return InMemoryPractices(self.day_repo)


def day_use_cases(repo: InMemoryDays | None = None, clock: FixedClock | None = None) -> DayUseCases:
    repo, clock = repo or InMemoryDays(), clock or FixedClock()
    return DayUseCases(
        get=GetDays(repo, clock), set=SetDayStatus(repo, clock), clear=ClearDayStatus(repo)
    )


def practice_use_cases(repo: InMemoryDays | None = None) -> PracticeUseCases:
    from pathlib import Path

    from tristhana.infrastructure.seed.practice_catalog import load_practice_catalog

    catalog = load_practice_catalog(Path(__file__).resolve().parents[2] / "data" / "seed").catalog
    practices = InMemoryPractices(repo or InMemoryDays())
    return PracticeUseCases(
        save=SavePractice(practices, catalog),
        copy_last=CopyLastPractice(practices),
        clear=ClearPractice(practices),
        presets=GetPracticePresets(practices, catalog),
        catalog=catalog,
    )
