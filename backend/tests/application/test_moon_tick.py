from dataclasses import replace
from datetime import date, datetime, time, timedelta
from pathlib import Path

import pytest

from tests.fakes import (
    FakeCalculator,
    FakeNotifier,
    FixedClock,
    InMemoryAccounts,
    InMemoryMoon,
    InMemoryNotifications,
)
from tristhana.application.moon import (
    GetMoonView,
    SetMoonLocation,
    UnknownLocation,
    UpdateMoonReminders,
    UseCityTimezone,
)
from tristhana.application.policies import Principal
from tristhana.application.ports.notifications import DeliveryResult, DeliveryStatus, MoonPatch
from tristhana.application.tick import RunTick
from tristhana.domain.accounts import Account, IdentityKey, IdentityProvider, NewAccount
from tristhana.domain.moon import MoonDay, MoonDayKind, calendar_years
from tristhana.domain.notifications import DEFAULTS, InvalidSettings, send_instant
from tristhana.infrastructure.seed.cities_yaml import load_cities

CITIES = load_cities(Path(__file__).resolve().parents[3] / "data" / "seed" / "cities.yaml")
FULL = MoonDay(date(2026, 11, 5), MoonDayKind.PURNIMA)
# 19:00 in Almaty on the day before the full moon.
BUDGET = timedelta(seconds=40)
EVENING = send_instant(date(2026, 11, 4), time(19), "Asia/Almaty")


async def _account(
    accounts: InMemoryAccounts, user: str = "42", zone: str | None = "Asia/Almaty"
) -> Account:
    created = await accounts.create_with_identity(
        IdentityKey(IdentityProvider.TELEGRAM, user), NewAccount(display_name="A", locale="ru")
    )
    if zone:
        created = await accounts.set_timezone_if_unset(created.id, zone)
    return created


def _tick(
    accounts: InMemoryAccounts,
    moon: InMemoryMoon,
    notifications: InMemoryNotifications,
    notifier: FakeNotifier,
    now: datetime = EVENING,
) -> RunTick:
    return RunTick(FixedClock(now), CITIES, moon, FakeCalculator(), notifications, notifier)


@pytest.fixture
def accounts() -> InMemoryAccounts:
    return InMemoryAccounts()


@pytest.fixture
def moon() -> InMemoryMoon:
    m = InMemoryMoon()
    m.days_by_location["mysuru"] = [FULL]
    m.days_by_location["almaty"] = [MoonDay(date(2026, 11, 6), MoonDayKind.PURNIMA)]
    # Covered, so the tick doesn't compute in these tests unless asked to.
    for city in CITIES.all:
        for year in calendar_years(EVENING.date()):
            m.ledger[(city.slug, year)] = "test-1"
    return m


async def test_moon_view_defaults_to_mysuru(accounts: InMemoryAccounts, moon: InMemoryMoon) -> None:
    me = await _account(accounts)
    view = await GetMoonView(
        CITIES, moon, InMemoryNotifications(accounts), FixedClock(EVENING)
    ).execute(Principal(me))

    assert (view.city.slug, view.explicit, view.zone_known) == ("mysuru", False, True)
    assert view.days == [FULL]
    assert view.settings == DEFAULTS


async def test_choosing_a_city_and_its_zone(accounts: InMemoryAccounts) -> None:
    me = await _account(accounts, zone=None)

    chosen = await SetMoonLocation(CITIES, accounts).execute(Principal(me), "almaty")
    zoned = await UseCityTimezone(CITIES, accounts).execute(Principal(chosen), "almaty")
    back = await SetMoonLocation(CITIES, accounts).execute(Principal(zoned), "mysuru")

    assert chosen.moon_location == "almaty"
    assert zoned.timezone == "Asia/Almaty"
    assert back.moon_location is None  # the default is stored as "no choice"
    with pytest.raises(UnknownLocation):
        await SetMoonLocation(CITIES, accounts).execute(Principal(me), "atlantis")


async def test_city_zone_never_overwrites_a_known_zone(accounts: InMemoryAccounts) -> None:
    me = await _account(accounts, zone="Europe/Moscow")

    kept = await UseCityTimezone(CITIES, accounts).execute(Principal(me), "almaty")

    assert kept.timezone == "Europe/Moscow"


async def test_reminder_settings_are_validated(accounts: InMemoryAccounts) -> None:
    me = await _account(accounts)
    update = UpdateMoonReminders(InMemoryNotifications(accounts))

    saved = await update.execute(Principal(me), MoonPatch(offsets=frozenset({1})))

    assert saved.moon.offsets == {1}
    with pytest.raises(InvalidSettings):
        await update.execute(Principal(me), MoonPatch(offsets=frozenset({2})))


async def test_tick_sends_once_with_the_intro_first(
    accounts: InMemoryAccounts, moon: InMemoryMoon
) -> None:
    await _account(accounts)
    notifications, notifier = InMemoryNotifications(accounts), FakeNotifier()

    first = await _tick(accounts, moon, notifications, notifier).execute(BUDGET)
    again = await _tick(accounts, moon, notifications, notifier).execute(BUDGET)

    assert (first.sent, again.sent) == (1, 0)
    [(recipient, reminder)] = notifier.moon
    assert (recipient.telegram_id, recipient.locale) == ("42", "ru")
    assert (reminder.days_before, reminder.city.slug, reminder.intro) == (1, "mysuru", True)


