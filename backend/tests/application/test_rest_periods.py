"""WH-01 part 2 use cases on fakes (ADR-0023): the pause offer after a 🌸/🤒/✈️ save, the
cut by 🧘 and "keep the pause", start / end early, reads that merge covered days, the
reminder's insert-if-absent 🧘/😌 (Q26), and the tick skipping paused days."""

from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

import pytest

from tests.fakes import (
    FakeCalculator,
    FakeNotifier,
    FixedClock,
    InMemoryStorage,
    cities,
    practice_use_cases,
)
from tristhana.application import remind as remind_app
from tristhana.application.days import ClearDayStatus, GetDays, SetDayStatus
from tristhana.application.policies import Principal
from tristhana.application.ports.notifications import ReminderPatch
from tristhana.application.rest_periods import (
    EndRestPeriod,
    RestoreRestPeriod,
    SkipRestPeriod,
    StartRestPeriod,
)
from tristhana.application.stats import GetYearStats
from tristhana.application.tick import RunTick
from tristhana.domain.accounts import IdentityKey, IdentityProvider, NewAccount
from tristhana.domain.days import DateInFuture, DayLog, DayStatus
from tristhana.domain.moon import MoonDay, MoonDayKind, calendar_years
from tristhana.domain.notifications import DEFAULTS, send_instant
from tristhana.domain.rest_periods import InvalidRestPeriod, PauseOffer, RestPeriod
from tristhana.infrastructure.seed.cities_yaml import load_cities

L, K, T = DayStatus.LADIES, DayStatus.SICK, DayStatus.TRAVEL
ZONE = "Asia/Almaty"
TODAY = date(2026, 10, 26)  # a Monday
NOW = datetime(2026, 10, 26, 6, tzinfo=UTC)  # 11:00 in Almaty
MORNING = send_instant(TODAY, time(10), ZONE)
CITIES = load_cities(Path(__file__).resolve().parents[3] / "data" / "seed" / "cities.yaml")


def _d(offset: int) -> date:
    return TODAY + timedelta(days=offset)


def _p(start: int, end: int, kind: DayStatus = L) -> RestPeriod:
    return RestPeriod(_d(start), _d(end), kind)


@pytest.fixture
def storage() -> InMemoryStorage:
    return InMemoryStorage()


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(NOW)


async def _me(storage: InMemoryStorage, reminders: bool = False) -> Principal:
    created = await storage.accounts.create_with_identity(
        IdentityKey(IdentityProvider.TELEGRAM, "42"), NewAccount(display_name="A", locale="ru")
    )
    account = await storage.accounts.set_timezone_if_unset(created.id, ZONE)
    if reminders:
        await storage.notifications.patch_practice(account.id, ReminderPatch(on=True), DEFAULTS)
    return Principal(account)


def _store(storage: InMemoryStorage, me: Principal, *periods: RestPeriod) -> None:
    for p in periods:
        storage.rest_periods.rows[(me.account.id, p.start)] = p


def _log(storage: InMemoryStorage, me: Principal, day: date, status: DayStatus) -> None:
    storage.days.rows[(me.account.id, day)] = (DayLog(day, status), ZONE)


def _periods(storage: InMemoryStorage, me: Principal) -> list[RestPeriod]:
    return storage.rest_periods.of(me.account.id)


# SetDayStatus → DaySaved: the offer


@pytest.mark.parametrize("kind", [L, K, T])
async def test_a_pausable_status_today_comes_with_the_offer(
    storage: InMemoryStorage, clock: FixedClock, kind: DayStatus
) -> None:
    me = await _me(storage)

    saved = await SetDayStatus(storage.days, clock).execute(me, TODAY, kind)

    assert saved.day == DayLog(TODAY, kind)
    assert saved.offer == PauseOffer(TODAY, kind, reminders_on=False)
    assert (saved.period, saved.cut) == (None, None)
    assert _periods(storage, me) == []  # nothing is stored until a number is chosen


async def test_the_offer_says_whether_practice_reminders_are_on(
    storage: InMemoryStorage, clock: FixedClock
) -> None:
    me = await _me(storage, reminders=True)

    saved = await SetDayStatus(storage.days, clock).execute(me, _d(-1), K)

    assert saved.offer == PauseOffer(_d(-1), K, reminders_on=True)


