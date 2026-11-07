"""An explicit Mysuru choice is stored as its slug (ID-04 spec §7, ADR-0030), so "chose Mysuru"
differs from "never chose" for MD-02. To everything else `"mysuru"` and NULL are one city."""

from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta

import pytest

from tests.domain.test_practice import catalog
from tests.fakes import (
    FakeCalculator,
    FakeNotifier,
    FakePacker,
    FixedClock,
    InMemoryAccounts,
    InMemoryDays,
    InMemoryExport,
    InMemoryMoon,
    InMemoryNotifications,
    cities,
    practice_use_cases,
)
from tristhana.application.days import GetDays
from tristhana.application.export import SendMyExport
from tristhana.application.labels import PracticeLabels
from tristhana.application.moon import GetMoonView, SetMoonLocation, UnknownLocation
from tristhana.application.policies import Principal
from tristhana.application.stats import GetYearStats
from tristhana.application.tick import RunTick
from tristhana.domain.accounts import Account, IdentityKey, IdentityProvider, NewAccount
from tristhana.domain.moon import MoonDay, MoonDayKind, calendar_years
from tristhana.domain.notifications import send_instant
from tristhana.domain.progression import Track
from tristhana.domain.rest_days import AutoDay, AutoKind
from tristhana.infrastructure.i18n.fluent import FluentTranslator

ZONE = "Asia/Almaty"
FULL = MoonDay(date(2026, 11, 5), MoonDayKind.PURNIMA)
EVENING = send_instant(date(2026, 11, 4), time(19), ZONE)  # the evening before the full moon
BOTH = pytest.mark.parametrize("stored", [None, "mysuru"])


async def _account(accounts: InMemoryAccounts, stored: str | None = None) -> Account:
    created = await accounts.create_with_identity(
        IdentityKey(IdentityProvider.TELEGRAM, "42"), NewAccount(display_name="A", locale="en")
    )
    account = replace(
        created,
        timezone=ZONE,
        moon_location=stored,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    accounts.accounts[account.id] = account
    return account


def _moon() -> InMemoryMoon:
    return InMemoryMoon({"mysuru": [FULL]})


async def test_choosing_mysuru_stores_its_slug() -> None:
    accounts = InMemoryAccounts()
    me = await _account(accounts, "almaty")

    chosen = await SetMoonLocation(cities(), accounts).execute(Principal(me), "mysuru")

    assert chosen.moon_location == "mysuru"
    assert accounts.accounts[me.id].moon_location == "mysuru"


async def test_none_stores_null_and_reads_as_never_chosen() -> None:
    accounts = InMemoryAccounts()
    me = await _account(accounts, "almaty")

    back = await SetMoonLocation(cities(), accounts).execute(Principal(me), None)

    assert back.moon_location is None
    view = await GetMoonView(
        cities(), _moon(), InMemoryNotifications(accounts), FixedClock(EVENING)
    ).execute(Principal(back))
    assert (view.city.slug, view.explicit) == ("mysuru", False)


async def test_a_chosen_mysuru_reads_as_explicit() -> None:
    accounts = InMemoryAccounts()
    me = await _account(accounts)

    chosen = await SetMoonLocation(cities(), accounts).execute(Principal(me), "mysuru")

    view = await GetMoonView(
        cities(), _moon(), InMemoryNotifications(accounts), FixedClock(EVENING)
    ).execute(Principal(chosen))
    assert (view.city.slug, view.explicit) == ("mysuru", True)


async def test_an_unknown_slug_raises_and_stores_nothing() -> None:
    accounts = InMemoryAccounts()
    me = await _account(accounts, "almaty")

    with pytest.raises(UnknownLocation):
        await SetMoonLocation(cities(), accounts).execute(Principal(me), "atlantis")

    assert accounts.accounts[me.id].moon_location == "almaty"


# `"mysuru"` and NULL are the same city to every other reader (spec §7's table).


@BOTH
async def test_auto_rest_is_the_same(stored: str | None) -> None:
    accounts, moon = InMemoryAccounts(), _moon()
    me = await _account(accounts, stored)
    days = InMemoryDays(moon=moon)

    view = await GetDays(days, cities(), FixedClock(EVENING + timedelta(days=2))).execute(
        Principal(me), date(2026, 11, 1), date(2026, 11, 6)
    )

    assert view.city.slug == "mysuru"
    assert view.auto == {FULL.date: AutoDay(AutoKind.MOON)}


@BOTH
async def test_stats_are_the_same(stored: str | None) -> None:
    accounts, moon = InMemoryAccounts(), _moon()
    me = await _account(accounts, stored)
    stats = GetYearStats(
        InMemoryDays(), moon, cities(), practice_use_cases().catalog, FixedClock(EVENING)
    )

    view = await stats.execute(Principal(me))

    assert view.city.slug == "mysuru"
    assert [d.date for d in view.moon_days] == [FULL.date]


@BOTH
async def test_reminders_are_the_same(stored: str | None) -> None:
    accounts, moon = InMemoryAccounts(), _moon()
    await _account(accounts, stored)
    for city in cities().all:  # calendars already computed
        for year in calendar_years(EVENING.date()):
            moon.ledger[(city.slug, year)] = FakeCalculator.version
    notifier = FakeNotifier()
    tick = RunTick(
        FixedClock(EVENING),
        cities(),
        moon,
        FakeCalculator(),
        InMemoryNotifications(accounts),
        notifier,
    )

    result = await tick.execute(timedelta(seconds=40))

    assert result.sent == 1
    [(_, reminder)] = notifier.moon
    assert (reminder.city.slug, reminder.moon_day) == ("mysuru", FULL)


async def test_the_export_says_mysuru_is_no_default_once_chosen() -> None:
    clock = FixedClock(EVENING)
    accounts = InMemoryAccounts(clock=clock)
    me = await _account(accounts, "mysuru")
    packer = FakePacker()
    t = FluentTranslator()
    export = SendMyExport(
        InMemoryExport(accounts),
        packer,
        FakeNotifier(),
        t,
        PracticeLabels(t, catalog(), Track(catalog())),
        cities(),
        "cat-v1",
        clock,
    )

    await export.execute(Principal(me))

    [(data, _, _)] = packer.packed
    assert data["account"]["moon_city"] == {"slug": "mysuru", "default": False}  # type: ignore[index]
