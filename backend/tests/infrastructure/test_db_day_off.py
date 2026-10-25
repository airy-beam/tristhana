"""The weekly day off on real Postgres (PR-09, ADR-0022): the bitmask, CHECKs, moon dates
with the day range in one statement, reminder days that follow, and migration 0007."""

import asyncio
import base64
from datetime import UTC, date, datetime
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from tristhana.application.ports.notifications import ReminderPatch
from tristhana.domain.accounts import IdentityKey, IdentityProvider, NewAccount
from tristhana.domain.days import DayLog, DayStatus
from tristhana.domain.moon import MoonDay, MoonDayKind
from tristhana.domain.notifications import DEFAULTS, StoredSettings
from tristhana.domain.rest_days import DayOff
from tristhana.infrastructure.crypto import FieldCipher
from tristhana.infrastructure.db import migrate
from tristhana.infrastructure.db.accounts import SqlAccountRepository, from_mask, to_mask
from tristhana.infrastructure.db.days import SqlDayLogRepository
from tristhana.infrastructure.db.moon import SqlMoonCalendarRepository
from tristhana.infrastructure.db.notifications import SqlNotificationRepository

pytestmark = pytest.mark.db

NOW = datetime(2026, 10, 25, 4, tzinfo=UTC)
SAT, SUN = frozenset({6}), frozenset({7})


async def _account(engine: AsyncEngine, user: str = "42") -> UUID:
    repo = SqlAccountRepository(engine)
    a = await repo.create_with_identity(
        IdentityKey(IdentityProvider.TELEGRAM, user), NewAccount(display_name="A", locale="ru")
    )
    await repo.set_timezone_if_unset(a.id, "Asia/Almaty")
    return a.id


def test_mask_round_trip() -> None:
    assert to_mask(frozenset()) == 0
    assert to_mask(SAT) == 32
    assert to_mask(None) is None
    for days in (frozenset[int](), SAT, SUN, frozenset({1, 7})):
        assert from_mask(to_mask(days)) == days


async def test_new_accounts_have_never_chosen_a_day_off(engine: AsyncEngine) -> None:
    me = await _account(engine)
    account = await SqlAccountRepository(engine).set_timezone_if_unset(me, "UTC")
    assert account.day_off == DayOff()
    assert account.day_off_dismissed is False
    assert account.created_at is not None


async def test_set_day_off_round_trips_the_period(engine: AsyncEngine) -> None:
    me = await _account(engine)
    repo = SqlAccountRepository(engine)
    off = DayOff(SUN, date(2026, 10, 25), SAT)
    assert (await repo.set_day_off(me, off)).day_off == off
    assert (await repo.set_day_off(me, DayOff(frozenset()))).day_off == DayOff(frozenset())


@pytest.mark.parametrize(
    "values",
    [
        "day_off = 128",
        "day_off = 32, day_off_before = 64",  # an earlier value needs its change date
        "day_off = NULL, day_off_since = '2026-10-25', day_off_before = 32",
    ],
)
async def test_checks_refuse_broken_day_off_rows(engine: AsyncEngine, values: str) -> None:
    me = await _account(engine)
    with pytest.raises(IntegrityError):
        async with engine.connect() as conn:
            await conn.execute(
                text(f"UPDATE tristhana.account SET {values} WHERE id = :id"),  # noqa: S608  # fixed test values
                {"id": me},
            )


async def test_dismiss_keeps_the_first_time(engine: AsyncEngine) -> None:
    me = await _account(engine)
    repo = SqlAccountRepository(engine)
    await repo.dismiss_day_off_question(me)
    async with engine.connect() as conn:
        first = (
            await conn.execute(
                text("SELECT day_off_dismissed_at FROM tristhana.account WHERE id = :id"),
                {"id": me},
            )
        ).scalar_one()
    await repo.dismiss_day_off_question(me)
    async with engine.connect() as conn:
        again = (
            await conn.execute(
                text("SELECT day_off_dismissed_at FROM tristhana.account WHERE id = :id"),
                {"id": me},
            )
        ).scalar_one()
    assert first is not None
    assert again == first


