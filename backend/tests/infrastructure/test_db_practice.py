import base64
from datetime import date, time
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from tristhana.application.practice_patch import PracticePatch
from tristhana.domain.accounts import IdentityKey, IdentityProvider, NewAccount
from tristhana.domain.days import DayLog, DayStatus
from tristhana.domain.practice import (
    FULL_PRIMARY,
    SHORT,
    InvalidPractice,
    Practice,
    PracticeContext,
    PracticeLength,
)
from tristhana.infrastructure.crypto import FieldCipher
from tristhana.infrastructure.db.accounts import SqlAccountRepository
from tristhana.infrastructure.db.days import SqlDayLogRepository
from tristhana.infrastructure.db.practice import SqlPracticeRepository

pytestmark = pytest.mark.db

KEYS = "1:" + base64.b64encode(b"\x07" * 32).decode()
FRI, MON = date(2026, 10, 16), date(2026, 10, 19)
HALF_PLUS = PracticeLength(("primary", "intermediate"), "pasasana", "second_half")


async def _setup(engine: AsyncEngine, *practiced: date) -> tuple[UUID, SqlDayLogRepository]:
    account = await SqlAccountRepository(engine).create_with_identity(
        IdentityKey(IdentityProvider.TELEGRAM, "42"), NewAccount(display_name="A", locale="en")
    )
    days = SqlDayLogRepository(engine, FieldCipher(KEYS))
    for day in practiced:
        await days.upsert(account.id, DayLog(day, DayStatus.PRACTICED), "Asia/Almaty")
    return account.id, days


async def test_patches_upsert_only_their_fields(engine: AsyncEngine) -> None:
    me, _ = await _setup(engine, MON)
    repo = SqlPracticeRepository(engine)

    await repo.save(
        me, MON, PracticePatch.of(context=PracticeContext.MYSORE, timezone="Asia/Almaty")
    )
    saved = await repo.save(me, MON, PracticePatch.of(length=HALF_PLUS, duration_min=120))

    assert saved is not None
    assert saved.practice == Practice(
        PracticeContext.MYSORE, length=HALF_PLUS, duration_min=120, timezone="Asia/Almaty"
    )


async def test_short_practice_and_no_length_are_different(engine: AsyncEngine) -> None:
    me, _ = await _setup(engine, MON)
    repo = SqlPracticeRepository(engine)

    short = await repo.save(me, MON, PracticePatch.of(length=SHORT))
    cleared = await repo.save(me, MON, PracticePatch.of(length=None))

    assert short is not None
    assert short.practice.length == SHORT
    assert cleared is not None
    assert cleared.practice.length is None


async def test_no_details_on_a_day_that_is_not_practiced(engine: AsyncEngine) -> None:
    me, days = await _setup(engine)
    await days.upsert(me, DayLog(MON, DayStatus.LADIES), None)
    repo = SqlPracticeRepository(engine)

    assert await repo.save(me, MON, PracticePatch.of(duration_min=60)) is None
    assert await repo.save(me, FRI, PracticePatch.of(duration_min=60)) is None  # no day at all


async def test_status_change_deletes_details_in_the_same_statement(engine: AsyncEngine) -> None:
    me, days = await _setup(engine, MON)
    repo = SqlPracticeRepository(engine)
    await repo.save(me, MON, PracticePatch.of(duration_min=60))

    await days.upsert(me, DayLog(MON, DayStatus.MOON), None)

    async with engine.connect() as conn:
        left = (await conn.execute(text("SELECT count(*) FROM tristhana.practice"))).scalar_one()
    assert left == 0


async def test_list_range_carries_practices_of_practiced_days(engine: AsyncEngine) -> None:
    me, days = await _setup(engine, FRI, MON)
    repo = SqlPracticeRepository(engine)
    await repo.save(me, MON, PracticePatch.of(length=FULL_PRIMARY))

    logged = await days.list_range(me, FRI, MON)

    assert [(d.local_date, len(d.practices)) for d in logged] == [(FRI, 0), (MON, 1)]
    assert logged[1].practices[0].length == FULL_PRIMARY


async def test_copy_latest_in_one_statement_keeps_the_start_time(engine: AsyncEngine) -> None:
    me, _ = await _setup(engine, FRI, MON)
    repo = SqlPracticeRepository(engine)
    await repo.save(
        me,
        FRI,
        PracticePatch.full(
            Practice(
                PracticeContext.LED,
                length=FULL_PRIMARY,
                duration_min=90,
                start_time=time(6),
                timezone="Asia/Almaty",
            )
        ),
    )
    await repo.save(me, MON, PracticePatch.of(start_time=time(7), timezone="Asia/Almaty"))

    copied = await repo.copy_latest(me, MON, "Asia/Almaty")

    assert copied is not None
    assert copied.practice == Practice(
        PracticeContext.LED,
        length=FULL_PRIMARY,
        duration_min=90,
        start_time=time(7),  # not copied; this day's own start time stays
        timezone="Asia/Almaty",
    )
    assert await repo.copy_latest(me, FRI, None) is None  # nothing earlier