@pytest.mark.parametrize(
    ("day", "status"),
    [(_d(-2), L), (_d(-10), K), (_d(0), DayStatus.REST), (_d(0), DayStatus.PRACTICED)],
)
async def test_no_offer_for_backfill_or_other_statuses(
    storage: InMemoryStorage, clock: FixedClock, day: date, status: DayStatus
) -> None:
    me = await _me(storage)

    saved = await SetDayStatus(storage.days, clock).execute(me, day, status)

    assert saved.offer is None


async def test_no_offer_for_a_continuation(storage: InMemoryStorage, clock: FixedClock) -> None:
    me = await _me(storage)
    _log(storage, me, _d(-1), L)

    saved = await SetDayStatus(storage.days, clock).execute(me, TODAY, L)

    assert saved.offer is None


async def test_a_pause_that_ran_out_asks_again(storage: InMemoryStorage, clock: FixedClock) -> None:
    me = await _me(storage)
    _log(storage, me, _d(-3), L)
    _store(storage, me, _p(-3, -1, L))

    saved = await SetDayStatus(storage.days, clock).execute(me, TODAY, L)

    assert saved.offer == PauseOffer(TODAY, L, reminders_on=False)


async def test_no_offer_inside_a_period_and_the_period_is_returned(
    storage: InMemoryStorage, clock: FixedClock
) -> None:
    me = await _me(storage)
    period = _p(-1, 2, L)
    _log(storage, me, _d(-1), L)
    _store(storage, me, period)

    saved = await SetDayStatus(storage.days, clock).execute(me, TODAY, L)

    assert saved.offer is None
    assert saved.period == period


async def test_a_re_tap_on_the_origin_may_choose_again(
    storage: InMemoryStorage, clock: FixedClock
) -> None:
    me = await _me(storage)
    _store(storage, me, _p(0, 3, K))

    saved = await SetDayStatus(storage.days, clock).execute(me, TODAY, T)  # corrected kind

    assert saved.offer == PauseOffer(TODAY, T, reminders_on=False)


# Logging inside a period


async def test_practiced_inside_a_period_cuts_it_and_returns_the_cut(
    storage: InMemoryStorage, clock: FixedClock
) -> None:
    me = await _me(storage)
    period = _p(-2, 2, K)
    _store(storage, me, period)

    saved = await SetDayStatus(storage.days, clock).execute(me, TODAY, DayStatus.PRACTICED)

    assert saved.cut == period  # as it was, for "keep the pause"
    assert saved.period is None
    assert saved.offer is None
    assert _periods(storage, me) == [_p(-2, -1, K)]


async def test_practiced_on_the_origin_removes_the_period(
    storage: InMemoryStorage, clock: FixedClock
) -> None:
    me = await _me(storage)
    _store(storage, me, _p(0, 4, L))

    saved = await SetDayStatus(storage.days, clock).execute(me, TODAY, DayStatus.PRACTICED)

    assert saved.cut == _p(0, 4, L)
    assert _periods(storage, me) == []


@pytest.mark.parametrize("status", [DayStatus.SKIPPED, DayStatus.REST, DayStatus.MOON, T])
async def test_other_statuses_inside_change_only_that_day(
    storage: InMemoryStorage, clock: FixedClock, status: DayStatus
) -> None:
    me = await _me(storage)
    period = _p(-2, 2, L)
    _store(storage, me, period)

    saved = await SetDayStatus(storage.days, clock).execute(me, TODAY, status)

    assert saved.cut is None
    assert saved.period == period
    assert _periods(storage, me) == [period]


async def test_clearing_the_origin_removes_the_period(
    storage: InMemoryStorage, clock: FixedClock
) -> None:
    me = await _me(storage)
    set_status = SetDayStatus(storage.days, clock)
    await set_status.execute(me, _d(-1), L)
    _store(storage, me, _p(-1, 3, L))

    await ClearDayStatus(storage.days).execute(me, _d(-1))

    assert _periods(storage, me) == []


async def test_clearing_a_later_day_keeps_the_period(
    storage: InMemoryStorage, clock: FixedClock
) -> None:
    me = await _me(storage)
    period = _p(-1, 3, L)
    _store(storage, me, period)
    await SetDayStatus(storage.days, clock).execute(me, TODAY, DayStatus.SKIPPED)

    await ClearDayStatus(storage.days).execute(me, TODAY)

    assert _periods(storage, me) == [period]


