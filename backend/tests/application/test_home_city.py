"""MD-04 + ID-06 use cases: the home city in settings, the moon view and a shared location."""

import logging
from dataclasses import dataclass, field, replace
from datetime import date, time

import pytest

from tests.fakes import FixedClock, InMemoryAccounts, InMemoryMoon, InMemoryNotifications, cities
from tristhana.application.moon import GetMoonView, MoonView
from tristhana.application.policies import Principal
from tristhana.application.settings import UpdateProfile, ZoneFromLocation
from tristhana.domain.accounts import (
    NOT_LISTED,
    Account,
    ExternalProfile,
    IdentityKey,
    IdentityProvider,
    NewAccount,
    ProfilePatch,
    UnknownCity,
)
from tristhana.domain.moon import MoonDay, MoonDayKind
from tristhana.domain.notifications import send_instant

KEY = IdentityKey(IdentityProvider.TELEGRAM, "42")
TG = ExternalProfile(KEY, "Ash", "en")
NOW = send_instant(date(2026, 10, 20), time(9), "Asia/Almaty")
P, A = MoonDayKind.PURNIMA, MoonDayKind.AMAVASYA


async def _me(accounts: InMemoryAccounts, zone: str | None = "Asia/Almaty") -> Account:
    me = await accounts.create_with_identity(KEY, NewAccount("Ash", "en"))
    return await accounts.set_timezone_if_unset(me.id, zone) if zone else me


async def test_picking_astana_stores_astana_and_its_zone() -> None:
    accounts = InMemoryAccounts()
    me = await _me(accounts, zone=None)

    saved = await UpdateProfile(accounts, cities()).execute(
        Principal(me), ProfilePatch(home_city="astana"), TG
    )

    assert (saved.home_city, saved.timezone) == ("astana", "Asia/Almaty")
    assert accounts.writes == 2  # the create, then one settings write


async def test_travel_clears_the_city_and_an_unknown_city_is_refused() -> None:
    accounts = InMemoryAccounts()
    me = await _me(accounts)
    update = UpdateProfile(accounts, cities())
    astana = await update.execute(Principal(me), ProfilePatch(home_city="astana"), TG)

    away = await update.execute(Principal(astana), ProfilePatch(timezone="Asia/Bangkok"), TG)

    assert (away.home_city, away.timezone) == (NOT_LISTED, "Asia/Bangkok")
    with pytest.raises(UnknownCity):
        await update.execute(Principal(away), ProfilePatch(home_city="atlantis"), TG)


# The moon view: the home city's calendar comes back in the same statement.


def _moon() -> InMemoryMoon:
    moon = InMemoryMoon()
    moon.days_by_location["mysuru"] = [
        MoonDay(date(2026, 10, 26), P),
        MoonDay(date(2026, 11, 9), A),
        MoonDay(date(2026, 12, 19), P),  # outside the asked window
    ]
    moon.days_by_location["almaty"] = [
        MoonDay(date(2026, 10, 25), P),  # a day earlier
        MoonDay(date(2026, 11, 9), A),  # the same day
    ]
    return moon


async def _view(account: Account, moon: InMemoryMoon, accounts: InMemoryAccounts) -> MoonView:
    view = GetMoonView(cities(), moon, InMemoryNotifications(accounts), FixedClock(NOW))
    return await view.execute(Principal(account), date(2026, 10, 26), date(2026, 11, 30))


async def test_the_view_pairs_the_home_city_in_one_statement() -> None:
    accounts, moon = InMemoryAccounts(), _moon()
    me = replace(await _me(accounts), home_city="almaty")

    view = await _view(me, moon, accounts)

    assert view.home is not None
    assert view.home.slug == "almaty"
    assert [d.date for d in view.days] == [date(2026, 10, 26), date(2026, 11, 9)]
    assert view.home_dates == {date(2026, 10, 26): date(2026, 10, 25)}
    assert moon.statements == 1


@pytest.mark.parametrize(
    ("home", "moon_location", "zone"),
    [
        (None, None, "Asia/Almaty"),  # never chosen
        (NOT_LISTED, None, "Asia/Almaty"),
        ("mysuru", None, "Asia/Kolkata"),  # the followed city itself
        ("almaty", "almaty", "Asia/Almaty"),
        ("almaty", None, "Asia/Bangkok"),  # a stale city outside its zone
    ],
)
async def test_no_fyi_without_another_home_city(
    home: str | None, moon_location: str | None, zone: str
) -> None:
    accounts, moon = InMemoryAccounts(), _moon()
    me = replace(await _me(accounts), home_city=home, moon_location=moon_location, timezone=zone)

    view = await _view(me, moon, accounts)

    assert (view.home, view.home_dates) == (None, {})
    assert moon.statements == 1


# A shared location: the zone only; the coordinates are never kept or logged.


@dataclass
class FakeZoneLookup:
    zone: str | None
    asked: list[tuple[float, float]] = field(default_factory=list[tuple[float, float]])

    async def zone_at(self, lat: float, lon: float) -> str | None:
        self.asked.append((lat, lon))
        return self.zone


async def test_a_location_sets_the_zone_and_answers_the_city_question(
    caplog: pytest.LogCaptureFixture,
) -> None:
    accounts = InMemoryAccounts()
    me = replace(await _me(accounts), home_city="almaty")
    accounts.accounts[me.id] = me
    lookup = FakeZoneLookup("Asia/Bangkok")

    with caplog.at_level(logging.INFO):
        saved = await ZoneFromLocation(lookup, UpdateProfile(accounts, cities())).execute(
            Principal(me), 13.7563, 100.5018, TG
        )

    assert saved is not None
    assert (saved.timezone, saved.home_city) == ("Asia/Bangkok", NOT_LISTED)
    assert "found=True" in caplog.text
    assert "13.75" not in caplog.text
    assert "100.50" not in caplog.text


@pytest.mark.parametrize("zone", [None, "Etc/GMT-7"])  # open sea: nothing, or a fixed offset
async def test_no_zone_at_a_location_writes_nothing(zone: str | None) -> None:
    accounts = InMemoryAccounts()
    me = await _me(accounts)
    writes = accounts.writes

    saved = await ZoneFromLocation(FakeZoneLookup(zone), UpdateProfile(accounts, cities())).execute(
        Principal(me), 0.0, -30.0, TG
    )

    assert saved is None
    assert accounts.writes == writes