async def test_range_with_moon_returns_logs_and_moon_dates(engine: AsyncEngine) -> None:
    me = await _account(engine)
    days = SqlDayLogRepository(engine, FieldCipher("1:" + base64.b64encode(bytes(32)).decode()))
    moon = SqlMoonCalendarRepository(engine)
    await moon.replace_year(
        "mysuru",
        2026,
        [
            MoonDay(date(2026, 10, 21), MoonDayKind.AMAVASYA),
            MoonDay(date(2026, 11, 5), MoonDayKind.PURNIMA),
        ],
        "v1",
    )
    start, end = date(2026, 10, 19), date(2026, 10, 25)
    empty = await days.range_with_moon(me, start, end, "mysuru")
    assert empty.days == []
    assert empty.moon_dates == {date(2026, 10, 21)}
    await days.upsert(me, DayLog(date(2026, 10, 21), DayStatus.PRACTICED), "Asia/Almaty")
    view = await days.range_with_moon(me, start, end, "mysuru")
    assert view.days == [DayLog(date(2026, 10, 21), DayStatus.PRACTICED)]
    assert view.moon_dates == {date(2026, 10, 21)}
    assert (await days.range_with_moon(me, start, end, "almaty")).moon_dates == frozenset()


async def test_candidates_follow_each_accounts_day_off(engine: AsyncEngine) -> None:
    me = await _account(engine)
    await SqlAccountRepository(engine).set_day_off(me, DayOff(SUN))
    repo = SqlNotificationRepository(engine)
    await repo.patch_practice(me, ReminderPatch(on=True), DEFAULTS)
    [candidate] = await repo.candidates(NOW, NOW.date(), DEFAULTS)
    assert candidate.settings.practice.days == frozenset({1, 2, 3, 4, 5, 6})


async def test_0007_nulls_default_reminder_days_and_keeps_custom_ones(
    migrated_url: str, engine: AsyncEngine
) -> None:
    me = await _account(engine)
    other = await _account(engine, "43")
    await asyncio.to_thread(migrate.downgrade, migrated_url, "0006")
    try:
        async with engine.connect() as conn:
            for account_id, days in ((me, [1, 2, 3, 4, 5, 7]), (other, [1, 2, 3, 4, 5, 6])):
                await conn.execute(
                    text(
                        "INSERT INTO tristhana.notification_settings (account_id, practice_days) "
                        "VALUES (:id, :days)"
                    ),
                    {"id": account_id, "days": days},
                )
    finally:
        await asyncio.to_thread(migrate.upgrade, migrated_url)
    repo = SqlNotificationRepository(engine)
    assert await repo.stored_row(me) == StoredSettings()  # Sun-Fri reads the same as before
    assert (await repo.settings(me, DEFAULTS)).practice.days == frozenset({1, 2, 3, 4, 5, 7})
    # No day off is inferred from the stored days.
    accounts = SqlAccountRepository(engine)
    assert (await accounts.set_timezone_if_unset(other, "UTC")).day_off == DayOff()


async def test_0008_clears_custom_reminder_days(migrated_url: str, engine: AsyncEngine) -> None:
    me = await _account(engine)
    await asyncio.to_thread(migrate.downgrade, migrated_url, "0007")
    try:
        async with engine.connect() as conn:
            await conn.execute(
                text(
                    "INSERT INTO tristhana.notification_settings (account_id, practice_days) "
                    "VALUES (:id, :days)"
                ),
                {"id": me, "days": [1, 3, 5]},
            )
    finally:
        await asyncio.to_thread(migrate.upgrade, migrated_url)
    async with engine.connect() as conn:
        stored = (
            await conn.execute(
                text(
                    "SELECT practice_days FROM tristhana.notification_settings"
                    " WHERE account_id = :id"
                ),
                {"id": me},
            )
        ).scalar_one()
    assert stored is None
