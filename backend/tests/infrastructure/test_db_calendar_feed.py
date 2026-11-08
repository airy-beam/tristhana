"""SC-06 on real Postgres (spec §3, §6, §7, §8; ADR-0036, ADR-0016): migration 0023's
`calendar_feed`; `replace` is the create-or-rotate upsert (the old hash stops matching in the
same statement) and seals the token (no plaintext at rest, the hash is SHA-256); `get` unseals
it; `account_by_token` is one statement that returns the account as the account load does and
writes `fetched_on` at most once a day (the row is untouched on a second poll that day);
`delete` is idempotent; the CHECK and UNIQUE on the hash; the account cascade; a poll is two
statements in all; up/down/up with no drift; the app role can use it.

Assumed adapter: `tristhana.infrastructure.db.calendar_feed.SqlCalendarFeedRepository(engine,
cipher)`, the port shapes in `tests/calendar_feed_fakes.py`. Imported inside the tests
(test-first), so the module collects and skips without a database."""

import asyncio
import base64
import hashlib
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import event, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.fakes import FixedClock, cities
from tests.infrastructure.test_db_app_role import app_engine  # noqa: F401  # pyright: ignore[reportUnusedImport]
from tests.infrastructure.test_db_shalas import (  # pyright: ignore[reportPrivateUsage]
    _person,  # pyright: ignore[reportPrivateUsage]
    _shala,  # pyright: ignore[reportPrivateUsage]
    _student,  # pyright: ignore[reportPrivateUsage]
)
from tristhana.domain.classes import ClassType
from tristhana.infrastructure.crypto import FieldCipher
from tristhana.infrastructure.db import migrate
from tristhana.infrastructure.db.accounts import SqlAccountRepository
from tristhana.infrastructure.db.classes import SqlScheduleRepository
from tristhana.infrastructure.i18n.fluent import FluentTranslator

pytestmark = pytest.mark.db

KEYS = "1:" + base64.b64encode(b"\x07" * 32).decode()
TOKEN_1 = "Xy3kP9qR2sT5uV8wZ1aB4cD7eF0gH3iJ6kL9mN2oP5q"
TOKEN_2 = "Qm7nB4vC1xZ8lK5jH2gF9dS6aP3oI0uY7tR4eW1q-_A"
TODAY = date(2026, 11, 9)
NOW = datetime(2026, 11, 9, 3, 0, tzinfo=UTC)


def _hash(token: str) -> bytes:
    return hashlib.sha256(token.encode()).digest()


def _repo(engine: AsyncEngine) -> Any:
    from tristhana.infrastructure.db.calendar_feed import SqlCalendarFeedRepository

    return SqlCalendarFeedRepository(engine, FieldCipher(KEYS))


async def _sql(engine: AsyncEngine, statement: str, **params: Any) -> Any:
    async with engine.connect() as conn:
        result = await conn.execute(text(statement), params)
        await conn.commit()
        return result


@contextmanager
def _statements(engine: AsyncEngine) -> Generator[list[str]]:
    seen: list[str] = []

    def record(_conn: object, _cursor: object, statement: str, *_: object) -> None:
        if "tristhana." in statement:
            seen.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", record)
    try:
        yield seen
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", record)


async def _row(engine: AsyncEngine, account: UUID) -> Any:
    result = await _sql(
        engine,
        "SELECT token_hash, sealed_token, created_at, fetched_on, xmin::text AS version"
        " FROM tristhana.calendar_feed WHERE account_id = :a",
        a=account,
    )
    return result.one_or_none()


# Create, show, rotate, revoke


async def test_replace_seals_and_get_unseals(engine: AsyncEngine) -> None:
    me, _ = await _person(engine, "Sam")
    repo = _repo(engine)

    with _statements(engine) as seen:
        link = await repo.replace(me.id, _hash(TOKEN_1), TOKEN_1)

    assert len(seen) == 1
    assert link.token == TOKEN_1
    assert link.fetched_on is None
    assert link.created_at.tzinfo is not None
    assert await repo.get(me.id) == link
    row = await _row(engine, me.id)
    assert bytes(row.token_hash) == _hash(TOKEN_1)
    assert TOKEN_1.encode() not in bytes(row.sealed_token)
    assert bytes(row.sealed_token) != TOKEN_1.encode()


