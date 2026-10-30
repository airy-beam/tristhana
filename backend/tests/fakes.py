"""In-memory adapters for tests above the infrastructure layer."""

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, fields, replace
from datetime import UTC, date, datetime, timedelta
from functools import cache
from typing import Any
from uuid import UUID, uuid4

from tristhana.application.days import ClearDayStatus, GetDays, SetDayStatus
from tristhana.application.ports.accounts import IdentityTaken
from tristhana.application.ports.days import History, Inserted, RangeView, Upserted
from tristhana.application.ports.export import Owned
from tristhana.application.ports.notifications import (
    Delivery,
    DeliveryResult,
    DeliveryStatus,
    ExportFile,
    MoonReminder,
    Notification,
    PracticePause,
    PracticeReminder,
    Recipient,
    ReminderCandidate,
    ReminderPatch,
)
from tristhana.application.ports.practice import CopiedPractice, SavedPractice
from tristhana.application.ports.progression import ProgressionView
from tristhana.application.ports.rest_periods import Ended, Placed
from tristhana.application.ports.storage import StorageUnavailable
from tristhana.application.practice import (
    ClearPractice,
    CopyLastPractice,
    GetPracticePresets,
    SavePractice,
)
from tristhana.application.practice_patch import PracticePatch
from tristhana.application.rest_days import DismissDayOffQuestion, SetDayOff
from tristhana.bots.telegram.runtime import (
    DayUseCases,
    MoonUseCases,
    PracticeUseCases,
    RemindUseCases,
    SettingsUseCases,
)
from tristhana.domain.accounts import (
    Account,
    IdentityKey,
    NewAccount,
    ProfileChange,
    ProfileUpdate,
)
from tristhana.domain.days import DayLog, DayStatus, public_status
from tristhana.domain.export import ExportIdentity
from tristhana.domain.milestones import NO_COUNTS
from tristhana.domain.moon import Cities, MoonDay, MoonDayKind, MoonLocation
from tristhana.domain.notifications import (
    NotificationSettings,
    StoredSettings,
    defaults_for,
    effective,
)
from tristhana.domain.practice import Practice, PracticeContext
from tristhana.domain.progression import (
    HISTORY_LIMIT,
    Change,
    Earlier,
    EventKind,
    Position,
    Progression,
    ProgressionEvent,
)
from tristhana.domain.rest_days import DayOff
from tristhana.domain.rest_periods import UNCHANGED, RestPeriod, cut_by_log, end_from, place

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
    deleted: list[UUID] = field(default_factory=list[UUID])

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

    async def update_settings(self, account_id: UUID, change: ProfileChange) -> Account:
        self._check()
        current = self.accounts[account_id]
        if "name" in change.fields:
            current = replace(
                current, display_name=change.display_name, name_custom=change.name_custom
            )
        if "locale" in change.fields:
            current = replace(current, locale=change.locale, locale_custom=change.locale_custom)
        if "timezone" in change.fields:
            current = replace(current, timezone=change.timezone)
        if "hide_ladies" in change.fields:  # WH-01 part 2
            current = replace(current, hide_ladies=change.hide_ladies)  # type: ignore[call-arg]
        if "offer_check_in" in change.fields:  # PR-06
            current = replace(current, offer_check_in=change.offer_check_in)  # type: ignore[call-arg,attr-defined]
        return self._save(current)

    async def set_moon_location(self, account_id: UUID, slug: str | None) -> Account:
        self._check()
        return self._save(replace(self.accounts[account_id], moon_location=slug))

    async def set_timezone_if_unset(self, account_id: UUID, timezone: str) -> Account:
        self._check()
        account = self.accounts[account_id]
        if account.timezone is not None:
            return account
        return self._save(replace(account, timezone=timezone))

    async def set_day_off(self, account_id: UUID, day_off: DayOff) -> Account:
        self._check()
        return self._save(replace(self.accounts[account_id], day_off=day_off))

    async def dismiss_day_off_question(self, account_id: UUID) -> None:
        self._check()
        self._save(replace(self.accounts[account_id], day_off_dismissed=True))

    async def delete(self, account_id: UUID) -> bool:  # ST-09
        self._check()
        self.deleted.append(account_id)
        for key in [k for k, v in self.identities.items() if v == account_id]:
            del self.identities[key]
        return self.accounts.pop(account_id, None) is not None

    def _insert(self, key: IdentityKey, new: NewAccount) -> Account:
        account = Account(
            id=uuid4(),
            display_name=new.display_name,
            locale=new.locale,
            timezone=None,
            last_seen_at=self.clock.now(),
            created_at=self.clock.now(),
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
class InMemoryRestPeriods:
    """Rest periods (WH-01, ADR-0023). The overlap and cut rules are the domain's, as the
    SQL implements them (parity tests run the same table against Postgres)."""

    rows: dict[tuple[UUID, date], RestPeriod] = field(
        default_factory=dict[tuple[UUID, date], RestPeriod]
    )
    down: bool = False
    # Wired by `InMemoryDays` / `InMemoryStorage` (the DB reads both in the same statement).
    practiced: Callable[[UUID, date, date], bool] = lambda _a, _s, _e: False
    practice_on: Callable[[UUID], bool] = lambda _: False
    logged: Callable[[UUID, date], DayStatus | None] = lambda _a, _d: None

    def of(self, account_id: UUID) -> list[RestPeriod]:
        return sorted(
            (p for (a, _), p in self.rows.items() if a == account_id), key=lambda p: p.start
        )

    def covering(self, account_id: UUID, day: date) -> RestPeriod | None:
        return next((p for p in self.of(account_id) if p.start <= day <= p.end), None)

    async def place(self, account_id: UUID, period: RestPeriod) -> Placed:
        self._check()
        # As the SQL: the start day, if logged, must show the kind (public: 🌸 is `rest`).
        logged = self.logged(account_id, period.start)
        if logged is not None and public_status(logged) is not public_status(period.kind):
            return Placed(None, self.practice_on(account_id))
        self._place(account_id, period)
        return Placed(period, self.practice_on(account_id))

    async def restore(self, account_id: UUID, period: RestPeriod, today: date) -> RestPeriod | None:
        self._check()
        if not self.practiced(account_id, period.start, min(period.end, today)):
            return None  # no cut happened: never a backfill
        if any(period.start < p.start <= period.end for p in self.of(account_id)):
            return None  # a newer pause began since the cut: never undo it
        self._place(account_id, period)
        return period

    def _place(self, account_id: UUID, period: RestPeriod) -> None:
        placement = place(period, self.of(account_id))
        for start in placement.removed:
            self.rows.pop((account_id, start), None)
        for start, end in placement.ended.items():
            self.rows[(account_id, start)] = replace(self.rows[(account_id, start)], end=end)
        self.rows[(account_id, period.start)] = period

    async def end(self, account_id: UUID, start: date, today: date) -> Ended:
        self._check()
        current = self.rows.get((account_id, start))
        if current is None:
            return Ended(None)
        ended = end_from(current, today)
        if ended is None:
            del self.rows[(account_id, start)]
        else:
            self.rows[(account_id, start)] = ended
        return Ended(ended, current.kind)

    def apply_log(self, account_id: UUID, day: date, status: DayStatus | None) -> RestPeriod | None:
        """The cut rule of a log or a clear on `day`; returns the period as it was when a
        🧘 Practiced cut it."""
        current = self.covering(account_id, day)
        if current is None:
            return None
        result = cut_by_log(current, day, status)
        if result is UNCHANGED:
            return None
        if result is None:
            del self.rows[(account_id, current.start)]
        else:
            self.rows[(account_id, current.start)] = result  # type: ignore[assignment]
        return current if status is DayStatus.PRACTICED else None

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
    # PR-06: slot-1 check-ins (`CheckIn`), stored as written (an empty row stays a row; the
    # use case reads it as none). Typed loosely so this module imports before the feature.
    check_in_rows: dict[tuple[UUID, date], Any] = field(
        default_factory=dict[tuple[UUID, date], Any]
    )
    # PR-07: one note per local day (`DiaryNote`; `DiaryNote(None)` = an unreadable seal),
    # independent of the status: status changes and clearing the day never touch it.
    diary_rows: dict[tuple[UUID, date], Any] = field(default_factory=dict[tuple[UUID, date], Any])
    # PR-08: the progression state per account and the event history (oldest first).
    progression_rows: dict[UUID, Progression] = field(default_factory=dict[UUID, Progression])
    progression_events: list[tuple[UUID, ProgressionEvent]] = field(
        default_factory=list[tuple[UUID, ProgressionEvent]]
    )
    # GM-01 part 2: the practice-count ledger, (account, threshold) -> celebrated.
    milestone_rows: dict[tuple[UUID, int], bool] = field(
        default_factory=dict[tuple[UUID, int], bool]
    )
    down: bool = False
    moon: "InMemoryMoon | None" = None  # for `range_with_moon`
    periods: InMemoryRestPeriods = field(default_factory=InMemoryRestPeriods)
    # Whether practice reminders are on (the DB reads it in the same statement).
    practice_on: Callable[[UUID], bool] = lambda _: False

    def __post_init__(self) -> None:
        def practiced(account_id: UUID, start: date, end: date) -> bool:
            return any(
                a == account_id and start <= when <= end and day.status is DayStatus.PRACTICED
                for (a, when), (day, _) in self.rows.items()
            )

        self.periods.practiced = practiced

        def logged(account_id: UUID, day: date) -> DayStatus | None:
            row = self.rows.get((account_id, day))
            return row[0].status if row else None

        self.periods.logged = logged

    def _ledger(self, account_id: UUID, thresholds: Sequence[int]) -> int | None:
        """As the SQL (ADR-0028): after a day became 🧘, record every threshold at or below
        the count; the one equal to it, newly recorded, celebrates."""
        after = sum(
            1
            for (a, _), (d, _) in self.rows.items()
            if a == account_id and d.status is DayStatus.PRACTICED
        )
        reached = None
        for t in thresholds:
            if t <= after and (account_id, t) not in self.milestone_rows:
                self.milestone_rows[(account_id, t)] = t == after
                reached = t if t == after else reached
        return reached

    async def upsert(
        self, account_id: UUID, day: DayLog, timezone: str | None, thresholds: Sequence[int] = ()
    ) -> Upserted:
        self._check()
        when = day.local_date
        prev = self.rows.get((account_id, when - timedelta(days=1)))
        snapshot = tuple(
            p
            for p in self.periods.of(account_id)
            if p.start <= when and p.end >= when - timedelta(1)
        )
        same = self.rows.get((account_id, when))
        again = same is not None and same[0].status is DayStatus.PRACTICED
        # As the SQL: re-saving 🧘 on a 🧘 day cuts nothing (e.g. after "keep the pause").
        cut = None
        if not (again and day.status is DayStatus.PRACTICED):
            cut = self.periods.apply_log(account_id, when, day.status)
        self.rows[(account_id, when)] = (day, timezone)
        if day.status is not DayStatus.PRACTICED:
            self.practice_rows.pop((account_id, when), None)
            self.check_in_rows.pop((account_id, when), None)  # PR-06: same statement
        became = day.status is DayStatus.PRACTICED and not again
        return Upserted(
            day,
            prev=prev[0].status if prev else None,
            periods=snapshot,
            practice_on=self.practice_on(account_id),
            cut=cut,
            reached=self._ledger(account_id, thresholds) if became else None,
        )

    async def insert_if_absent(
        self, account_id: UUID, day: DayLog, timezone: str | None, thresholds: Sequence[int] = ()
    ) -> Inserted:
        self._check()
        if (account_id, day.local_date) in self.rows:
            return Inserted(False)
        cut = self.periods.apply_log(account_id, day.local_date, day.status)
        self.rows[(account_id, day.local_date)] = (day, timezone)
        practiced = day.status is DayStatus.PRACTICED
        return Inserted(True, cut, self._ledger(account_id, thresholds) if practiced else None)

    async def delete(self, account_id: UUID, local_date: date) -> None:
        self._check()
        self.periods.apply_log(account_id, local_date, None)
        self.rows.pop((account_id, local_date), None)
        self.practice_rows.pop((account_id, local_date), None)
        self.check_in_rows.pop((account_id, local_date), None)  # FK cascade

    def _overlapping(self, account_id: UUID, start: date, end: date) -> tuple[RestPeriod, ...]:
        return tuple(p for p in self.periods.of(account_id) if p.start <= end and p.end >= start)

    async def list_range(self, account_id: UUID, start: date, end: date) -> list[DayLog]:
        self._check()
        found = [
            self._with_check_in(a, when, replace(d, practices=self._practices_of(a, when, d)))
            for (a, when), (d, _) in self.rows.items()
            if a == account_id and start <= when <= end
        ]
        return sorted(found, key=lambda d: d.local_date)

    async def range_with_moon(
        self, account_id: UUID, start: date, end: date, location: str
    ) -> RangeView:
        days = await self.list_range(account_id, start, end)
        moon = await self.moon.days(location, start, end) if self.moon else []
        notes = {
            when: note
            for (a, when), note in self.diary_rows.items()
            if a == account_id and start <= when <= end
        }
        # PR-07: `notes` only when there are some, so this works before RangeView has it.
        extra: dict[str, Any] = {"notes": notes} if notes else {}
        return RangeView(
            days,
            frozenset(d.date for d in moon),
            self._overlapping(account_id, start, end),
            self.practice_on(account_id),
            **extra,
        )

    async def history(self, account_id: UUID, start: date, end: date) -> History:
        days = await self.list_range(account_id, start, end)
        mine = [when for (a, when) in self.rows if a == account_id]
        return History(days, min(mine) if mine else None, self._overlapping(account_id, start, end))

    def _with_check_in(self, account_id: UUID, when: date, day: DayLog) -> DayLog:
        """PR-06: like the SQL LEFT JOIN, only on a practiced day (rows as stored)."""
        check_in = self.check_in_rows.get((account_id, when))
        if check_in is None or day.status is not DayStatus.PRACTICED:
            return day  # no `check_ins` keyword: works before DayLog gains the field
        return replace(day, check_ins=(check_in,))  # type: ignore[call-arg]

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

    def _saved(
        self, account_id: UUID, local_date: date, practice: Practice, before: Practice | None
    ) -> SavedPractice:
        """With the day's check-in and the progression, as the SQL's joins (empty check-in
        rows read as none)."""
        found = self.days.check_in_rows.get((account_id, local_date))
        changed = practice.length != (before.length if before else None)
        return SavedPractice(
            practice,
            None if found is None or found.is_empty() else found,
            self.days.progression_rows.get(account_id),
            changed,
        )

    async def save(
        self, account_id: UUID, local_date: date, patch: PracticePatch
    ) -> SavedPractice | None:
        self.days._check()  # pyright: ignore[reportPrivateUsage]
        if not self._practiced(account_id, local_date):
            return None
        before = self.days.practice_rows.get((account_id, local_date))
        changes = {
            f.name: getattr(patch.values, f.name)
            for f in fields(Practice)
            if f.name in patch.fields
        }
        saved = replace(before or Practice(), **changes)
        self.days.practice_rows[(account_id, local_date)] = saved
        return self._saved(account_id, local_date, saved, before)

    async def copy_latest(
        self, account_id: UUID, local_date: date, timezone: str | None
    ) -> SavedPractice | None:
        self.days._check()  # pyright: ignore[reportPrivateUsage]
        if not self._practiced(account_id, local_date):
            return None
        previous = await self.recent(account_id, local_date, 1)
        if not previous:
            return None
        copied = replace(previous[0], start_time=None, timezone=timezone)
        before = self.days.practice_rows.get((account_id, local_date))
        self.days.practice_rows[(account_id, local_date)] = copied
        return self._saved(account_id, local_date, copied, before)

    async def copy_usual(
        self, account_id: UUID, local_date: date, timezone: str | None
    ) -> CopiedPractice | None:
        self.days._check()  # pyright: ignore[reportPrivateUsage]
        if not self._practiced(account_id, local_date):
            return None
        earlier = sorted(
            (
                (when, p)
                for (a, when), p in self.days.practice_rows.items()
                if a == account_id and when < local_date
            ),
            key=lambda r: (r[1].context is not PracticeContext.LED, r[0]),
            reverse=True,
        )
        if not earlier:
            return None
        source, previous = earlier[0]
        copied = replace(previous, start_time=None, timezone=timezone)
        self.days.practice_rows[(account_id, local_date)] = copied
        return CopiedPractice(copied, source)

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

    async def recent_with_progression(
        self, account_id: UUID, before: date, limit: int
    ) -> tuple[list[Practice], Progression | None]:
        recent = await self.recent(account_id, before, limit)
        return recent, self.days.progression_rows.get(account_id)


@dataclass
class InMemoryProgression:
    """PR-08 `ProgressionRepository` over `InMemoryDays.progression_*`, with the SQL's
    compare-and-set and latest-only undo. `calls` counts statements."""

    days: InMemoryDays
    calls: list[str] = field(default_factory=list[str])

    def _events(self, account_id: UUID) -> list[ProgressionEvent]:
        return [e for a, e in self.days.progression_events if a == account_id]

    async def get(self, account_id: UUID) -> ProgressionView:
        self.days._check()  # pyright: ignore[reportPrivateUsage]
        self.calls.append("get")
        events = self._events(account_id)
        targets = frozenset(e.after for e in events if e.after is not None)
        items = frozenset(e.item for e in events if e.kind is EventKind.ITEM_GIVEN and e.item)
        newest = tuple(reversed(events))[:HISTORY_LIMIT]
        return ProgressionView(
            self.days.progression_rows.get(account_id), Earlier(targets, items), newest
        )

    async def apply(
        self, account_id: UUID, change: Change, expected_event_id: int | None, marked_by: UUID
    ) -> ProgressionEvent | None:
        self.days._check()  # pyright: ignore[reportPrivateUsage]
        self.calls.append("apply")
        current = self.days.progression_rows.get(account_id)
        if (current.last_event_id if current else None) != expected_event_id:
            return None
        event_id = 1 + max((e.id for _, e in self.days.progression_events), default=0)
        event = ProgressionEvent(
            event_id,
            change.kind,
            change.occurred_on,
            change.before,
            change.after,
            change.item,
            marked_by == account_id,
        )
        self.days.progression_events.append((account_id, event))
        hint = (current.hint, current.hint_event_id) if current else (None, None)
        self.days.progression_rows[account_id] = Progression(
            change.state.position, change.state.items, event_id, *hint
        )
        return event

    async def undo(self, account_id: UUID, event_id: int) -> bool:
        self.days._check()  # pyright: ignore[reportPrivateUsage]
        self.calls.append("undo")
        current = self.days.progression_rows.get(account_id)
        if current is None or current.last_event_id != event_id:
            return False
        event = next(e for e in self._events(account_id) if e.id == event_id)
        self.days.progression_events.remove((account_id, event))
        if event.kind is EventKind.START:
            del self.days.progression_rows[account_id]
            return True
        previous = max((e.id for e in self._events(account_id)), default=None)
        position, items = current.position, current.items
        if event.kind is EventKind.ITEM_GIVEN and event.item:
            items = items - {event.item}
        elif event.kind is EventKind.ITEM_REMOVED and event.item:
            items = items | {event.item}
        elif event.before is not None:
            position = event.before
        self.days.progression_rows[account_id] = replace(
            current, position=position, items=items, last_event_id=previous
        )
        return True

    async def dismiss_hint(self, account_id: UUID, target: Position) -> None:
        self.days._check()  # pyright: ignore[reportPrivateUsage]
        self.calls.append("dismiss_hint")
        current = self.days.progression_rows.get(account_id)
        if current is not None:
            self.days.progression_rows[account_id] = replace(
                current, hint=target, hint_event_id=current.last_event_id
            )


@dataclass
class InMemoryCheckIns:
    """PR-06 `CheckInRepository`: shares the day log's rows, so a check-in only lands on a
    practiced day (the SQL's EXISTS guard); `CheckIn` is imported lazily."""

    days: InMemoryDays

    def _practiced(self, account_id: UUID, local_date: date) -> bool:
        row = self.days.rows.get((account_id, local_date))
        return row is not None and row[0].status is DayStatus.PRACTICED

    async def save(self, account_id: UUID, local_date: date, patch: Any) -> Any:
        from tristhana.domain.check_in import CheckIn

        self.days._check()  # pyright: ignore[reportPrivateUsage]
        if not self._practiced(account_id, local_date):
            return None
        current = self.days.check_in_rows.get((account_id, local_date), CheckIn())
        changes = {
            f.name: getattr(patch.values, f.name)
            for f in fields(CheckIn)
            if f.name in patch.fields and f.name != "slot"
        }
        saved = replace(current, **changes)
        self.days.check_in_rows[(account_id, local_date)] = saved
        return saved

    async def set_tag(self, account_id: UUID, local_date: date, tag: Any, on: bool) -> Any:
        from tristhana.domain.check_in import CheckIn

        self.days._check()  # pyright: ignore[reportPrivateUsage]
        if not self._practiced(account_id, local_date):
            return None
        current = self.days.check_in_rows.get((account_id, local_date), CheckIn())
        tags = current.tags | {tag} if on else current.tags - {tag}
        saved = replace(current, tags=frozenset(tags))
        self.days.check_in_rows[(account_id, local_date)] = saved
        return saved

    async def delete(self, account_id: UUID, local_date: date) -> None:
        self.days._check()  # pyright: ignore[reportPrivateUsage]
        self.days.check_in_rows.pop((account_id, local_date), None)


@dataclass
class InMemoryDiary:
    """PR-07 `DiaryRepository`: one row per local day in `InMemoryDays.diary_rows`, any
    status or none (no tie to the day log); `DiaryNote` is imported lazily."""

    days: InMemoryDays

    async def save(self, account_id: UUID, local_date: date, text: str) -> None:
        from tristhana.domain.diary import DiaryNote

        self.days._check()  # pyright: ignore[reportPrivateUsage]
        self.days.diary_rows[(account_id, local_date)] = DiaryNote(text)

    async def get(self, account_id: UUID, local_date: date) -> Any:
        self.days._check()  # pyright: ignore[reportPrivateUsage]
        return self.days.diary_rows.get((account_id, local_date))

    async def delete(self, account_id: UUID, local_date: date) -> None:
        self.days._check()  # pyright: ignore[reportPrivateUsage]
        self.days.diary_rows.pop((account_id, local_date), None)


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
    days: "InMemoryDays | None" = None  # logged days for the practice reminder
    intro_sent: set[UUID] = field(default_factory=set[UUID])

    async def settings(
        self, account_id: UUID, defaults: NotificationSettings
    ) -> NotificationSettings:
        stored = self.stored.get(account_id)
        if stored is None:
            return defaults
        # Reminder days are the practice days (PR-09): never stored.
        return replace(stored, practice=replace(stored.practice, days=defaults.practice.days))

    async def save(
        self, account_id: UUID, settings: NotificationSettings, with_practice: bool = True
    ) -> NotificationSettings:
        if not with_practice:
            current = self.stored.get(account_id)
            settings = replace(
                settings, practice=current.practice if current else settings.practice
            )
        self.stored[account_id] = settings
        return settings

    async def settings_with_pause(
        self, account_id: UUID, defaults: NotificationSettings, today: date
    ) -> tuple[NotificationSettings, PracticePause | None]:
        """WH-01: plus the rest period covering `today` (dates only)."""
        settings = await self.settings(account_id, defaults)
        covering = self.days.periods.covering(account_id, today) if self.days else None
        return settings, PracticePause(covering.start, covering.end) if covering else None

    async def stored_row(self, account_id: UUID) -> StoredSettings:
        s = self.stored.get(account_id)
        if s is None:
            return StoredSettings()
        return StoredSettings(
            s.moon.offsets,
            s.moon.at,
            s.quiet.start,
            s.quiet.end,
            s.daily_cap,
            s.practice.on,
            s.practice.at,
        )

    async def patch(
        self, account_id: UUID, columns: dict[str, object], defaults: NotificationSettings
    ) -> NotificationSettings:
        row = replace(await self.stored_row(account_id), **columns)  # type: ignore[arg-type]
        self.stored[account_id] = effective(row, defaults)
        return await self.settings(account_id, defaults)

    async def patch_with_pause(
        self,
        account_id: UUID,
        columns: dict[str, object],
        defaults: NotificationSettings,
        today: date,
    ) -> tuple[NotificationSettings, PracticePause | None]:
        await self.patch(account_id, columns, defaults)
        return await self.settings_with_pause(account_id, defaults, today)

    async def mark_intro_sent(self, account_id: UUID, at: datetime) -> None:
        self.intro_sent.add(account_id)

    async def patch_practice(
        self, account_id: UUID, patch: ReminderPatch, defaults: NotificationSettings
    ) -> NotificationSettings:
        current = await self.settings(account_id, defaults)
        self.stored[account_id] = replace(current, practice=patch.apply(current.practice))
        return await self.settings(account_id, defaults)

    async def candidates(
        self, since: datetime, logged_from: date, defaults: NotificationSettings
    ) -> list[ReminderCandidate]:
        out: list[ReminderCandidate] = []
        for key, account_id in self.accounts.identities.items():
            account = self.accounts.accounts[account_id]
            settings = await self.settings(account_id, defaults_for(account.day_off.days, defaults))
            on = settings.moon.on or settings.practice.enabled
            if account.timezone is None or not on or account_id in self.unreachable:
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
            had = account_id in self.intro_sent
            logged = frozenset(
                when
                for (a, when) in (self.days.rows if self.days else {})
                if a == account_id and when >= logged_from and settings.practice.enabled
            )
            paused = frozenset(
                p.start + timedelta(days=i)
                for p in (self.days.periods.of(account_id) if self.days else [])
                for i in range((p.end - p.start).days + 1)
                if settings.practice.enabled and p.start + timedelta(days=i) >= logged_from
            )
            out.append(
                ReminderCandidate(
                    account_id,
                    key.provider_user_id,
                    account.locale,
                    account.timezone,
                    account.moon_location,
                    settings,
                    tuple(mine),
                    had,
                    logged,
                    paused - logged,
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
    delivered: list[tuple[Recipient, Notification]] = field(
        default_factory=list[tuple[Recipient, Notification]]
    )
    exports: list[tuple[Recipient, ExportFile]] = field(
        default_factory=list[tuple[Recipient, ExportFile]]
    )
    export_outcomes: list[DeliveryResult] = field(default_factory=list[DeliveryResult])

    @property
    def moon(self) -> list[tuple[Recipient, MoonReminder]]:
        return [(r, n) for r, n in self.delivered if isinstance(n, MoonReminder)]

    @property
    def practice(self) -> list[tuple[Recipient, PracticeReminder]]:
        return [(r, n) for r, n in self.delivered if isinstance(n, PracticeReminder)]

    async def deliver(self, recipient: Recipient, notification: Notification) -> DeliveryResult:
        self.delivered.append((recipient, notification))
        return self.outcomes.pop(0) if self.outcomes else DeliveryResult(DeliveryStatus.SENT)

    async def send_export(self, recipient: Recipient, file: ExportFile) -> DeliveryResult:
        self.exports.append((recipient, file))
        if self.export_outcomes:
            return self.export_outcomes.pop(0)
        return DeliveryResult(DeliveryStatus.SENT)


@dataclass
class InMemoryExport:
    """ST-09: the claim slot as the SQL does it; `snapshot` = the account and its Telegram id
    (plus `owned`, when a test sets the rows). Row coverage is a DB test."""

    accounts: InMemoryAccounts
    claimed: dict[UUID, datetime] = field(default_factory=dict[UUID, datetime])
    released: list[UUID] = field(default_factory=list[UUID])
    owned: Owned | None = None

    async def snapshot(
        self, account_id: UUID, defaults: NotificationSettings, reminders_from: date
    ) -> Owned | None:
        self.accounts._check()  # pyright: ignore[reportPrivateUsage]
        account = self.accounts.accounts.get(account_id)
        if account is None:
            return None
        if self.owned is not None:
            return replace(self.owned, account=account)
        identities = tuple(
            ExportIdentity(k.provider.value, k.provider_user_id, NOW)
            for k, v in self.accounts.identities.items()
            if v == account_id
        )
        return Owned(account, identities, defaults, (), (), (), (), (), None, (), ())

    async def claim(self, account_id: UUID, now: datetime, before: datetime) -> datetime | None:
        self.accounts._check()  # pyright: ignore[reportPrivateUsage]
        last = self.claimed.get(account_id)
        if last is not None and last > before:
            return last
        self.claimed[account_id] = now
        return None

    async def release(self, account_id: UUID) -> None:
        self.released.append(account_id)
        self.claimed.pop(account_id, None)


@dataclass
class FakePacker:
    """Packs as JSON so tests can look inside; the ZIP itself is the adapter's test."""

    packed: list[tuple[dict[str, object], dict[str, list[list[str]]], str]] = field(
        default_factory=list[tuple[dict[str, object], dict[str, list[list[str]]], str]]
    )
    size: int | None = None  # force a size (the too-large path)

    async def pack(
        self, data: dict[str, object], tables: dict[str, list[list[str]]], readme: str
    ) -> bytes:
        self.packed.append((data, tables, readme))
        if self.size is not None:
            return b"x" * self.size
        return json.dumps({"data": data, "tables": tables, "readme": readme}).encode()


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
    export_repo: InMemoryExport | None = None

    def __post_init__(self) -> None:
        if self.notification_repo is None:
            self.notification_repo = InMemoryNotifications(self.repo, days=self.day_repo)
        if self.day_repo.moon is None:
            self.day_repo.moon = self.moon_repo
        notifications = self.notification_repo

        def practice_on(account_id: UUID) -> bool:
            stored = notifications.stored.get(account_id)
            return stored is not None and stored.practice.on is True

        self.day_repo.practice_on = practice_on
        self.day_repo.periods.practice_on = practice_on

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

    @property
    def rest_periods(self) -> InMemoryRestPeriods:
        return self.day_repo.periods

    @property
    def check_ins(self) -> InMemoryCheckIns:  # PR-06
        return InMemoryCheckIns(self.day_repo)

    @property
    def diary(self) -> InMemoryDiary:  # PR-07
        return InMemoryDiary(self.day_repo)

    @property
    def progression(self) -> InMemoryProgression:  # PR-08
        return InMemoryProgression(self.day_repo)

    @property
    def export(self) -> InMemoryExport:  # ST-09
        if self.export_repo is None:
            self.export_repo = InMemoryExport(self.repo)
        return self.export_repo


def day_use_cases(repo: InMemoryDays | None = None, clock: FixedClock | None = None) -> DayUseCases:
    repo, clock = repo or InMemoryDays(), clock or FixedClock()
    return DayUseCases(
        get=GetDays(repo, cities(), clock),
        set=SetDayStatus(repo, clock, NO_COUNTS),
        clear=ClearDayStatus(repo),
    )


@cache
def cities() -> Cities:
    from pathlib import Path

    from tristhana.infrastructure.seed.cities_yaml import load_cities

    return load_cities(Path(__file__).resolve().parents[2] / "data" / "seed" / "cities.yaml")


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

    from tristhana.application.moon import (
        GetMoonView,
        SetMoonLocation,
        UpdateMoonReminders,
        UseCityTimezone,
    )

    storage = storage or InMemoryStorage()
    known = cities()
    return MoonUseCases(
        cities=known,
        view=GetMoonView(known, storage.moon, storage.notifications, FixedClock()),
        set_location=SetMoonLocation(known, storage.accounts),
        use_city_zone=UseCityTimezone(known, storage.accounts),
        reminders=UpdateMoonReminders(storage.notifications),
    )


def remind_use_cases(
    storage: "InMemoryStorage | None" = None, clock: FixedClock | None = None
) -> RemindUseCases:
    from tristhana.application.moon import NotificationSettingsUseCase
    from tristhana.application.remind import (
        AnswerPracticeOffer,
        QuickLogSameAsLast,
        UpdatePracticeReminder,
    )

    storage, clock = storage or InMemoryStorage(), clock or FixedClock()
    return RemindUseCases(
        settings=NotificationSettingsUseCase(storage.notifications, clock),
        update=UpdatePracticeReminder(storage.notifications, clock),
        offer=AnswerPracticeOffer(storage.notifications, clock),
        quick_log=QuickLogSameAsLast(storage.days, storage.practices, clock, NO_COUNTS),
        day_off=SetDayOff(storage.accounts, clock),
        dismiss_day_off=DismissDayOffQuestion(storage.accounts),
    )


def settings_use_cases(storage: "InMemoryStorage | None" = None) -> SettingsUseCases:
    from tristhana.application.moon import NotificationSettingsUseCase
    from tristhana.application.settings import UpdateProfile

    storage = storage or InMemoryStorage()
    return SettingsUseCases(
        profile=UpdateProfile(storage.accounts),
        settings=NotificationSettingsUseCase(storage.notifications, FixedClock()),
        cities=moon_use_cases(storage).cities,
        today=day_use_cases(storage.days).get.today,
        day_off=SetDayOff(storage.accounts, FixedClock()),
    )
