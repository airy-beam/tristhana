import asyncio
from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from tristhana.domain.accounts import IdentityKey, IdentityProvider, NewAccount
from tristhana.domain.moon import MoonDay, MoonDayKind
from tristhana.domain.notifications import DEFAULTS
from tristhana.infrastructure.db.accounts import SqlAccountRepository
from tristhana.infrastructure.db.moon import SqlMoonCalendarRepository
from tristhana.infrastructure.db.notifications import SqlNotificationRepository

pytestmark = pytest.mark.db

NOW = datetime(2026, 10, 19, 12, tzinfo=UTC)


async def _account(engine: AsyncEngine, user: str = "42", zone: str | None = "Asia/Almaty") -> UUID:
    repo = SqlAccountRepository(engine)
    account = await repo.create_with_identity(
        IdentityKey(IdentityProvider.TELEGRAM, user), NewAccount(display_name="A", locale="ru")
    )
    if zone:
        await repo.set_timezone_if_unset(account.id, zone)
    return account.id


async def test_replace_year_is_atomic_and_versioned(engine: AsyncEngine) -> None:
    repo = SqlMoonCalendarRepository(engine)
    first = [
        MoonDay(date(2026, 1, 3), MoonDayKind.PURNIMA),
        MoonDay(date(2026, 1, 18), MoonDayKind.AMAVASYA),
    ]
    second = [MoonDay(date(2026, 1, 4), MoonDayKind.KSHAYA_PURNIMA)]

    await repo.replace_year("mysuru", 2026, first, "v1")
    await repo.replace_year("mysuru", 2026, second, "v2")

    assert await repo.days("mysuru", date(2026, 1, 1), date(2026, 12, 31)) == second
    assert await repo.coverage() == {("mysuru", 2026): "v2"}
    assert await repo.days("almaty", date(2026, 1, 1), date(2026, 12, 31)) == []


async def test_settings_default_patch_and_save(engine: AsyncEngine) -> None:
    me = await _account(engine)
    repo = SqlNotificationRepository(engine)

    assert await repo.settings(me, DEFAULTS) == DEFAULTS
    patched = await repo.patch(me, {"moon_offsets": frozenset({1})}, DEFAULTS)
    timed = await repo.patch(me, {"moon_at": time(7)}, DEFAULTS)

    assert patched.moon.offsets == {1}
    assert (timed.moon.offsets, timed.moon.at, timed.quiet) == ({1}, time(7), DEFAULTS.quiet)
    off = await repo.patch(me, {"moon_offsets": frozenset[int]()}, DEFAULTS)
    assert not off.moon.on


async def test_moon_candidates(engine: AsyncEngine) -> None:
    on = await _account(engine, "1")
    await _account(engine, "2", zone=None)  # no zone: never a candidate
    off = await _account(engine, "3")
    blocked = await _account(engine, "4")
    repo = SqlNotificationRepository(engine)
    await repo.patch(off, {"moon_offsets": frozenset[int]()}, DEFAULTS)
    async with engine.connect() as conn:  # seen before the block, whatever today's date is
        await conn.execute(
            text("UPDATE tristhana.account SET last_seen_at = :seen WHERE id = :id"),
            {"seen": NOW - timedelta(days=1), "id": blocked},
        )
    await repo.mark_unreachable(blocked, NOW)

    candidates = await repo.candidates(NOW - timedelta(days=12), NOW.date(), DEFAULTS)

    assert [(c.account_id, c.telegram_id, c.zone, c.settings) for c in candidates] == [
        (on, "1", "Asia/Almaty", DEFAULTS)
    ]


async def test_unreachable_accounts_come_back_when_they_write_again(engine: AsyncEngine) -> None:
    me = await _account(engine)
    repo = SqlNotificationRepository(engine)
    await repo.mark_unreachable(me, NOW - timedelta(days=2))
    async with engine.connect() as conn:  # the daily last_seen_at refresh after a message
        await conn.execute(text("UPDATE tristhana.account SET last_seen_at = now()"))

    assert [
        c.account_id for c in await repo.candidates(NOW - timedelta(days=12), NOW.date(), DEFAULTS)
    ] == [me]


