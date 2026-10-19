"""Settings on real Postgres (ID-06, ADR-0021): chosen name/locale survive a racing refresh,
partial writes, and migration 0006's data steps."""

import asyncio
from datetime import UTC, datetime, time

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from tristhana.domain.accounts import (
    IdentityKey,
    IdentityProvider,
    NewAccount,
    ProfileChange,
    ProfileUpdate,
)
from tristhana.domain.notifications import DEFAULTS, NotificationPatch, StoredSettings
from tristhana.infrastructure.db import migrate
from tristhana.infrastructure.db.accounts import SqlAccountRepository
from tristhana.infrastructure.db.notifications import SqlNotificationRepository

pytestmark = pytest.mark.db

NOW = datetime(2026, 10, 19, 5, tzinfo=UTC)


async def _account(engine: AsyncEngine, user: str = "42"):
    return await SqlAccountRepository(engine).create_with_identity(
        IdentityKey(IdentityProvider.TELEGRAM, user), NewAccount(display_name="Ash", locale="en")
    )


async def test_a_refresh_never_undoes_a_choice_made_in_settings(engine: AsyncEngine) -> None:
    me = await _account(engine)
    repo = SqlAccountRepository(engine)

    chosen = await repo.update_settings(
        me.id, ProfileChange("Ашенька", True, "ru", True, "Asia/Almaty")
    )
    # A Telegram refresh computed before the choice lands afterwards.
    refreshed = await repo.update_profile(me.id, ProfileUpdate("Telegram Ash", "en"), NOW)

    assert (chosen.name_custom, chosen.locale_custom, chosen.timezone) == (
        True,
        True,
        "Asia/Almaty",
    )
    assert (refreshed.display_name, refreshed.locale) == ("Ашенька", "ru")


async def test_back_to_telegram_lets_refreshes_through_again(engine: AsyncEngine) -> None:
    me = await _account(engine)
    repo = SqlAccountRepository(engine)
    await repo.update_settings(me.id, ProfileChange("X", True, "ru", True, None))

    await repo.update_settings(me.id, ProfileChange("Ash", False, "ru", False, None))
    refreshed = await repo.update_profile(me.id, ProfileUpdate("New Telegram", "en"), NOW)

    assert (refreshed.display_name, refreshed.locale) == ("New Telegram", "en")


async def test_patch_writes_only_the_sent_columns(engine: AsyncEngine) -> None:
    me = await _account(engine)
    repo = SqlNotificationRepository(engine)
    await repo.patch(
        me.id, NotificationPatch(practice_on=True, practice_at=time(18)).columns(), DEFAULTS
    )

    saved = await repo.patch(
        me.id, NotificationPatch(moon_offsets=frozenset({7, 3})).columns(), DEFAULTS
    )
    reset = await repo.patch(me.id, NotificationPatch(moon_offsets=None).columns(), DEFAULTS)

    assert (saved.moon.offsets, saved.practice.on, saved.practice.at) == ({7, 3}, True, time(18))
    assert reset.moon.offsets == DEFAULTS.moon.offsets
    assert await repo.stored_row(me.id) == StoredSettings(practice_on=True, practice_at=time(18))


async def test_concurrent_partial_writes_both_land(engine: AsyncEngine) -> None:
    me = await _account(engine)
    repo = SqlNotificationRepository(engine)

    await asyncio.gather(
        repo.patch(me.id, {"moon_at": time(7)}, DEFAULTS),
        repo.patch(me.id, {"practice_on": True}, DEFAULTS),
    )

    stored = await repo.stored_row(me.id)
    assert (stored.moon_at, stored.practice_on) == (time(7), True)


async def test_0006_backfills_the_intro_and_nulls_frozen_defaults(
    migrated_url: str, engine: AsyncEngine
) -> None:
    me = await _account(engine)
    other = await _account(engine, "43")
    await SqlAccountRepository(engine).set_timezone_if_unset(me.id, "Asia/Almaty")
    await asyncio.to_thread(migrate.downgrade, migrated_url, "0005")
    try:
        async with engine.connect() as conn:
            await conn.execute(
                text(
                    "INSERT INTO tristhana.notification_settings "
                    "(account_id, moon_offsets, moon_at, quiet_start, quiet_end, daily_cap) "
                    "VALUES (:id, '{1,7}', '19:00', '22:00', '07:00', 3)"
                ),
                {"id": me.id},
            )
            await conn.execute(
                text(
                    "INSERT INTO tristhana.notification_settings "
                    "(account_id, moon_offsets, moon_at, quiet_start, quiet_end, daily_cap) "
                    "VALUES (:id, '{3}', '07:00', '23:00', '07:00', 5)"
                ),
                {"id": other.id},
            )
            await conn.execute(
                text(
                    "INSERT INTO tristhana.notification_delivery "
                    "(account_id, dedupe_key, category, local_date, status) "
                    "VALUES (:id, 'moon:2026-11-05:1', 'moon', '2026-11-04', 'sent')"
                ),
                {"id": me.id},
            )
    finally:
        await asyncio.to_thread(migrate.upgrade, migrated_url)

    repo = SqlNotificationRepository(engine)
    assert await repo.stored_row(me.id) == StoredSettings()  # all back to "the default"
    assert await repo.settings(me.id, DEFAULTS) == DEFAULTS  # nothing changed in effect
    custom = await repo.stored_row(other.id)  # chosen values stay exactly as they were
    assert (custom.moon_offsets, custom.moon_at, custom.daily_cap) == ({3}, time(7), 5)
    assert (custom.quiet_start, custom.quiet_end) == (time(23), time(7))
    [candidate] = await repo.candidates(NOW, NOW.date(), DEFAULTS)
    assert candidate.had_moon_reminder is True  # backfilled from the delivery (Q24)


async def test_two_settings_saves_at_once_both_land(engine: AsyncEngine) -> None:
    """A name and a language saved at the same moment from stale snapshots."""
    me = await _account(engine)
    repo = SqlAccountRepository(engine)

    await asyncio.gather(
        repo.update_settings(
            me.id, ProfileChange("Anna", True, "en", False, None, frozenset({"name"}))
        ),
        repo.update_settings(
            me.id, ProfileChange("Ash", False, "ru", True, None, frozenset({"locale"}))
        ),
    )

    found = await repo.find_by_identity(IdentityKey(IdentityProvider.TELEGRAM, "42"))
    assert found is not None
    assert (found.display_name, found.name_custom, found.locale, found.locale_custom) == (
        "Anna",
        True,
        "ru",
        True,
    )
