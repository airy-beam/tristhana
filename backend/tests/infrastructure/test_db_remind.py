"""PR-10 on real Postgres: practice settings, candidates with logged days, the never-
overwriting quick log, and "same as last time" preferring a non-Led practice."""

import base64
from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from tristhana.application.ports.notifications import ReminderPatch
from tristhana.application.practice_patch import PracticePatch
from tristhana.domain.accounts import IdentityKey, IdentityProvider, NewAccount
from tristhana.domain.days import DayLog, DayStatus
from tristhana.domain.notifications import DEFAULTS
from tristhana.domain.practice import PracticeContext, PracticeLength
from tristhana.infrastructure.crypto import FieldCipher
from tristhana.infrastructure.db.accounts import SqlAccountRepository
from tristhana.infrastructure.db.days import SqlDayLogRepository
from tristhana.infrastructure.db.notifications import SqlNotificationRepository
from tristhana.infrastructure.db.practice import SqlPracticeRepository

pytestmark = pytest.mark.db

KEYS = "1:" + base64.b64encode(b"\x07" * 32).decode()
NOW = datetime(2026, 10, 19, 5, tzinfo=UTC)
MON = date(2026, 10, 19)
ZONE = "Asia/Almaty"


async def _account(engine: AsyncEngine, user: str = "42", zone: str | None = ZONE) -> UUID:
    repo = SqlAccountRepository(engine)
    account = await repo.create_with_identity(
        IdentityKey(IdentityProvider.TELEGRAM, user), NewAccount(display_name="A", locale="ru")
    )
    if zone:
        await repo.set_timezone_if_unset(account.id, zone)
    return account.id


async def test_practice_settings_default_patch_and_save(engine: AsyncEngine) -> None:
    me = await _account(engine)
    repo = SqlNotificationRepository(engine)

    assert (await repo.settings(me, DEFAULTS)).practice == DEFAULTS.practice
    on = await repo.patch_practice(me, ReminderPatch(on=True), DEFAULTS)
    sun_off = await repo.patch_practice(
        me, ReminderPatch(days=frozenset({1, 2, 3, 4, 5, 6}), at=time(20)), DEFAULTS
    )

    assert on.practice.on is True
    assert on.practice.at == DEFAULTS.practice.at  # NULL column = the default
    assert (sun_off.practice.on, sun_off.practice.at) == (True, time(20))
    assert sun_off.practice.days == {1, 2, 3, 4, 5, 6}
    saved = await repo.save(me, replace(sun_off, practice=replace(sun_off.practice, on=False)))
    assert await repo.settings(me, DEFAULTS) == saved


async def test_candidates_include_practice_only_accounts_with_their_logged_days(
    engine: AsyncEngine,
) -> None:
    practising = await _account(engine, "1")
    moon_only = await _account(engine, "2")
    neither = await _account(engine, "3")
    notifications = SqlNotificationRepository(engine)
    days = SqlDayLogRepository(engine, FieldCipher(KEYS))
    no_moon = replace(DEFAULTS.moon, offsets=frozenset[int]())
    await notifications.save(
        practising, replace(DEFAULTS, moon=no_moon, practice=replace(DEFAULTS.practice, on=True))
    )
    await notifications.save(neither, replace(DEFAULTS, moon=no_moon))
    await days.upsert(practising, DayLog(MON - timedelta(days=1), DayStatus.LADIES), ZONE)
    await days.upsert(practising, DayLog(MON - timedelta(days=30), DayStatus.REST), ZONE)
    await days.upsert(moon_only, DayLog(MON, DayStatus.REST), ZONE)

    found = {
        c.account_id: c
        for c in await notifications.candidates(
            NOW - timedelta(days=21), MON - timedelta(days=21), DEFAULTS
        )
    }

    assert set(found) == {practising, moon_only}
    assert found[practising].logged == {MON - timedelta(days=1)}  # inside the window only
    assert found[moon_only].logged == frozenset()  # not needed without the practice reminder


async def test_practice_deliveries_are_accepted(engine: AsyncEngine) -> None:
    me = await _account(engine)
    repo = SqlNotificationRepository(engine)

    assert await repo.claim(me, "practice:2026-10-19", "practice", MON)
    await repo.finish(me, "practice:2026-10-19", "sent")


async def test_insert_if_absent_never_overwrites(engine: AsyncEngine) -> None:
    me = await _account(engine)
    days = SqlDayLogRepository(engine, FieldCipher(KEYS))
    await days.upsert(me, DayLog(MON, DayStatus.LADIES), ZONE)

    first = await days.insert_if_absent(me, DayLog(MON, DayStatus.PRACTICED), ZONE)
    fresh = await days.insert_if_absent(
        me, DayLog(MON + timedelta(days=1), DayStatus.PRACTICED), ZONE
    )

    assert (first, fresh) == (False, True)
    stored = await days.list_range(me, MON, MON + timedelta(days=1))
    assert [d.status for d in stored] == [DayStatus.LADIES, DayStatus.PRACTICED]


async def test_copy_usual_prefers_the_newest_non_led_practice(engine: AsyncEngine) -> None:
    me = await _account(engine)
    days = SqlDayLogRepository(engine, FieldCipher(KEYS))
    practices = SqlPracticeRepository(engine)
    thu, sun = MON - timedelta(days=4), MON - timedelta(days=1)
    for day, context in ((thu, PracticeContext.MYSORE), (sun, PracticeContext.LED)):
        await days.upsert(me, DayLog(day, DayStatus.PRACTICED), ZONE)
        await practices.save(
            me,
            day,
            PracticePatch.of(
                context=context,
                length=PracticeLength(("primary",)),
                start_time=time(6),
                timezone=ZONE,
            ),
        )
    await days.insert_if_absent(me, DayLog(MON, DayStatus.PRACTICED), ZONE)

    copied = await practices.copy_usual(me, MON, ZONE)

    assert copied is not None
    assert copied.source == thu
    assert copied.practice.context is PracticeContext.MYSORE
    assert copied.practice.start_time is None  # never copied
    [day] = await days.list_range(me, MON, MON)
    assert day.practices[0].context is PracticeContext.MYSORE


async def test_copy_usual_with_only_led_history_and_with_none(engine: AsyncEngine) -> None:
    me = await _account(engine)
    days = SqlDayLogRepository(engine, FieldCipher(KEYS))
    practices = SqlPracticeRepository(engine)
    await days.insert_if_absent(me, DayLog(MON, DayStatus.PRACTICED), ZONE)
    assert await practices.copy_usual(me, MON, ZONE) is None

    sun = MON - timedelta(days=1)
    await days.upsert(me, DayLog(sun, DayStatus.PRACTICED), ZONE)
    await practices.save(me, sun, PracticePatch.of(context=PracticeContext.LED))

    copied = await practices.copy_usual(me, MON, ZONE)
    assert copied is not None
    assert (copied.source, copied.practice.context) == (sun, PracticeContext.LED)


async def test_saving_without_practice_leaves_it_alone(engine: AsyncEngine) -> None:
    me = await _account(engine)
    repo = SqlNotificationRepository(engine)
    await repo.patch_practice(me, ReminderPatch(on=True, at=time(18)), DEFAULTS)

    saved = await repo.save(me, replace(DEFAULTS, daily_cap=2), with_practice=False)

    assert (saved.practice.on, saved.practice.at, saved.daily_cap) == (True, time(18), 2)
