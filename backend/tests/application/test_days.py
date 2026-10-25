from dataclasses import replace
from datetime import UTC, date, datetime
from uuid import uuid4

import pytest

from tests.fakes import FixedClock, InMemoryDays, InMemoryMoon, cities
from tristhana.application.days import ClearDayStatus, GetDays, SetDayStatus
from tristhana.application.policies import Principal
from tristhana.domain.accounts import Account
from tristhana.domain.days import DateInFuture, DayLog, DayStatus, InvalidRange
from tristhana.domain.locale import Locale
from tristhana.domain.moon import MoonDay, MoonDayKind
from tristhana.domain.rest_days import AutoDay, AutoKind, DayOff

# 20:00 UTC: already Oct 19 in Almaty (UTC+5), still Oct 18 in Moscow (UTC+3) and UTC.
NOW = datetime(2026, 10, 18, 20, 0, tzinfo=UTC)


def _principal(timezone: str | None = "Asia/Almaty", locale: Locale = "ru") -> Principal:
    account = Account(
        id=uuid4(),
        display_name="Аня",
        locale=locale,
        timezone=timezone,
        last_seen_at=NOW,  # type: ignore[arg-type]
    )
    return Principal(account)


@pytest.fixture
def repo() -> InMemoryDays:
    return InMemoryDays()


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(NOW)


async def test_today_uses_the_account_zone(repo: InMemoryDays, clock: FixedClock) -> None:
    view = await GetDays(repo, cities(), clock).execute(_principal("Asia/Almaty"))

    assert (view.today, view.timezone_known) == (date(2026, 10, 19), True)


@pytest.mark.parametrize(
    ("locale", "today"), [("ru", date(2026, 10, 18)), ("en", date(2026, 10, 18))]
)
async def test_unknown_zone_uses_a_provisional_guess(
    repo: InMemoryDays, clock: FixedClock, locale: Locale, today: date
) -> None:
    view = await GetDays(repo, cities(), clock).execute(_principal(None, locale))

    assert (view.today, view.timezone_known) == (today, False)


async def test_set_today_yesterday_and_overwrite(repo: InMemoryDays, clock: FixedClock) -> None:
    me = _principal()
    set_status = SetDayStatus(repo, clock)

    await set_status.execute(me, date(2026, 10, 19), DayStatus.PRACTICED)
    await set_status.execute(me, date(2026, 10, 18), DayStatus.MOON)
    await set_status.execute(me, date(2026, 10, 19), DayStatus.LADIES)

    view = await GetDays(repo, cities(), clock).execute(me)
    assert view.days == [
        DayLog(date(2026, 10, 18), DayStatus.MOON),
        DayLog(date(2026, 10, 19), DayStatus.LADIES),
    ]


async def test_future_dates_are_refused(repo: InMemoryDays, clock: FixedClock) -> None:
    with pytest.raises(DateInFuture):
        await SetDayStatus(repo, clock).execute(_principal(), date(2026, 10, 20), DayStatus.REST)


async def test_unknown_zone_never_blocks_a_real_today(
    repo: InMemoryDays, clock: FixedClock
) -> None:
    # The guess (Moscow) says Oct 18, but the person may really be in Almaty (Oct 19).
    me = _principal(None)

    await SetDayStatus(repo, clock).execute(me, date(2026, 10, 19), DayStatus.PRACTICED)

    [(_, zone)] = repo.rows.values()
    assert zone is None  # the guess is never stored


async def test_clear_is_idempotent(repo: InMemoryDays, clock: FixedClock) -> None:
    me = _principal()
    await SetDayStatus(repo, clock).execute(me, date(2026, 10, 19), DayStatus.REST)

    await ClearDayStatus(repo).execute(me, date(2026, 10, 19))
    await ClearDayStatus(repo).execute(me, date(2026, 10, 19))

    assert repo.rows == {}


async def test_days_are_per_account(repo: InMemoryDays, clock: FixedClock) -> None:
    await SetDayStatus(repo, clock).execute(_principal(), date(2026, 10, 19), DayStatus.REST)

    assert (await GetDays(repo, cities(), clock).execute(_principal())).days == []


async def test_range_is_validated(repo: InMemoryDays, clock: FixedClock) -> None:
    with pytest.raises(InvalidRange):
        await GetDays(repo, cities(), clock).execute(
            _principal(), date(2026, 10, 19), date(2026, 10, 1)
        )


# PR-09: auto-rest (ADR-0022). Oct 19, 2026 is a Monday in Almaty.


async def test_auto_rest_fills_only_unlogged_days_since_joining(clock: FixedClock) -> None:
    moon = InMemoryMoon({"mysuru": [MoonDay(date(2026, 10, 15), MoonDayKind.AMAVASYA)]})
    repo = InMemoryDays(moon=moon)
    base = _principal().account
    account = replace(
        base,
        created_at=datetime(2026, 10, 9, 12, tzinfo=UTC),  # a Friday
        day_off=DayOff(frozenset({6})),
    )
    await repo.upsert(account.id, DayLog(date(2026, 10, 17), DayStatus.PRACTICED), "Asia/Almaty")
    view = await GetDays(repo, cities(), clock).execute(
        Principal(account), date(2026, 10, 1), date(2026, 10, 19)
    )
    assert view.city.slug == "mysuru"
    assert view.auto == {
        date(2026, 10, 10): AutoDay(AutoKind.DAY_OFF),  # Sat after joining
        date(2026, 10, 15): AutoDay(AutoKind.MOON),
        # Oct 3 (before joining) and Oct 17 (practised) are not auto days
    }


async def test_followed_city_moon_days_drive_auto_rest(clock: FixedClock) -> None:
    moon = InMemoryMoon(
        {
            "mysuru": [MoonDay(date(2026, 10, 15), MoonDayKind.AMAVASYA)],
            "almaty": [MoonDay(date(2026, 10, 14), MoonDayKind.AMAVASYA)],
        }
    )
    account = replace(_principal().account, moon_location="almaty")
    view = await GetDays(InMemoryDays(moon=moon), cities(), clock).execute(
        Principal(account), date(2026, 10, 13), date(2026, 10, 16)
    )
    assert view.auto == {date(2026, 10, 14): AutoDay(AutoKind.MOON)}