async def test_claim_is_at_most_once_even_when_racing(engine: AsyncEngine) -> None:
    me = await _account(engine)
    repo = SqlNotificationRepository(engine)

    results = await asyncio.gather(
        *(repo.claim(me, "moon:2026-11-05:1", "moon", date(2026, 11, 4)) for _ in range(5))
    )

    assert sorted(results) == [False, False, False, False, True]


async def test_failed_claims_are_retried_three_times_then_final(engine: AsyncEngine) -> None:
    me = await _account(engine)
    repo = SqlNotificationRepository(engine)
    key = "moon:2026-11-05:1"

    claims: list[bool] = []
    for _ in range(4):
        claims.append(await repo.claim(me, key, "moon", date(2026, 11, 4)))
        await repo.finish(me, key, "failed")
    [candidate] = await repo.candidates(NOW - timedelta(days=12), NOW.date(), DEFAULTS)

    assert claims == [True, True, True, False]
    assert [(d.key, d.final) for d in candidate.deliveries] == [(key, True)]


async def test_sent_reminders_mark_the_intro_done_and_prune(engine: AsyncEngine) -> None:
    me = await _account(engine)
    repo = SqlNotificationRepository(engine)
    await repo.claim(me, "moon:2026-11-05:1", "moon", date(2026, 11, 4))
    await repo.finish(me, "moon:2026-11-05:1", "sent")
    await repo.mark_intro_sent(me, NOW)
    await repo.mark_intro_sent(me, NOW + timedelta(days=1))  # the first one stays

    pruned = await repo.prune(datetime.now(UTC) + timedelta(seconds=1))
    [candidate] = await repo.candidates(NOW - timedelta(days=12), NOW.date(), DEFAULTS)

    assert pruned == 1
    assert candidate.had_moon_reminder is True  # survives pruning (Q24)


async def test_moon_location_round_trip_and_check(engine: AsyncEngine) -> None:
    me = await _account(engine)
    accounts = SqlAccountRepository(engine)

    chosen = await accounts.set_moon_location(me, "almaty")
    found = await accounts.find_by_identity(IdentityKey(IdentityProvider.TELEGRAM, "42"))

    assert chosen.moon_location == "almaty"
    assert found is not None
    assert found.moon_location == "almaty"
    with pytest.raises(Exception, match="check"):
        await accounts.set_moon_location(me, "Not A Slug")


async def test_replace_year_rolls_back_as_a_whole(engine: AsyncEngine) -> None:
    repo = SqlMoonCalendarRepository(engine)
    good = [MoonDay(date(2026, 1, 3), MoonDayKind.PURNIMA)]
    await repo.replace_year("mysuru", 2026, good, "v1")
    duplicate = [MoonDay(date(2026, 1, 4), MoonDayKind.PURNIMA)] * 2  # violates the PK

    with pytest.raises(IntegrityError):
        await repo.replace_year("mysuru", 2026, duplicate, "v2")

    assert await repo.days("mysuru", date(2026, 1, 1), date(2026, 12, 31)) == good
    assert await repo.coverage() == {("mysuru", 2026): "v1"}


async def test_concurrent_top_ups_of_one_year_serialize(engine: AsyncEngine) -> None:
    repo = SqlMoonCalendarRepository(engine)
    days = [MoonDay(date(2026, 1, 3), MoonDayKind.PURNIMA)]

    await asyncio.gather(*(repo.replace_year("mysuru", 2026, days, "v1") for _ in range(4)))

    assert await repo.days("mysuru", date(2026, 1, 1), date(2026, 12, 31)) == days


async def test_a_stale_claim_is_taken_over(engine: AsyncEngine) -> None:
    me = await _account(engine)
    repo = SqlNotificationRepository(engine)
    key = "moon:2026-11-05:1"
    assert await repo.claim(me, key, "moon", date(2026, 11, 4))
    assert not await repo.claim(me, key, "moon", date(2026, 11, 4))  # fresh: someone has it
    async with engine.connect() as conn:  # a tick cut off mid-send, long ago
        await conn.execute(
            text("UPDATE tristhana.notification_delivery SET updated_at = now() - interval '6 min'")
        )

    [candidate] = await repo.candidates(NOW - timedelta(days=12), NOW.date(), DEFAULTS)
    assert [(d.final, d.counts_today) for d in candidate.deliveries] == [(False, True)]
    assert await repo.claim(me, key, "moon", date(2026, 11, 4))
