"""GetYearStats on fakes: the year window, defaults, moon markers, InvalidYear."""

from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from tests.fakes import FixedClock, InMemoryAccounts, InMemoryDays, InMemoryMoon, practice_use_cases
from tristhana.application.policies import Principal
from tristhana.application.stats import GetYearStats, InvalidYear
from tristhana.domain.accounts import Account, IdentityKey, IdentityProvider, NewAccount
from tristhana.domain.days import DayLog, DayStatus
from tristhana.domain.moon import MoonDay, MoonDayKind
from tristhana.infrastructure.seed.cities_yaml import load_cities

CITIES = load_cities(Path(__file__).resolve().parents[3] / "data" / "seed" / "cities.yaml")
NOW = datetime(2026, 10, 19, 5, tzinfo=UTC)


async def _me(accounts: InMemoryAccounts, zone: str | None = "Asia/Almaty") -> Account:
    a = await accounts.create_with_identity(
        IdentityKey(IdentityProvider.TELEGRAM, "42"), NewAccount(display_name="A", locale="ru")
    )
    return await accounts.set_timezone_if_unset(a.id, zone) if zone else a


def _use_case(days: InMemoryDays, moon: InMemoryMoon, now: datetime = NOW) -> GetYearStats:
    catalog = practice_use_cases().catalog
    return GetYearStats(days, moon, CITIES, catalog, FixedClock(now))


async def test_defaults_to_the_local_current_year_with_moon_markers() -> None:
    accounts, days, moon = InMemoryAccounts(), InMemoryDays(), InMemoryMoon()
    me = await _me(accounts)
    days.rows[(me.id, date(2025, 3, 2))] = (DayLog(date(2025, 3, 2), DayStatus.PRACTICED), None)
    days.rows[(me.id, date(2026, 10, 18))] = (DayLog(date(2026, 10, 18), DayStatus.PRACTICED), None)
    moon.days_by_location["mysuru"] = [
        MoonDay(date(2026, 10, 25), MoonDayKind.PURNIMA),  # future: still a marker
        MoonDay(date(2025, 12, 30), MoonDayKind.AMAVASYA),  # another year
    ]

    view = await _use_case(days, moon).execute(Principal(me))

    assert (view.year, view.today, view.first_year) == (2026, date(2026, 10, 19), 2025)
    assert view.city.slug == "mysuru"
    assert [d.date for d in view.moon_days] == [date(2026, 10, 25)]
    assert len(view.stats.cells) == (date(2026, 10, 19) - date(2026, 1, 1)).days + 1
    assert view.stats.current_run == 1


async def test_follows_the_chosen_city_and_works_with_a_provisional_zone() -> None:
    accounts, days, moon = InMemoryAccounts(), InMemoryDays(), InMemoryMoon()
    me = replace(await _me(accounts, zone=None), moon_location="almaty")
    moon.days_by_location["almaty"] = [MoonDay(date(2026, 10, 25), MoonDayKind.PURNIMA)]

    view = await _use_case(days, moon).execute(Principal(me))

    assert not view.timezone_known
    assert view.city.slug == "almaty"
    assert view.first_year is None


@pytest.mark.parametrize("year", [1999, 2027])
async def test_invalid_year(year: int) -> None:
    accounts = InMemoryAccounts()
    me = await _me(accounts)

    with pytest.raises(InvalidYear):
        await _use_case(InMemoryDays(), InMemoryMoon()).execute(Principal(me), year)


@pytest.mark.parametrize(
    ("zone", "year", "next_ok"),
    [("Pacific/Kiritimati", 2027, True), ("Pacific/Honolulu", 2026, False)],
)
async def test_the_year_follows_the_account_zone(zone: str, year: int, next_ok: bool) -> None:
    accounts = InMemoryAccounts()
    me = await _me(accounts, zone)
    use_case = _use_case(InMemoryDays(), InMemoryMoon(), datetime(2026, 12, 31, 12, tzinfo=UTC))

    assert (await use_case.execute(Principal(me))).year == year
    if next_ok:
        assert (await use_case.execute(Principal(me), 2027)).year == 2027
    else:
        with pytest.raises(InvalidYear):
            await use_case.execute(Principal(me), 2027)


async def test_year_zero_is_invalid_not_the_current_year() -> None:
    me = await _me(InMemoryAccounts())

    with pytest.raises(InvalidYear):
        await _use_case(InMemoryDays(), InMemoryMoon()).execute(Principal(me), 0)