async def test_recent_is_newest_first_and_before_the_date(engine: AsyncEngine) -> None:
    me, _ = await _setup(engine, FRI, MON)
    repo = SqlPracticeRepository(engine)
    await repo.save(me, FRI, PracticePatch.of(duration_min=60))
    await repo.save(me, MON, PracticePatch.of(duration_min=90))

    assert [p.duration_min for p in await repo.recent(me, date(2026, 10, 20), 5)] == [90, 60]
    assert [p.duration_min for p in await repo.recent(me, MON, 5)] == [60]


async def test_database_checks(engine: AsyncEngine) -> None:
    me, _ = await _setup(engine, MON)
    repo = SqlPracticeRepository(engine)

    with pytest.raises(InvalidPractice):  # self-practice is never online
        await repo.save(me, MON, PracticePatch.of(context=PracticeContext.SELF, online=True))
    for bad in (
        "UPDATE tristhana.practice SET slot = 2",
        "UPDATE tristhana.practice SET context = 'home'",
        "UPDATE tristhana.practice SET end_item = 'navasana', series = NULL",
        "UPDATE tristhana.practice SET duration_min = 601",
        "UPDATE tristhana.practice SET start_time = '06:00', timezone = NULL",
    ):
        await repo.save(me, MON, PracticePatch.of(duration_min=60))
        with pytest.raises(IntegrityError):
            async with engine.connect() as conn:
                await conn.execute(text(bad))


async def test_clearing_the_day_cascades(engine: AsyncEngine) -> None:
    me, days = await _setup(engine, MON)
    repo = SqlPracticeRepository(engine)
    await repo.save(me, MON, PracticePatch.of(duration_min=60))

    await days.delete(me, MON)
    await repo.delete(me, MON)  # idempotent

    assert await repo.recent(me, date(2026, 10, 20), 5) == []


async def test_zone_travels_only_with_the_start_time(engine: AsyncEngine) -> None:
    me, _ = await _setup(engine, MON)
    repo = SqlPracticeRepository(engine)
    await repo.save(me, MON, PracticePatch.of(start_time=time(4, 30), timezone="Asia/Kolkata"))

    # Back home: a duration tap, then a full PUT re-sending the same start time.
    await repo.save(me, MON, PracticePatch.of(duration_min=90))
    same = await repo.save(
        me, MON, PracticePatch.of(start_time=time(4, 30), timezone="Asia/Almaty")
    )
    moved = await repo.save(me, MON, PracticePatch.of(start_time=time(7), timezone="Asia/Almaty"))

    assert same is not None
    assert (same.practice.start_time, same.practice.timezone) == (time(4, 30), "Asia/Kolkata")
    assert moved is not None
    assert (moved.practice.start_time, moved.practice.timezone) == (time(7), "Asia/Almaty")


async def test_empty_rows_never_count_as_last_time(engine: AsyncEngine) -> None:
    me, _ = await _setup(engine, FRI, date(2026, 10, 17), MON)
    repo = SqlPracticeRepository(engine)
    await repo.save(me, FRI, PracticePatch.of(duration_min=60))
    await repo.save(me, date(2026, 10, 17), PracticePatch.of(duration_min=None))  # empty row

    copied = await repo.copy_latest(me, MON, None)

    assert copied is not None
    assert copied.practice.duration_min == 60
    assert [p.duration_min for p in await repo.recent(me, MON, 5)] == [60]


async def test_details_left_on_a_rest_day_are_never_copied_and_go_on_re_practice(
    engine: AsyncEngine,
) -> None:
    me, days = await _setup(engine, FRI, MON)
    repo = SqlPracticeRepository(engine)
    await repo.save(me, FRI, PracticePatch.of(duration_min=60))
    # Simulate a race / old revision: Friday becomes rest but its details stay behind.
    async with engine.connect() as conn:
        await conn.execute(
            text("UPDATE tristhana.day_log SET status = 'skipped' WHERE local_date = :d"),
            {"d": FRI},
        )

    assert await repo.copy_latest(me, MON, None) is None
    await days.upsert(me, DayLog(FRI, DayStatus.PRACTICED), None)
    assert await repo.recent(me, MON, 5) == []  # the leftover was removed