# StartRestPeriod


async def test_start_stores_the_inclusive_range(
    storage: InMemoryStorage, clock: FixedClock
) -> None:
    me = await _me(storage)

    placed = await StartRestPeriod(storage.rest_periods, clock).execute(me, TODAY, 5, L)

    assert placed.period == _p(0, 4, L)
    assert placed.practice_on is False
    assert _periods(storage, me) == [placed.period]


async def test_start_says_whether_practice_reminders_are_on(
    storage: InMemoryStorage, clock: FixedClock
) -> None:
    me = await _me(storage, reminders=True)

    placed = await StartRestPeriod(storage.rest_periods, clock).execute(me, TODAY, 3, K)

    assert placed.practice_on is True


async def test_start_allows_fourteen_days_of_sick(
    storage: InMemoryStorage, clock: FixedClock
) -> None:
    me = await _me(storage)

    placed = await StartRestPeriod(storage.rest_periods, clock).execute(me, _d(-1), 14, K)

    assert placed.period == _p(-1, 12, K)


@pytest.mark.parametrize(
    ("start", "days", "kind"),
    [
        (_d(0), 10, L),  # not a 🌸 choice
        (_d(0), 14, L),
        (_d(0), 15, K),
        (_d(0), 1, T),
        (_d(0), 3, DayStatus.REST),
        (_d(-2), 3, K),  # never a backfill
    ],
)
async def test_start_validates_per_kind(
    storage: InMemoryStorage, clock: FixedClock, start: date, days: int, kind: DayStatus
) -> None:
    me = await _me(storage)

    with pytest.raises(InvalidRestPeriod):
        await StartRestPeriod(storage.rest_periods, clock).execute(me, start, days, kind)
    assert _periods(storage, me) == []


async def test_start_refuses_a_future_day(storage: InMemoryStorage, clock: FixedClock) -> None:
    me = await _me(storage)

    with pytest.raises(DateInFuture):
        await StartRestPeriod(storage.rest_periods, clock).execute(me, _d(1), 3, K)


async def test_start_replaces_what_it_overlaps(storage: InMemoryStorage, clock: FixedClock) -> None:
    me = await _me(storage)
    _store(storage, me, _p(-4, 1, K), _p(2, 5, T), _p(6, 8, T))

    await StartRestPeriod(storage.rest_periods, clock).execute(me, TODAY, 3, L)

    assert _periods(storage, me) == [_p(-4, -1, K), _p(0, 2, L), _p(6, 8, T)]


async def test_start_on_the_same_day_replaces_the_earlier_choice(
    storage: InMemoryStorage, clock: FixedClock
) -> None:
    me = await _me(storage)
    start = StartRestPeriod(storage.rest_periods, clock)

    await start.execute(me, TODAY, 5, L)
    await start.execute(me, TODAY, 2, L)

    assert _periods(storage, me) == [_p(0, 1, L)]


# RestoreRestPeriod ("keep the pause")


async def test_keep_the_pause_restores_the_period_exactly(
    storage: InMemoryStorage, clock: FixedClock
) -> None:
    me = await _me(storage)
    _store(storage, me, _p(-2, 3, L))
    saved = await SetDayStatus(storage.days, clock).execute(me, TODAY, DayStatus.PRACTICED)
    assert saved.cut is not None

    kept = await RestoreRestPeriod(storage.rest_periods, clock).execute(me, saved.cut)

    assert kept == _p(-2, 3, L)
    assert _periods(storage, me) == [_p(-2, 3, L)]
    assert storage.days.rows[(me.account.id, TODAY)][0].status is DayStatus.PRACTICED


async def test_keep_the_pause_after_the_origin_was_practiced(
    storage: InMemoryStorage, clock: FixedClock
) -> None:
    me = await _me(storage)
    _store(storage, me, _p(0, 2, K))
    saved = await SetDayStatus(storage.days, clock).execute(me, TODAY, DayStatus.PRACTICED)
    assert saved.cut == _p(0, 2, K)
    assert saved.cut is not None

    await RestoreRestPeriod(storage.rest_periods, clock).execute(me, saved.cut)

    assert _periods(storage, me) == [_p(0, 2, K)]


