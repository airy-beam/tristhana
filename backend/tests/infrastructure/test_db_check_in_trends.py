"""ST-05 facts on real Postgres (spec §4, §8): one statement over plain columns (never
`sealed_status`, never `tags`); only check-ins on days whose plain status is `practiced`, so a
stray row on a rest, No-practice or sealed 🌸 day is never read; rows with no scale, outside
the window or of another account are not returned; the moon days reach one day past each end;
and the read stays fast on a 9 000-day account."""

import base64
import time as clock
from collections.abc import Generator
from contextlib import contextmanager
from datetime import date, timedelta
from uuid import UUID

import pytest
from sqlalchemy import event, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncEngine

from tristhana.domain.accounts import IdentityKey, IdentityProvider, NewAccount
from tristhana.domain.check_in_trends import ScaleDay, window
from tristhana.domain.days import DayLog, DayStatus
from tristhana.domain.moon import MoonDay, MoonDayKind
from tristhana.infrastructure.crypto import FieldCipher
from tristhana.infrastructure.db.accounts import SqlAccountRepository
from tristhana.infrastructure.db.check_in_trends import SqlCheckInTrendsRepository, facts_statement
from tristhana.infrastructure.db.days import SqlDayLogRepository
from tristhana.infrastructure.db.moon import SqlMoonCalendarRepository

pytestmark = pytest.mark.db

KEYS = "1:" + base64.b64encode(b"\x07" * 32).decode()
TODAY = date(2026, 11, 11)
START, END = window(TODAY)
ZONE = "Asia/Almaty"


async def _account(engine: AsyncEngine, telegram_id: str) -> UUID:
    created = await SqlAccountRepository(engine).create_with_identity(
        IdentityKey(IdentityProvider.TELEGRAM, telegram_id),
        NewAccount(display_name="A", locale="en"),
    )
    return created.id


async def _log(engine: AsyncEngine, me: UUID, on: date, status: DayStatus) -> None:
    await SqlDayLogRepository(engine, FieldCipher(KEYS)).upsert(me, DayLog(on, status), ZONE)


async def _check_in(
    engine: AsyncEngine,
    me: UUID,
    on: date,
    mood: int | None = None,
    energy: int | None = None,
    effort: int | None = None,
    tags: tuple[str, ...] = (),
) -> None:
    """Raw, so a row can sit on a day that is not Practiced (the ADR-0024 race)."""
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO tristhana.check_in (account_id, local_date, mood, energy, effort,"
                " tags) VALUES (:a, :d, :m, :e, :f, CAST(:t AS text[]))"
            ),
            {"a": me, "d": on, "m": mood, "e": energy, "f": effort, "t": list(tags)},
        )


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


def test_the_statement_never_names_a_sealed_column_or_the_tags() -> None:
    sql = str(
        facts_statement(UUID(int=1), "mysuru", START, END).compile(dialect=postgresql.dialect())
    )

    assert "sealed" not in sql
    assert "tags" not in sql
    assert "status" in sql


async def test_one_statement_reads_the_scales_of_practiced_days(engine: AsyncEngine) -> None:
    me = await _account(engine, "1")
    for on, scales in (
        (date(2026, 11, 3), (4, 5, 2)),
        (date(2026, 11, 2), (None, 3, None)),
    ):
        await _log(engine, me, on, DayStatus.PRACTICED)
        await _check_in(engine, me, on, *scales)

    with _statements(engine) as seen:
        facts = await SqlCheckInTrendsRepository(engine).facts(me, "mysuru", START, END)

    assert len(seen) == 1
    assert facts.days == (
        ScaleDay(date(2026, 11, 2), None, 3, None),
        ScaleDay(date(2026, 11, 3), 4, 5, 2),
    )
    assert facts.moon == ()


@pytest.mark.parametrize("status", [DayStatus.REST, DayStatus.SKIPPED, DayStatus.LADIES])
async def test_a_stray_check_in_on_a_day_that_is_not_practiced_is_never_read(
    engine: AsyncEngine, status: DayStatus
) -> None:
    me = await _account(engine, "2")
    await _log(engine, me, date(2026, 11, 2), DayStatus.PRACTICED)
    await _check_in(engine, me, date(2026, 11, 2), energy=3)
    await _log(engine, me, date(2026, 11, 3), status)  # 🌸 is stored as plain `rest`
    await _check_in(engine, me, date(2026, 11, 3), mood=1, energy=1, effort=1)

    facts = await SqlCheckInTrendsRepository(engine).facts(me, "mysuru", START, END)

    assert [d.local_date for d in facts.days] == [date(2026, 11, 2)]


