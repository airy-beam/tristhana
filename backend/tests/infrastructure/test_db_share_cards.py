"""ST-07 on real Postgres (spec §6, ADR-0040): migration 0026's `share_card`; `insert` holds
the rate limit in one statement; `image` respects `expires_at`; `claim_send` takes the one
send once (also when two run at once), reads the Telegram id, and is "not found" for someone
else's card; `release_send`; `milestone_seen`; `prune`; the account cascade; the CHECKs;
up/down/up with no drift; the app role can use it."""

import asyncio
import hashlib
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.infrastructure.test_db_app_role import app_engine  # noqa: F401  # pyright: ignore[reportUnusedImport]
from tests.infrastructure.test_db_shalas import _person  # pyright: ignore[reportPrivateUsage]
from tristhana.application.ports.share_cards import NewShareCard
from tristhana.domain.share_cards import CardFormat
from tristhana.infrastructure.db import migrate
from tristhana.infrastructure.db.accounts import SqlAccountRepository
from tristhana.infrastructure.db.share_cards import SqlShareCardRepository

pytestmark = pytest.mark.db

NOW = datetime(2026, 11, 9, 3, 0, tzinfo=UTC)
PNG = b"\x89PNG\r\n\x1a\n fake"


def _hash(token: str) -> bytes:
    return hashlib.sha256(token.encode()).digest()


def _card(me: UUID, token: str, expires: datetime = NOW + timedelta(hours=24)) -> NewShareCard:
    return NewShareCard(me, _hash(token), "month", CardFormat.STORY, PNG, expires)


async def test_insert_image_and_expiry(engine: AsyncEngine) -> None:
    me, _ = await _person(engine, "Sam")
    repo = SqlShareCardRepository(engine)
    assert await repo.insert(_card(me.id, "t1"), NOW - timedelta(hours=24), 50)
    assert await repo.image(_hash("t1"), NOW) == PNG
    assert await repo.image(_hash("t1"), NOW + timedelta(hours=24)) is None
    assert await repo.image(_hash("nope"), NOW) is None


async def test_rate_limit_in_the_insert(engine: AsyncEngine) -> None:
    me, _ = await _person(engine, "Sam")
    other, _ = await _person(engine, "Kim")
    repo = SqlShareCardRepository(engine)
    since = datetime.now(UTC) - timedelta(hours=24)  # created_at is the database's now()
    assert await repo.insert(_card(me.id, "a"), since, 2)
    assert await repo.insert(_card(me.id, "b"), since, 2)
    assert not await repo.insert(_card(me.id, "c"), since, 2)
    assert await repo.image(_hash("c"), NOW) is None
    assert await repo.insert(_card(other.id, "d"), since, 2)  # per person
    assert await repo.insert(_card(me.id, "e"), datetime.now(UTC) + timedelta(seconds=1), 2)


async def test_claim_send_once_with_the_telegram_id(engine: AsyncEngine) -> None:
    me, key = await _person(engine, "Sam")
    other, _ = await _person(engine, "Kim")
    repo = SqlShareCardRepository(engine)
    await repo.insert(_card(me.id, "t"), NOW - timedelta(hours=24), 50)

    assert (await repo.claim_send(other.id, _hash("t"), NOW)).found is False
    first = await repo.claim_send(me.id, _hash("t"), NOW)
    assert (first.found, first.png, first.telegram_id) == (True, PNG, key.provider_user_id)
    second = await repo.claim_send(me.id, _hash("t"), NOW)
    assert (second.found, second.png) == (True, None)
    await repo.release_send(other.id, _hash("t"))  # not theirs: nothing
    assert (await repo.claim_send(me.id, _hash("t"), NOW)).png is None
    await repo.release_send(me.id, _hash("t"))
    assert (await repo.claim_send(me.id, _hash("t"), NOW)).png == PNG
    late = await repo.claim_send(me.id, _hash("t"), NOW + timedelta(hours=25))
    assert late.found is False


async def test_two_claims_at_once_send_once(engine: AsyncEngine) -> None:
    me, _ = await _person(engine, "Sam")
    repo = SqlShareCardRepository(engine)
    await repo.insert(_card(me.id, "race"), NOW - timedelta(hours=24), 50)
    claims = await asyncio.gather(*(repo.claim_send(me.id, _hash("race"), NOW) for _ in range(5)))
    assert sum(c.png is not None for c in claims) == 1


async def test_milestone_seen(engine: AsyncEngine) -> None:
    me, _ = await _person(engine, "Sam")
    repo = SqlShareCardRepository(engine)
    assert not await repo.milestone_seen(me.id, 100)
    async with engine.connect() as conn:
        await conn.execute(
            text(
                "INSERT INTO tristhana.practice_milestone (account_id, threshold, celebrated)"
                " VALUES (:a, 100, true)"
            ),
            {"a": me.id},
        )
        await conn.commit()
    assert await repo.milestone_seen(me.id, 100)
    assert not await repo.milestone_seen(me.id, 365)


async def test_prune_and_cascade(engine: AsyncEngine) -> None:
    me, _ = await _person(engine, "Sam")
    repo = SqlShareCardRepository(engine)
    await repo.insert(_card(me.id, "old", NOW - timedelta(minutes=1)), NOW - timedelta(days=2), 50)
    await repo.insert(_card(me.id, "new"), NOW - timedelta(days=2), 50)
    assert await repo.prune(NOW) >= 1
    assert await repo.image(_hash("new"), NOW) == PNG
    await SqlAccountRepository(engine).delete(me.id)
    assert await repo.image(_hash("new"), NOW) is None


async def test_checks(engine: AsyncEngine) -> None:
    me, _ = await _person(engine, "Sam")
    repo = SqlShareCardRepository(engine)
    with pytest.raises(IntegrityError):
        await repo.insert(
            NewShareCard(me.id, b"short", "month", CardFormat.STORY, PNG, NOW), NOW, 50
        )
    with pytest.raises(IntegrityError):
        await repo.insert(
            NewShareCard(me.id, _hash("big"), "month", CardFormat.STORY, b"x" * 2_000_001, NOW),
            NOW,
            50,
        )


async def test_0026_up_down_up_and_no_drift(migrated_url: str, engine: AsyncEngine) -> None:
    exists = text(
        "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'tristhana'"
        " AND table_name = 'share_card'"
    )
    await asyncio.to_thread(migrate.downgrade, migrated_url, "0025")
    try:
        async with engine.connect() as conn:
            assert (await conn.execute(exists)).scalar_one() == 0
    finally:
        await asyncio.to_thread(migrate.upgrade, migrated_url)
    async with engine.connect() as conn:
        assert (await conn.execute(exists)).scalar_one() == 1
    await asyncio.to_thread(migrate.check, migrated_url)


async def test_share_cards_work_as_the_app_role(app_engine: AsyncEngine) -> None:  # noqa: F811
    me, _ = await _person(app_engine, "Sam")
    repo = SqlShareCardRepository(app_engine)
    assert await repo.insert(_card(me.id, "role"), NOW - timedelta(hours=24), 50)
    assert await repo.image(_hash("role"), NOW) == PNG
    assert (await repo.claim_send(me.id, _hash("role"), NOW)).png == PNG
    await repo.release_send(me.id, _hash("role"))
    assert await repo.prune(NOW + timedelta(days=2)) >= 1
