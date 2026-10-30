"""GM-01 part 2 (ADR-0028) on Postgres: the practice-count ledger written inside the day
write, still one statement; parity with the domain rule; races; timing; migration 0017."""

import asyncio
import base64
import random
from collections.abc import Generator
from contextlib import contextmanager
from datetime import date, timedelta
from uuid import UUID

import pytest
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.fakes import InMemoryDays
from tristhana.domain.accounts import IdentityKey, IdentityProvider, NewAccount
from tristhana.domain.days import DayLog, DayStatus
from tristhana.infrastructure.crypto import FieldCipher
from tristhana.infrastructure.db import migrate
from tristhana.infrastructure.db.accounts import SqlAccountRepository
from tristhana.infrastructure.db.days import SqlDayLogRepository

pytestmark = pytest.mark.db

KEYS = "1:" + base64.b64encode(b"\x07" * 32).decode()
THRESHOLDS = (100, 365, 1000)
DAY = date(2026, 10, 30)
P = DayStatus.PRACTICED


async def _account(engine: AsyncEngine, user: str = "42") -> UUID:
    account = await SqlAccountRepository(engine).create_with_identity(
        IdentityKey(IdentityProvider.TELEGRAM, user), NewAccount(display_name="A", locale="en")
    )
    return account.id


def _repo(engine: AsyncEngine) -> SqlDayLogRepository:
    return SqlDayLogRepository(engine, FieldCipher(KEYS))


async def _practised(engine: AsyncEngine, me: UUID, n: int, status: str = "practiced") -> None:
    """`n` days ending two days before DAY (DAY and DAY - 1 stay free)."""
    async with engine.connect() as conn:
        await conn.execute(
            text(
                "INSERT INTO tristhana.day_log (account_id, local_date, status)"
                " SELECT :a, CAST(:end AS date) - g, :s FROM generate_series(0, :n - 1) AS g"
            ),
            {"a": me, "end": DAY - timedelta(days=2), "n": n, "s": status},
        )


async def _ledger(engine: AsyncEngine, me: UUID) -> list[tuple[int, bool]]:
    async with engine.connect() as conn:
        rows = await conn.execute(
            text(
                "SELECT threshold, celebrated FROM tristhana.practice_milestone"
                " WHERE account_id = :a ORDER BY threshold"
            ),
            {"a": me},
        )
        return [(r[0], r[1]) for r in rows]


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


async def test_the_hundredth_practice_is_reached_once_in_one_statement(
    engine: AsyncEngine,
) -> None:
    me = await _account(engine)
    await _practised(engine, me, 99)
    repo = _repo(engine)

    with _statements(engine) as seen:
        saved = await repo.upsert(me, DayLog(DAY, P), "UTC", THRESHOLDS)
    again = await repo.upsert(me, DayLog(DAY, P), "UTC", THRESHOLDS)

    assert len(seen) == 1
    assert (saved.reached, again.reached) == (100, None)
    assert await _ledger(engine, me) == [(100, True)]


async def test_insert_if_absent_reaches_on_an_empty_day_only(engine: AsyncEngine) -> None:
    me = await _account(engine)
    await _practised(engine, me, 98)
    repo = _repo(engine)

    with _statements(engine) as seen:
        first = await repo.insert_if_absent(me, DayLog(DAY - timedelta(1), P), "UTC", THRESHOLDS)
    second = await repo.insert_if_absent(me, DayLog(DAY, P), "UTC", THRESHOLDS)
    already = await repo.insert_if_absent(me, DayLog(DAY, P), "UTC", THRESHOLDS)

    assert len(seen) == 1
    assert (first.reached, second.reached) == (None, 100)
    assert already.inserted is False
    assert await _ledger(engine, me) == [(100, True)]


async def test_rest_like_days_and_a_rest_reminder_never_count(engine: AsyncEngine) -> None:
    me = await _account(engine)
    await _practised(engine, me, 99)
    await _practised(engine, await _account(engine, "43"), 200)  # another account's days
    repo = _repo(engine)

    for status in (DayStatus.REST, DayStatus.LADIES, DayStatus.MOON, DayStatus.SKIPPED):
        assert (await repo.upsert(me, DayLog(DAY, status), "UTC", THRESHOLDS)).reached is None
    rest = await repo.insert_if_absent(me, DayLog(DAY - timedelta(1), DayStatus.REST), None, (1,))

    assert rest.reached is None
    assert await _ledger(engine, me) == []


async def test_status_change_and_clear_never_re_celebrate(engine: AsyncEngine) -> None:
    me = await _account(engine)
    await _practised(engine, me, 99)
    repo = _repo(engine)
    await repo.upsert(me, DayLog(DAY, P), "UTC", THRESHOLDS)

    await repo.upsert(me, DayLog(DAY, DayStatus.SICK), "UTC", THRESHOLDS)
    after_rest = await repo.upsert(me, DayLog(DAY, P), "UTC", THRESHOLDS)
    await repo.delete(me, DAY)
    after_clear = await repo.upsert(me, DayLog(DAY, P), "UTC", THRESHOLDS)

    assert (after_rest.reached, after_clear.reached) == (None, None)
    assert await _ledger(engine, me) == [(100, True)]