async def test_a_stale_keep_is_a_no_op(storage: InMemoryStorage, clock: FixedClock) -> None:
    me = await _me(storage)
    _store(storage, me, _p(-6, -4, K))

    kept = await RestoreRestPeriod(storage.rest_periods, clock).execute(me, _p(-6, -1, K))

    assert kept is None
    assert _periods(storage, me) == [_p(-6, -4, K)]


async def test_keep_without_a_practiced_day_inside_is_never_a_backfill(
    storage: InMemoryStorage, clock: FixedClock
) -> None:
    """Review fix: a forged keep from 13 days ago, with no 🧘 that cut it, writes nothing."""
    me = await _me(storage)
    _log(storage, me, _d(-14), DayStatus.PRACTICED)  # the day before it: does not count

    kept = await RestoreRestPeriod(storage.rest_periods, clock).execute(me, _p(-13, 0, K))

    assert kept is None
    assert _periods(storage, me) == []


async def test_a_forged_keep_longer_than_the_kind_allows_is_refused(
    storage: InMemoryStorage, clock: FixedClock
) -> None:
    me = await _me(storage)

    with pytest.raises(InvalidRestPeriod):
        await RestoreRestPeriod(storage.rest_periods, clock).execute(me, _p(-3, 4, L))  # 8 days
    assert _periods(storage, me) == []


# EndRestPeriod


async def test_end_early_keeps_the_past_days_and_is_idempotent(
    storage: InMemoryStorage, clock: FixedClock
) -> None:
    me = await _me(storage)
    _store(storage, me, _p(-3, 2, T))
    end = EndRestPeriod(storage.rest_periods, clock)

    first = await end.execute(me, _d(-3))
    again = await end.execute(me, _d(-3))

    assert first.period == again.period == _p(-3, -1, T)
    assert first.kind is T
    assert _periods(storage, me) == [_p(-3, -1, T)]


async def test_end_on_the_origin_removes_it(storage: InMemoryStorage, clock: FixedClock) -> None:
    me = await _me(storage)
    _store(storage, me, _p(0, 3, L))
    end = EndRestPeriod(storage.rest_periods, clock)

    first = await end.execute(me, TODAY)
    again = await end.execute(me, TODAY)

    assert (first.period, first.kind) == (None, L)  # removed, but it says what it was
    assert (again.period, again.kind) == (None, None)  # nothing there any more
    assert _periods(storage, me) == []


async def test_end_uses_the_account_zone_for_today(storage: InMemoryStorage) -> None:
    """23:30 UTC on Oct 25 is already Oct 26 in Almaty: the pause ends on the 25th."""
    me = await _me(storage)
    _store(storage, me, _p(-2, 3, K))

    ended = await EndRestPeriod(
        storage.rest_periods, FixedClock(datetime(2026, 10, 25, 23, 30, tzinfo=UTC))
    ).execute(me, _d(-2))

    assert ended.period == _p(-2, -1, K)


# Reads


async def test_get_days_returns_periods_and_never_auto_days_under_them(
    storage: InMemoryStorage, clock: FixedClock
) -> None:
    me = await _me(storage)
    storage.moon.days_by_location["mysuru"] = [MoonDay(_d(-1), MoonDayKind.PURNIMA)]
    period = _p(-2, 2, L)
    _store(storage, me, period)

    view = await GetDays(storage.days, cities(), clock).execute(me, _d(-6), TODAY)

    assert list(view.periods) == [period]  # unclipped: it runs past the window
    assert _d(-1) not in view.auto
    assert view.practice_on is False


async def test_get_days_says_whether_practice_reminders_are_on(
    storage: InMemoryStorage, clock: FixedClock
) -> None:
    me = await _me(storage, reminders=True)

    view = await GetDays(storage.days, cities(), clock).execute(me)

    assert view.practice_on is True