async def test_rows_without_a_scale_outside_the_window_or_of_others_stay_out(
    engine: AsyncEngine,
) -> None:
    me, other = await _account(engine, "3"), await _account(engine, "4")
    inside = date(2026, 11, 2)
    for who, on, scales, tags in (
        (me, inside, (None, 4, None), ()),
        (me, date(2026, 11, 4), (None, None, None), ("stiff",)),  # tags only
        (me, START - timedelta(days=1), (3, 3, 3), ()),
        (me, END + timedelta(days=1), (3, 3, 3), ()),
        (other, inside, (5, 5, 5), ()),
    ):
        await _log(engine, who, on, DayStatus.PRACTICED)
        await _check_in(engine, who, on, *scales, tags=tags)

    facts = await SqlCheckInTrendsRepository(engine).facts(me, "mysuru", START, END)

    assert facts.days == (ScaleDay(inside, None, 4, None),)


async def test_the_moon_days_reach_one_day_past_each_end(engine: AsyncEngine) -> None:
    me = await _account(engine, "5")
    moon = SqlMoonCalendarRepository(engine)
    edge = [
        MoonDay(START - timedelta(days=2), MoonDayKind.PURNIMA),
        MoonDay(START - timedelta(days=1), MoonDayKind.AMAVASYA),
    ]
    await moon.replace_year("mysuru", 2025, edge, "test")
    this_year = [
        MoonDay(date(2026, 10, 26), MoonDayKind.KSHAYA_PURNIMA),
        MoonDay(END + timedelta(days=1), MoonDayKind.AMAVASYA),
        MoonDay(END + timedelta(days=2), MoonDayKind.PURNIMA),
    ]
    await moon.replace_year("mysuru", 2026, this_year, "test")
    await moon.replace_year("almaty", 2026, [MoonDay(date(2026, 10, 27), MoonDayKind.PURNIMA)], "t")

    facts = await SqlCheckInTrendsRepository(engine).facts(me, "mysuru", START, END)

    assert facts.moon == (edge[1], this_year[0], this_year[1])
    assert facts.days == ()


async def test_a_9000_day_account_reads_only_its_window_fast(engine: AsyncEngine) -> None:
    me = await _account(engine, "6")
    first = TODAY - timedelta(days=8999)
    async with engine.connect() as conn:
        await conn.execute(
            text(
                "INSERT INTO tristhana.day_log (account_id, local_date, status, timezone)"
                " SELECT :a, d::date, 'practiced', :z"
                " FROM generate_series(CAST(:s AS date), CAST(:t AS date), '1 day') d"
            ),
            {"a": me, "z": ZONE, "s": first, "t": TODAY},
        )
        await conn.execute(
            text(
                "INSERT INTO tristhana.check_in (account_id, local_date, mood, energy, effort)"
                " SELECT account_id, local_date, 3, 4, 2 FROM tristhana.day_log"
                " WHERE account_id = :a"
            ),
            {"a": me},
        )
        await conn.execute(
            text(
                "INSERT INTO tristhana.moon_day (location, date, kind)"
                " SELECT 'mysuru', d::date, 'purnima'"
                " FROM generate_series(CAST(:s AS date), CAST(:t AS date), '15 days') d"
            ),
            {"s": first, "t": TODAY},
        )
        await conn.execute(text("ANALYZE tristhana.day_log, tristhana.check_in"))
        await conn.commit()
    repo = SqlCheckInTrendsRepository(engine)

    timings: list[float] = []
    facts = await repo.facts(me, "mysuru", START, END)  # warm
    for _ in range(5):
        began = clock.perf_counter()
        facts = await repo.facts(me, "mysuru", START, END)
        timings.append((clock.perf_counter() - began) * 1000)

    assert len(facts.days) == (END - START).days + 1
    print(f"check-in trend facts, 9000-day account: best {min(timings):.1f} ms")
    assert min(timings) < 60  # the Q283 limit; measured far below
