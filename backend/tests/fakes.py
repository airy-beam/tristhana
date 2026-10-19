"""In-memory adapters for tests above the infrastructure layer."""

from dataclasses import dataclass, field, fields, replace
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID, uuid4

from tristhana.application.days import ClearDayStatus, GetDays, SetDayStatus
from tristhana.application.ports.accounts import IdentityTaken
from tristhana.application.ports.notifications import (
    Delivery,
    DeliveryResult,
    DeliveryStatus,
    MoonCandidate,
    MoonPatch,
    MoonReminder,
    Recipient,
)
from tristhana.application.ports.storage import StorageUnavailable
from tristhana.application.practice import (
    ClearPractice,
    CopyLastPractice,
    GetPracticePresets,
    SavePractice,
)
from tristhana.application.practice_patch import PracticePatch
from tristhana.bots.telegram.runtime import DayUseCases, MoonUseCases, PracticeUseCases
from tristhana.domain.accounts import Account, IdentityKey, NewAccount, ProfileUpdate
from tristhana.domain.days import DayLog, DayStatus
from tristhana.domain.moon import MoonDay, MoonDayKind, MoonLocation
from tristhana.domain.notifications import NotificationSettings
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

    async def set_moon_location(self, account_id: UUID, slug: str | None) -> Account:
        self._check()
        return self._save(replace(self.accounts[account_id], moon_location=slug))

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
class InMemoryMoon:
    days_by_location: dict[str, list[MoonDay]] = field(default_factory=dict[str, list[MoonDay]])
    ledger: dict[tuple[str, int], str] = field(default_factory=dict[tuple[str, int], str])

    async def days(self, location: str, start: date, end: date) -> list[MoonDay]:
        return [d for d in self.days_by_location.get(location, []) if start <= d.date <= end]

    async def coverage(self) -> dict[tuple[str, int], str]:
        return dict(self.ledger)

    async def replace_year(
        self, location: str, year: int, days: list[MoonDay], algo_version: str
    ) -> None:
        kept = [d for d in self.days_by_location.get(location, []) if d.date.year != year]
        self.days_by_location[location] = sorted([*kept, *days], key=lambda d: d.date)
        self.ledger[(location, year)] = algo_version


@dataclass
class InMemoryNotifications:
    accounts: InMemoryAccounts
    stored: dict[UUID, NotificationSettings] = field(
        default_factory=dict[UUID, NotificationSettings]
    )
    deliveries: dict[tuple[UUID, str], dict[str, Any]] = field(
        default_factory=dict[tuple[UUID, str], dict[str, Any]]
    )
    unreachable: dict[UUID, datetime] = field(default_factory=dict[UUID, datetime])

    async def settings(
        self, account_id: UUID, defaults: NotificationSettings
    ) -> NotificationSettings:
        return self.stored.get(account_id, defaults)

    async def save(self, account_id: UUID, settings: NotificationSettings) -> NotificationSettings:
        self.stored[account_id] = settings
        return settings

    async def patch_moon(
        self, account_id: UUID, patch: MoonPatch, defaults: NotificationSettings
    ) -> NotificationSettings:
        current = self.stored.get(account_id, defaults)
        moon = replace(
            current.moon,
            offsets=patch.offsets if patch.offsets is not None else current.moon.offsets,
            at=patch.at or current.moon.at,
        )
        self.stored[account_id] = replace(current, moon=moon)
        return self.stored[account_id]

    async def moon_candidates(
        self, since: datetime, defaults: NotificationSettings
    ) -> list[MoonCandidate]:
        out: list[MoonCandidate] = []
        for key, account_id in self.accounts.identities.items():
            account = self.accounts.accounts[account_id]
            settings = self.stored.get(account_id, defaults)
            if account.timezone is None or not settings.moon.on or account_id in self.unreachable:
                continue
            mine = [
                Delivery(
                    k,
                    d["local_date"],
                    d["status"] != "failed" or d["attempts"] >= 3,
                    d["status"] in ("sent", "claimed"),
                )
                for (a, k), d in self.deliveries.items()
                if a == account_id
            ]
            had = any(
                d["status"] == "sent" for (a, _), d in self.deliveries.items() if a == account_id
            )
            out.append(
                MoonCandidate(
                    account_id,
                    key.provider_user_id,
                    account.locale,
                    account.timezone,
                    account.moon_location,
                    settings,
                    tuple(mine),
                    had,
                )
            )
        return out

    async def claim(self, account_id: UUID, key: str, category: str, local_date: date) -> bool:
        row = self.deliveries.get((account_id, key))
        if row is None:
            self.deliveries[(account_id, key)] = {
                "status": "claimed",
                "attempts": 1,
                "local_date": local_date,
            }
            return True
        if row["status"] == "failed" and row["attempts"] < 3:
            row.update(status="claimed", attempts=row["attempts"] + 1)
            return True
        return False

    async def finish(self, account_id: UUID, key: str, status: str) -> None:
        self.deliveries[(account_id, key)]["status"] = status

    async def mark_unreachable(self, account_id: UUID, at: datetime) -> None:
        self.unreachable[account_id] = at

    async def prune(self, before: datetime) -> int:
        return 0


@dataclass
class FakeNotifier:
    outcomes: list[DeliveryResult] = field(default_factory=list[DeliveryResult])
    delivered: list[tuple[Recipient, MoonReminder]] = field(
        default_factory=list[tuple[Recipient, MoonReminder]]
    )

    async def deliver(self, recipient: Recipient, reminder: MoonReminder) -> DeliveryResult:
        self.delivered.append((recipient, reminder))
        return self.outcomes.pop(0) if self.outcomes else DeliveryResult(DeliveryStatus.SENT)


@dataclass
class FakeCalculator:
    version: str = "test-1"
    calls: int = 0

    async def compute_year(self, location: MoonLocation, year: int) -> list[MoonDay]:
        self.calls += 1
        return [
            MoonDay(date(year, 3, 14), MoonDayKind.PURNIMA),
            MoonDay(date(year, 3, 29), MoonDayKind.AMAVASYA),
        ]


@dataclass
class InMemoryStorage:
    repo: InMemoryAccounts = field(default_factory=InMemoryAccounts)
    day_repo: InMemoryDays = field(default_factory=InMemoryDays)
    moon_repo: InMemoryMoon = field(default_factory=InMemoryMoon)
    notification_repo: InMemoryNotifications | None = None

    def __post_init__(self) -> None:
        if self.notification_repo is None:
            self.notification_repo = InMemoryNotifications(self.repo)

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

    @property
    def moon(self) -> InMemoryMoon:
        return self.moon_repo

    @property
    def notifications(self) -> InMemoryNotifications:
        assert self.notification_repo is not None
        return self.notification_repo


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


def moon_use_cases(storage: "InMemoryStorage | None" = None) -> MoonUseCases:
    from pathlib import Path

    from tristhana.application.moon import (
        GetMoonView,
        SetMoonLocation,
        UpdateMoonReminders,
        UseCityTimezone,
    )
    from tristhana.infrastructure.seed.cities_yaml import load_cities

    storage = storage or InMemoryStorage()
    cities = load_cities(Path(__file__).resolve().parents[2] / "data" / "seed" / "cities.yaml")
    return MoonUseCases(
        cities=cities,
        view=GetMoonView(cities, storage.moon, storage.notifications, FixedClock()),
        set_location=SetMoonLocation(cities, storage.accounts),
        use_city_zone=UseCityTimezone(cities, storage.accounts),
        reminders=UpdateMoonReminders(storage.notifications),
    )