async def test_tick_follows_the_chosen_city(accounts: InMemoryAccounts, moon: InMemoryMoon) -> None:
    me = await _account(accounts)
    await accounts.set_moon_location(me.id, "almaty")
    notifier = FakeNotifier()
    almaty_evening = send_instant(date(2026, 11, 5), time(19), "Asia/Almaty")

    result = await _tick(
        accounts, moon, InMemoryNotifications(accounts), notifier, almaty_evening
    ).execute(BUDGET)

    assert result.sent == 1
    assert notifier.moon[0][1].city.slug == "almaty"


async def test_no_zone_no_reminders(accounts: InMemoryAccounts, moon: InMemoryMoon) -> None:
    await _account(accounts, zone=None)
    notifier = FakeNotifier()

    await _tick(accounts, moon, InMemoryNotifications(accounts), notifier).execute(BUDGET)

    assert notifier.delivered == []


async def test_blocked_bot_pauses_and_rate_limit_stops(
    accounts: InMemoryAccounts, moon: InMemoryMoon
) -> None:
    await _account(accounts, "1")
    await _account(accounts, "2")
    notifications = InMemoryNotifications(accounts)
    notifier = FakeNotifier(
        [DeliveryResult(DeliveryStatus.BLOCKED), DeliveryResult(DeliveryStatus.RETRY_AFTER, 5)]
    )

    result = await _tick(accounts, moon, notifications, notifier).execute(BUDGET)

    assert (result.blocked, result.failed, result.stopped_early) == (1, 1, True)
    assert len(notifications.unreachable) == 1


async def test_failed_deliveries_are_retried_up_to_three_times(
    accounts: InMemoryAccounts, moon: InMemoryMoon
) -> None:
    await _account(accounts)
    notifications = InMemoryNotifications(accounts)
    failing = FakeNotifier([DeliveryResult(DeliveryStatus.FAILED)] * 5)

    attempts = [
        (await _tick(accounts, moon, notifications, failing).execute(BUDGET)).failed
        for _ in range(4)
    ]

    assert attempts == [1, 1, 1, 0]


async def test_reminders_off_means_nothing(accounts: InMemoryAccounts, moon: InMemoryMoon) -> None:
    me = await _account(accounts)
    notifications, notifier = InMemoryNotifications(accounts), FakeNotifier()
    await UpdateMoonReminders(notifications).execute(Principal(me), MoonPatch(offsets=frozenset()))

    await _tick(accounts, moon, notifications, notifier).execute(BUDGET)

    assert notifier.delivered == []


async def test_tick_tops_up_missing_and_outdated_calendars(accounts: InMemoryAccounts) -> None:
    moon = InMemoryMoon()
    years = calendar_years(EVENING.date())
    for city in CITIES.all:
        for year in years:
            moon.ledger[(city.slug, year)] = "test-1"
    moon.ledger[("almaty", years[0])] = "old-version"
    del moon.ledger[("mysuru", years[-1])]
    calculator = FakeCalculator()
    tick = RunTick(
        FixedClock(EVENING),
        CITIES,
        moon,
        calculator,
        InMemoryNotifications(accounts),
        FakeNotifier(),
    )

    result = await tick.execute(BUDGET)

    assert (result.computed, calculator.calls) == (2, 2)
    assert moon.ledger[("almaty", years[0])] == "test-1"


async def test_tick_respects_its_deadline(accounts: InMemoryAccounts) -> None:
    moon = InMemoryMoon()  # nothing computed yet
    tick = RunTick(
        FixedClock(EVENING),
        CITIES,
        moon,
        FakeCalculator(),
        InMemoryNotifications(accounts),
        FakeNotifier(),
    )

    result = await tick.execute(timedelta(0))  # no time at all

    assert (result.computed, result.stopped_early) == (0, True)


async def test_a_failed_send_does_not_use_up_a_cap_of_one(
    accounts: InMemoryAccounts, moon: InMemoryMoon
) -> None:
    me = await _account(accounts)
    notifications = InMemoryNotifications(accounts)
    await notifications.save(me.id, replace(DEFAULTS, daily_cap=1))
    notifier = FakeNotifier([DeliveryResult(DeliveryStatus.FAILED)])

    first = await _tick(accounts, moon, notifications, notifier).execute(BUDGET)
    retry = await _tick(accounts, moon, notifications, notifier).execute(BUDGET)

    assert (first.failed, retry.sent) == (1, 1)


async def test_out_of_time_mid_candidate_stops_before_claiming(
    accounts: InMemoryAccounts, moon: InMemoryMoon
) -> None:
    await _account(accounts)
    notifications = InMemoryNotifications(accounts)

    class SlowClock(FixedClock):
        def now(self) -> datetime:  # every look at the clock costs a minute
            self.instant += timedelta(minutes=1)
            return self.instant

    tick = RunTick(
        SlowClock(EVENING), CITIES, moon, FakeCalculator(), notifications, FakeNotifier()
    )
    result = await tick.execute(timedelta(minutes=2))

    assert result.stopped_early
    assert notifications.deliveries == {}  # nothing claimed that this run couldn't finish


async def test_intro_names_the_recipients_offsets_and_stays_until_sent(
    accounts: InMemoryAccounts, moon: InMemoryMoon
) -> None:
    me = await _account(accounts)
    notifications = InMemoryNotifications(accounts)
    await notifications.save(
        me.id, replace(DEFAULTS, moon=replace(DEFAULTS.moon, offsets=frozenset({3, 1})))
    )
    failing = FakeNotifier([DeliveryResult(DeliveryStatus.FAILED)])

    await _tick(accounts, moon, notifications, failing).execute(BUDGET)
    await _tick(accounts, moon, notifications, failing).execute(BUDGET)

    first, retried = (r for _, r in failing.moon)
    assert (first.intro, retried.intro) == (True, True)
    assert first.offsets == {3, 1}