async def test_year_stats_count_covered_days_as_their_kind(
    storage: InMemoryStorage, clock: FixedClock
) -> None:
    me = await _me(storage)
    _log(storage, me, _d(-3), L)
    _store(storage, me, _p(-3, 1, L))
    catalog = practice_use_cases().catalog

    view = await GetYearStats(storage.days, storage.moon, CITIES, catalog, clock).execute(me)

    yday = TODAY.timetuple().tm_yday - 1
    assert view.stats.cells[yday - 3 : yday + 1] == [L, L, L, L]
    assert view.stats.months[9].rest.get(L) == 4  # Oct 23..26; nothing after today
    assert view.stats.months[9].unlogged == 22  # Oct 1..22 only


# The reminder's 🧘 / 😌 (Q26): insert-if-absent, never overwrite


def _from_reminder(storage: InMemoryStorage, clock: FixedClock):
    return remind_app.LogFromReminder(storage.days, clock)


@pytest.mark.parametrize("status", [DayStatus.PRACTICED, DayStatus.REST])
async def test_reminder_tap_logs_an_empty_day(
    storage: InMemoryStorage, clock: FixedClock, status: DayStatus
) -> None:
    me = await _me(storage)

    logged = await _from_reminder(storage, clock).execute(me, TODAY, status)

    assert not logged.already
    assert logged.day == DayLog(TODAY, status)
    assert storage.days.rows[(me.account.id, TODAY)][0] == DayLog(TODAY, status)


@pytest.mark.parametrize("status", [DayStatus.PRACTICED, DayStatus.REST])
async def test_reminder_tap_never_overwrites_a_day_logged_since(
    storage: InMemoryStorage, clock: FixedClock, status: DayStatus
) -> None:
    me = await _me(storage)
    _log(storage, me, TODAY, L)

    logged = await _from_reminder(storage, clock).execute(me, TODAY, status)

    assert logged.already
    assert logged.day == DayLog(TODAY, L)  # shown as stored, with ✏️ Change
    assert storage.days.rows[(me.account.id, TODAY)][0].status is L


async def test_reminder_practiced_inside_a_period_cuts_it(
    storage: InMemoryStorage, clock: FixedClock
) -> None:
    me = await _me(storage)
    _store(storage, me, _p(-2, 2, K))

    await _from_reminder(storage, clock).execute(me, TODAY, DayStatus.PRACTICED)

    assert _periods(storage, me) == [_p(-2, -1, K)]


async def test_reminder_rest_inside_a_period_changes_only_that_day(
    storage: InMemoryStorage, clock: FixedClock
) -> None:
    me = await _me(storage)
    _store(storage, me, _p(-2, 2, K))

    await _from_reminder(storage, clock).execute(me, TODAY, DayStatus.REST)

    assert _periods(storage, me) == [_p(-2, 2, K)]


async def test_reminder_tap_for_a_future_day_is_refused(
    storage: InMemoryStorage, clock: FixedClock
) -> None:
    me = await _me(storage)

    with pytest.raises(DateInFuture):
        await _from_reminder(storage, clock).execute(me, _d(2), DayStatus.PRACTICED)


# The tick: practice reminders skip paused days, moon reminders keep coming


async def _tick(storage: InMemoryStorage, notifier: FakeNotifier) -> None:
    for city in CITIES.all:
        for year in calendar_years(MORNING.date()):
            storage.moon.ledger[(city.slug, year)] = "test-1"
    tick = RunTick(
        FixedClock(MORNING), CITIES, storage.moon, FakeCalculator(), storage.notifications, notifier
    )
    await tick.execute(timedelta(seconds=40))


async def _practice_only(storage: InMemoryStorage) -> Principal:
    me = await _me(storage)
    practice = replace(DEFAULTS.practice, on=True, days=frozenset(range(1, 8)))
    off = replace(DEFAULTS.moon, offsets=frozenset[int]())
    await storage.notifications.save(me.account.id, replace(DEFAULTS, moon=off, practice=practice))
    return me


async def test_tick_skips_a_paused_day(storage: InMemoryStorage) -> None:
    me = await _practice_only(storage)
    _store(storage, me, _p(-1, 1, K))
    notifier = FakeNotifier()

    await _tick(storage, notifier)

    assert notifier.practice == []


async def test_tick_reminds_again_once_the_pause_ran_out(storage: InMemoryStorage) -> None:
    me = await _practice_only(storage)
    _store(storage, me, _p(-3, -1, K))
    notifier = FakeNotifier()

    await _tick(storage, notifier)

    assert [n.day for _, n in notifier.practice] == [TODAY]