async def test_get_is_one_statement_and_none_when_off(engine: AsyncEngine) -> None:
    me, _ = await _person(engine, "Sam")

    with _statements(engine) as seen:
        assert await _repo(engine).get(me.id) is None

    assert len(seen) == 1


async def test_replace_rotates_in_one_statement(engine: AsyncEngine) -> None:
    me, _ = await _person(engine, "Sam")
    repo = _repo(engine)
    await repo.replace(me.id, _hash(TOKEN_1), TOKEN_1)

    with _statements(engine) as seen:
        link = await repo.replace(me.id, _hash(TOKEN_2), TOKEN_2)

    assert len(seen) == 1
    assert link.token == TOKEN_2
    assert await repo.account_by_token(_hash(TOKEN_1), TODAY) is None
    assert (await repo.account_by_token(_hash(TOKEN_2), TODAY)).account.id == me.id
    count = await _sql(engine, "SELECT count(*) FROM tristhana.calendar_feed")
    assert count.scalar_one() == 1


async def test_delete_is_idempotent(engine: AsyncEngine) -> None:
    me, _ = await _person(engine, "Sam")
    repo = _repo(engine)
    await repo.replace(me.id, _hash(TOKEN_1), TOKEN_1)

    with _statements(engine) as seen:
        await repo.delete(me.id)
    await repo.delete(me.id)

    assert len(seen) == 1
    assert await repo.get(me.id) is None
    assert await repo.account_by_token(_hash(TOKEN_1), TODAY) is None


# The poll lookup


async def test_the_lookup_is_one_statement_and_loads_the_account(engine: AsyncEngine) -> None:
    me, key = await _person(engine, "Sam", moon="mysuru")
    repo = _repo(engine)
    link = await repo.replace(me.id, _hash(TOKEN_1), TOKEN_1)

    with _statements(engine) as seen:
        owner = await repo.account_by_token(_hash(TOKEN_1), TODAY)

    assert len(seen) == 1
    assert owner.account == await SqlAccountRepository(engine).find_by_identity(key)
    assert owner.created_at == link.created_at


async def test_an_unknown_hash_is_none(engine: AsyncEngine) -> None:
    await _person(engine, "Sam")

    assert await _repo(engine).account_by_token(_hash(TOKEN_2), TODAY) is None


async def test_fetched_on_is_written_at_most_once_a_day(engine: AsyncEngine) -> None:
    me, _ = await _person(engine, "Sam")
    repo = _repo(engine)
    await repo.replace(me.id, _hash(TOKEN_1), TOKEN_1)

    await repo.account_by_token(_hash(TOKEN_1), TODAY)
    first = await _row(engine, me.id)
    await repo.account_by_token(_hash(TOKEN_1), TODAY)
    second = await _row(engine, me.id)
    await repo.account_by_token(_hash(TOKEN_1), TODAY + timedelta(days=1))
    third = await _row(engine, me.id)

    assert first.fetched_on == TODAY
    assert second.version == first.version  # no write on the same day
    assert third.fetched_on == TODAY + timedelta(days=1)
    assert third.version != second.version
    assert (await repo.get(me.id)).fetched_on == TODAY + timedelta(days=1)


# Constraints and cascade


async def test_the_hash_is_unique(engine: AsyncEngine) -> None:
    a, _ = await _person(engine, "A")
    b, _ = await _person(engine, "B")
    await _repo(engine).replace(a.id, _hash(TOKEN_1), TOKEN_1)

    with pytest.raises(IntegrityError):
        await _sql(
            engine,
            "INSERT INTO tristhana.calendar_feed (account_id, token_hash, sealed_token)"
            " VALUES (:a, :h, :s)",
            a=b.id,
            h=_hash(TOKEN_1),
            s=b"sealed",
        )