async def test_already_past_a_threshold_is_seeded_silently(engine: AsyncEngine) -> None:
    me = await _account(engine)
    await _practised(engine, me, 400)

    saved = await _repo(engine).upsert(me, DayLog(DAY, P), "UTC", THRESHOLDS)

    assert saved.reached is None
    assert await _ledger(engine, me) == [(100, False), (365, False)]


async def test_without_thresholds_the_sql_is_unchanged(engine: AsyncEngine) -> None:
    me = await _account(engine)
    await _practised(engine, me, 99)

    with _statements(engine) as seen:
        saved = await _repo(engine).upsert(me, DayLog(DAY, P), "UTC")

    assert "practice_milestone" not in seen[0]
    assert saved.reached is None
    assert await _ledger(engine, me) == []


async def test_concurrent_writes_at_99_reach_100_once(engine: AsyncEngine) -> None:
    me = await _account(engine)
    await _practised(engine, me, 99)
    repo = _repo(engine)

    results = await asyncio.gather(
        repo.upsert(me, DayLog(DAY, P), "UTC", THRESHOLDS),
        repo.upsert(me, DayLog(DAY - timedelta(1), P), "UTC", THRESHOLDS),
    )

    assert sorted(r.reached or 0 for r in results) == [0, 100]
    assert await _ledger(engine, me) == [(100, True)]


async def test_parity_with_the_fake_over_random_writes(engine: AsyncEngine) -> None:
    """The SQL and the in-memory rule (which mirrors the domain) agree on every write."""
    rng = random.Random(28)  # noqa: S311 - a reproducible test sequence
    me = await _account(engine)
    repo, fake = _repo(engine), InMemoryDays()
    thresholds = (3, 5, 8)
    pool = [DAY - timedelta(days=i) for i in range(12)]
    statuses = [P, P, P, DayStatus.REST, DayStatus.SKIPPED, None]

    for _ in range(80):
        when, status = rng.choice(pool), rng.choice(statuses)
        if status is None:
            await repo.delete(me, when)
            await fake.delete(me, when)
            continue
        if rng.random() < 0.3:
            got = (await repo.insert_if_absent(me, DayLog(when, status), "UTC", thresholds)).reached
            want = (
                await fake.insert_if_absent(me, DayLog(when, status), "UTC", thresholds)
            ).reached
        else:
            got = (await repo.upsert(me, DayLog(when, status), "UTC", thresholds)).reached
            want = (await fake.upsert(me, DayLog(when, status), "UTC", thresholds)).reached
        assert got == want

    stored = {(t, c) for (a, t), c in fake.milestone_rows.items() if a == me}
    assert set(await _ledger(engine, me)) == stored


async def test_the_count_is_fast_on_a_long_log(engine: AsyncEngine) -> None:
    """ADR-0028: the count's server time on 9 000 practised days (25 years) stays < 5 ms.
    If this fails, migration 0017's successor adds the partial index."""
    me = await _account(engine)
    await _practised(engine, me, 9000)
    count = (
        "EXPLAIN (ANALYZE, FORMAT JSON) SELECT count(*) + 1 FROM tristhana.day_log"
        " WHERE account_id = :a AND status = 'practiced' AND local_date <> :d"
    )
    async with engine.connect() as conn:
        await conn.execute(text("ANALYZE tristhana.day_log"))
        runs = [
            (await conn.execute(text(count), {"a": me, "d": DAY})).scalar_one()[0] for _ in range(5)
        ]

    assert min(r["Execution Time"] for r in runs) < 5.0


async def test_the_ledger_cascades_on_account_delete(engine: AsyncEngine) -> None:
    me = await _account(engine)
    await _practised(engine, me, 99)
    await _repo(engine).upsert(me, DayLog(DAY, P), "UTC", THRESHOLDS)

    assert await SqlAccountRepository(engine).delete(me)

    assert await _ledger(engine, me) == []


def test_0017_follows_0016_and_is_the_head() -> None:
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(migrate.alembic_config("postgresql://unused"))
    revision = script.get_revision("0017")
    assert revision is not None
    assert revision.down_revision == "0016"
    assert script.get_current_head() == "0017"


async def test_0017_down_and_up(migrated_url: str, engine: AsyncEngine) -> None:
    has_table = (
        "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'tristhana'"
        " AND table_name = 'practice_milestone'"
    )
    await asyncio.to_thread(migrate.downgrade, migrated_url, "0016")
    async with engine.connect() as conn:
        assert (await conn.execute(text(has_table))).scalar_one() == 0
    await asyncio.to_thread(migrate.upgrade, migrated_url)
    async with engine.connect() as conn:
        assert (await conn.execute(text(has_table))).scalar_one() == 1
    await asyncio.to_thread(migrate.check, migrated_url)