async def test_moon_reminders_still_come_during_a_pause(storage: InMemoryStorage) -> None:
    me = await _me(storage)
    storage.moon.days_by_location["mysuru"] = [MoonDay(_d(1), MoonDayKind.PURNIMA)]
    both = replace(
        DEFAULTS,
        moon=replace(DEFAULTS.moon, at=time(10)),
        practice=replace(DEFAULTS.practice, on=True, days=frozenset(range(1, 8))),
        daily_cap=2,
    )
    await storage.notifications.save(me.account.id, both)
    _store(storage, me, _p(-1, 2, L))
    notifier = FakeNotifier()

    await _tick(storage, notifier)

    assert len(notifier.moon) == 1
    assert notifier.practice == []


# Second review (2026-10-27)


async def test_a_stale_keep_never_deletes_a_newer_pause(
    storage: InMemoryStorage, clock: FixedClock
) -> None:
    """Owner: 🌸 Oct 20-26, 🧘 Oct 22 cuts it to 20-21, 🤒 Oct 23 for 5 days; the old Keep
    tapped on Oct 24 changes nothing."""
    me = await _me(storage)
    _store(storage, me, RestPeriod(date(2026, 10, 20), date(2026, 10, 26), L))
    on_24 = FixedClock(datetime(2026, 10, 24, 6, tzinfo=UTC))
    saved = await SetDayStatus(storage.days, on_24).execute(
        me, date(2026, 10, 22), DayStatus.PRACTICED
    )
    _store(storage, me, RestPeriod(date(2026, 10, 23), date(2026, 10, 27), K))
    assert saved.cut is not None

    kept = await RestoreRestPeriod(storage.rest_periods, on_24).execute(me, saved.cut)

    assert kept is None
    assert _periods(storage, me) == [
        RestPeriod(date(2026, 10, 20), date(2026, 10, 21), L),
        RestPeriod(date(2026, 10, 23), date(2026, 10, 27), K),
    ]


async def test_re_saving_practiced_never_cuts_again(
    storage: InMemoryStorage, clock: FixedClock
) -> None:
    """🧘 cut the pause, Keep put it back; tapping ✓🧘 again leaves it kept."""
    me = await _me(storage)
    _store(storage, me, _p(-2, 3, K))
    set_status = SetDayStatus(storage.days, clock)
    first = await set_status.execute(me, TODAY, DayStatus.PRACTICED)
    assert first.cut is not None
    await RestoreRestPeriod(storage.rest_periods, clock).execute(me, first.cut)

    again = await set_status.execute(me, TODAY, DayStatus.PRACTICED)

    assert again.cut is None
    assert _periods(storage, me) == [_p(-2, 3, K)]


async def test_a_stale_day_count_after_the_start_was_re_logged_starts_nothing(
    storage: InMemoryStorage, clock: FixedClock
) -> None:
    me = await _me(storage)
    _log(storage, me, TODAY, DayStatus.PRACTICED)

    placed = await StartRestPeriod(storage.rest_periods, clock).execute(me, TODAY, 3, K)

    assert placed.period is None
    assert _periods(storage, me) == []


async def test_the_day_count_needs_a_matching_or_empty_start_day(
    storage: InMemoryStorage, clock: FixedClock
) -> None:
    me = await _me(storage)
    _log(storage, me, _d(-1), L)
    start = StartRestPeriod(storage.rest_periods, clock)

    assert (await start.execute(me, _d(-1), 3, L)).period == _p(-1, 1, L)
    assert (await start.execute(me, TODAY, 3, K)).period == _p(0, 2, K)  # not logged yet


@pytest.mark.parametrize(
    ("day", "expected"),
    [(_d(0), []), (_d(-1), []), (_d(-3), [_p(-3, 2, K)])],
)
async def test_just_that_day_only_drops_a_recent_pause_starting_that_day(
    storage: InMemoryStorage, clock: FixedClock, day: date, expected: list[RestPeriod]
) -> None:
    me = await _me(storage)
    _store(storage, me, RestPeriod(day, _d(2), K))

    await SkipRestPeriod(storage.rest_periods, clock).execute(me, day)

    assert _periods(storage, me) == expected