@pytest.mark.parametrize("size", [0, 31, 33])
async def test_the_hash_is_32_bytes(engine: AsyncEngine, size: int) -> None:
    a, _ = await _person(engine, "A")

    with pytest.raises(IntegrityError):
        await _sql(
            engine,
            "INSERT INTO tristhana.calendar_feed (account_id, token_hash, sealed_token)"
            " VALUES (:a, :h, :s)",
            a=a.id,
            h=b"\x01" * size,
            s=b"sealed",
        )


async def test_deleting_the_account_removes_the_link(engine: AsyncEngine) -> None:
    me, _ = await _person(engine, "Sam")
    repo = _repo(engine)
    await repo.replace(me.id, _hash(TOKEN_1), TOKEN_1)

    assert await SqlAccountRepository(engine).delete(me.id) is True

    assert await _row(engine, me.id) is None
    assert await repo.account_by_token(_hash(TOKEN_1), TODAY) is None


# A whole poll


async def test_a_poll_is_two_statements(engine: AsyncEngine) -> None:
    from tests.infrastructure.test_db_classes import CAPS, _draft  # pyright: ignore[reportPrivateUsage]
    from tristhana.application.calendar_feed import GetCalendarFeed

    anna, _ = await _person(engine, "Anna")
    sam, _ = await _person(engine, "Sam")
    shala = await _shala(engine, anna.id, name="Ashtanga Almaty")
    await _student(engine, shala, anna.id, sam.id)
    schedule = SqlScheduleRepository(engine)
    created = await schedule.create(
        shala,
        anna.id,
        _draft(type=ClassType.MYSORE, teacher_id=anna.id, start=time(6, 0)),
        CAPS,
        TODAY,
    )
    assert created.value is not None
    await _sql(
        engine,
        "INSERT INTO tristhana.moon_day (location, date, kind) VALUES ('almaty', :d, 'purnima')"
        " ON CONFLICT DO NOTHING",
        d=date(2026, 11, 24),
    )
    feeds = _repo(engine)
    await feeds.replace(sam.id, _hash(TOKEN_1), TOKEN_1)
    use_case = GetCalendarFeed(feeds, schedule, FixedClock(NOW), cities(), FluentTranslator())

    with _statements(engine) as seen:
        feed = await use_case.execute(TOKEN_1)

    assert len(seen) == 2
    assert feed is not None
    assert any(e.uid.startswith(f"{created.value.id}-") for e in feed.events)
    assert any(e.all_day for e in feed.events)
    for statement in seen:
        for table in ("day_log", "rest_period", "check_in", "diary", "practice", "progression"):
            assert f"tristhana.{table}" not in statement, table


async def test_a_dead_token_is_one_statement(engine: AsyncEngine) -> None:
    from tristhana.application.calendar_feed import GetCalendarFeed

    use_case = GetCalendarFeed(
        _repo(engine), SqlScheduleRepository(engine), FixedClock(NOW), cities(),
        FluentTranslator(),
    )  # fmt: skip

    with _statements(engine) as seen:
        assert await use_case.execute(TOKEN_2) is None

    assert len(seen) == 1


# Migration 0023 and the app role


async def test_0023_up_down_up_and_no_drift(migrated_url: str, engine: AsyncEngine) -> None:
    exists = text(
        "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'tristhana'"
        " AND table_name = 'calendar_feed'"
    )
    await asyncio.to_thread(migrate.downgrade, migrated_url, "0022")
    try:
        async with engine.connect() as conn:
            assert (await conn.execute(exists)).scalar_one() == 0
    finally:
        await asyncio.to_thread(migrate.upgrade, migrated_url)
    async with engine.connect() as conn:
        assert (await conn.execute(exists)).scalar_one() == 1
    await asyncio.to_thread(migrate.check, migrated_url)


async def test_the_feed_works_as_the_app_role(app_engine: AsyncEngine) -> None:  # noqa: F811
    me, _ = await _person(app_engine, "Sam")
    repo = _repo(app_engine)

    await repo.replace(me.id, _hash(TOKEN_1), TOKEN_1)
    owner = await repo.account_by_token(_hash(TOKEN_1), TODAY)
    await repo.delete(me.id)

    assert owner.account.id == me.id
    assert await repo.get(me.id) is None
