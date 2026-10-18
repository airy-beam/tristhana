import base64
from datetime import date

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from tristhana.application.ports.storage import StorageUnavailable
from tristhana.domain.accounts import IdentityKey, IdentityProvider, NewAccount
from tristhana.domain.days import DayLog, DayStatus
from tristhana.infrastructure.crypto import FieldCipher, MissingCipher
from tristhana.infrastructure.db.accounts import SqlAccountRepository
from tristhana.infrastructure.db.days import SqlDayLogRepository

pytestmark = pytest.mark.db

KEYS = "1:" + base64.b64encode(b"\x07" * 32).decode()
DAY = date(2026, 10, 18)


async def _account_id(engine: AsyncEngine, user: str = "42"):
    key = IdentityKey(IdentityProvider.TELEGRAM, user)
    account = await SqlAccountRepository(engine).create_with_identity(
        key, NewAccount(display_name="A", locale="en")
    )
    return account.id


async def _raw(engine: AsyncEngine) -> list[tuple[str, int | None, str | None]]:
    async with engine.connect() as conn:
        rows = await conn.execute(
            text(
                "SELECT status, length(sealed_status), timezone"
                " FROM tristhana.day_log ORDER BY local_date"
            )
        )
        return [(r[0], r[1], r[2]) for r in rows]


async def test_upsert_inserts_then_overwrites(engine: AsyncEngine) -> None:
    repo = SqlDayLogRepository(engine, FieldCipher(KEYS))
    me = await _account_id(engine)

    await repo.upsert(me, DayLog(DAY, DayStatus.PRACTICED), "Asia/Almaty")
    await repo.upsert(me, DayLog(DAY, DayStatus.TRAVEL), None)

    assert await repo.list_range(me, DAY, DAY) == [DayLog(DAY, DayStatus.TRAVEL)]
    assert await _raw(engine) == [("travel", None, None)]


async def test_ladies_holiday_looks_like_rest_in_the_database(engine: AsyncEngine) -> None:
    repo = SqlDayLogRepository(engine, FieldCipher(KEYS))
    me = await _account_id(engine)
    yesterday = date(2026, 10, 17)

    await repo.upsert(me, DayLog(yesterday, DayStatus.REST), "Asia/Almaty")
    await repo.upsert(me, DayLog(DAY, DayStatus.LADIES), "Asia/Almaty")

    # Same plain status, same sealed length: indistinguishable without the key.
    assert await _raw(engine) == [("rest", 42, "Asia/Almaty"), ("rest", 42, "Asia/Almaty")]
    assert await repo.list_range(me, yesterday, DAY) == [
        DayLog(yesterday, DayStatus.REST),
        DayLog(DAY, DayStatus.LADIES),
    ]


async def test_unreadable_seal_degrades_to_rest(engine: AsyncEngine) -> None:
    me = await _account_id(engine)
    await SqlDayLogRepository(engine, FieldCipher(KEYS)).upsert(
        me, DayLog(DAY, DayStatus.LADIES), None
    )
    other_key = "2:" + base64.b64encode(b"\x08" * 32).decode()

    days = await SqlDayLogRepository(engine, FieldCipher(other_key)).list_range(me, DAY, DAY)

    assert days == [DayLog(DAY, DayStatus.REST)]


async def test_a_seal_moved_to_another_day_does_not_open(engine: AsyncEngine) -> None:
    repo = SqlDayLogRepository(engine, FieldCipher(KEYS))
    me = await _account_id(engine)
    await repo.upsert(me, DayLog(DAY, DayStatus.LADIES), None)
    await repo.upsert(me, DayLog(date(2026, 10, 17), DayStatus.REST), None)
    async with engine.connect() as conn:
        await conn.execute(
            text(
                "UPDATE tristhana.day_log SET sealed_status = "
                "(SELECT sealed_status FROM tristhana.day_log WHERE local_date = :d) "
                "WHERE local_date = :other"
            ),
            {"d": DAY, "other": date(2026, 10, 17)},
        )

    days = await repo.list_range(me, date(2026, 10, 17), DAY)

    assert days[0] == DayLog(date(2026, 10, 17), DayStatus.REST)


async def test_database_rejects_plain_ladies_and_unsealed_rest(engine: AsyncEngine) -> None:
    me = await _account_id(engine)
    for status, sealed in (("ladies", None), ("rest", None), ("practiced", b"x")):
        with pytest.raises(IntegrityError):
            async with engine.connect() as conn:
                await conn.execute(
                    text(
                        "INSERT INTO tristhana.day_log"
                        " (account_id, local_date, status, sealed_status) VALUES (:a, :d, :s, :x)"
                    ),
                    {"a": me, "d": DAY, "s": status, "x": sealed},
                )


async def test_without_a_key_private_statuses_are_unavailable(engine: AsyncEngine) -> None:
    repo = SqlDayLogRepository(engine, MissingCipher())
    me = await _account_id(engine)

    await repo.upsert(me, DayLog(DAY, DayStatus.PRACTICED), None)  # no seal needed
    with pytest.raises(StorageUnavailable):
        await repo.upsert(me, DayLog(DAY, DayStatus.LADIES), None)
    assert await _raw(engine) == [("practiced", None, None)]


async def test_range_delete_and_cascade(engine: AsyncEngine) -> None:
    repo = SqlDayLogRepository(engine, FieldCipher(KEYS))
    me, other = await _account_id(engine, "42"), await _account_id(engine, "43")
    for day in (date(2026, 10, 10), DAY, date(2026, 10, 20)):
        await repo.upsert(me, DayLog(day, DayStatus.PRACTICED), None)
    await repo.upsert(other, DayLog(DAY, DayStatus.MOON), None)

    assert [d.local_date for d in await repo.list_range(me, date(2026, 10, 11), DAY)] == [DAY]
    await repo.delete(me, DAY)
    await repo.delete(me, DAY)  # idempotent
    assert [
        d.local_date for d in await repo.list_range(me, date(2026, 10, 1), date(2026, 10, 31))
    ] == [
        date(2026, 10, 10),
        date(2026, 10, 20),
    ]

    async with engine.connect() as conn:
        await conn.execute(text("DELETE FROM tristhana.account WHERE id = :a"), {"a": me})
    assert await _raw(engine) == [("moon", None, None)]
