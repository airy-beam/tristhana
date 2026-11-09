"""GM-02 facts on real Postgres (spec §4, §8, §9): one statement over plain columns (never
`sealed_status` or a period's sealed kind), so a 😌 and a sealed 🌸 give identical facts; the
practice details are slot 1; the moon dates are the given calendar from the first logged date
to today; the ledger and the position and item events, oldest first; an undone event (and its
badge) is gone; and the statement stays under 30 ms on a 9 000-day account."""

import base64
import time as clock
from collections.abc import Generator
from contextlib import contextmanager
from datetime import date, time, timedelta
from uuid import UUID

import pytest
from sqlalchemy import event, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncEngine

from tristhana.application.practice_patch import PracticePatch
from tristhana.domain.accounts import IdentityKey, IdentityProvider, NewAccount
from tristhana.domain.badges import BadgeFacts
from tristhana.domain.days import DayLog, DayStatus
from tristhana.domain.moon import MoonDay, MoonDayKind
from tristhana.domain.practice import PracticeContext
from tristhana.domain.progression import Change, EventKind, Position, Progression
from tristhana.domain.rest_periods import RestPeriod
from tristhana.infrastructure.crypto import FieldCipher
from tristhana.infrastructure.db.accounts import SqlAccountRepository
from tristhana.infrastructure.db.badges import SqlBadgeFactsRepository, facts_statement
from tristhana.infrastructure.db.days import SqlDayLogRepository
from tristhana.infrastructure.db.moon import SqlMoonCalendarRepository
from tristhana.infrastructure.db.practice import SqlPracticeRepository
from tristhana.infrastructure.db.progression import SqlProgressionRepository
from tristhana.infrastructure.db.rest_periods import SqlRestPeriodRepository

pytestmark = pytest.mark.db

KEYS = "1:" + base64.b64encode(b"\x07" * 32).decode()
TODAY = date(2026, 11, 9)
MOON = date(2026, 11, 5)
ZONE = "Asia/Almaty"


async def _account(engine: AsyncEngine, telegram_id: str) -> UUID:
    created = await SqlAccountRepository(engine).create_with_identity(
        IdentityKey(IdentityProvider.TELEGRAM, telegram_id),
        NewAccount(display_name="A", locale="en"),
    )
    return created.id


async def _moon(engine: AsyncEngine, location: str, *days: date) -> None:
    await SqlMoonCalendarRepository(engine).replace_year(
        location, 2026, [MoonDay(d, MoonDayKind.PURNIMA) for d in days], "test"
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


def test_the_statement_never_names_a_sealed_column() -> None:
    sql = str(
        facts_statement(UUID(int=1), "mysuru", TODAY).compile(dialect=postgresql.dialect())
    ).lower()

    assert "sealed" not in sql
    assert "attendance" not in sql


async def test_facts_in_one_statement(engine: AsyncEngine) -> None:
    me = await _account(engine, "1")
    days = SqlDayLogRepository(engine, FieldCipher(KEYS))
    practices = SqlPracticeRepository(engine)
    await days.upsert(me, DayLog(date(2026, 10, 1), DayStatus.PRACTICED), ZONE)
    await days.upsert(me, DayLog(date(2026, 10, 2), DayStatus.PRACTICED), ZONE)
    await days.upsert(me, DayLog(date(2026, 10, 3), DayStatus.PRACTICED), ZONE)
    await days.upsert(me, DayLog(MOON, DayStatus.MOON), ZONE)
    await practices.save(me, date(2026, 10, 1), PracticePatch.of(context=PracticeContext.LED))
    await practices.save(
        me,
        date(2026, 10, 2),
        PracticePatch.of(context=PracticeContext.SELF, start_time=time(5, 30), timezone=ZONE),
    )
    await practices.save(me, date(2026, 10, 3), PracticePatch.of(context=PracticeContext.MYSORE))
    await SqlRestPeriodRepository(engine, FieldCipher(KEYS)).place(
        me, RestPeriod(date(2026, 10, 20), date(2026, 10, 22), DayStatus.TRAVEL)
    )
    # Before the first logged date, after today, another city: none of them are read.
    await _moon(engine, "mysuru", date(2026, 9, 1), MOON, date(2026, 11, 24))
    await _moon(engine, "almaty", date(2026, 11, 4))
    async with engine.connect() as conn:
        await conn.execute(
            text(
                "INSERT INTO tristhana.practice_milestone (account_id, threshold, celebrated)"
                " VALUES (:a, 100, false)"
            ),
            {"a": me},
        )
    progression = SqlProgressionRepository(engine)
    navasana, kurmasana = Position("primary", "navasana"), Position("primary", "kurmasana")
    first = await progression.apply(
        me, Change(EventKind.START, date(2026, 10, 1), Progression(navasana), after=navasana),
        None, me, before=None,
    )  # fmt: skip
    assert first is not None
    item = await progression.apply(
        me,
        Change(EventKind.ITEM_GIVEN, date(2026, 10, 2), Progression(navasana, frozenset({"drop-backs"})), item="drop-backs"),  # noqa: E501
        first.id, me, before=navasana,
    )  # fmt: skip
    assert item is not None
    removed = await progression.apply(
        me,
        Change(EventKind.ITEM_REMOVED, date(2026, 10, 3), Progression(navasana), item="drop-backs"),
        item.id, me, before=navasana,
    )  # fmt: skip
    assert removed is not None
    given = await progression.apply(
        me,
        Change(EventKind.GIVEN, date(2026, 10, 4), Progression(kurmasana), navasana, kurmasana),
        removed.id, me, before=navasana,
    )  # fmt: skip
    assert given is not None
    other = await _account(engine, "2")
    await days.upsert(other, DayLog(date(2026, 1, 1), DayStatus.PRACTICED), ZONE)

    repo = SqlBadgeFactsRepository(engine)
    with _statements(engine) as seen:
        facts = await repo.facts(me, "mysuru", TODAY)

    assert len(seen) == 1
    assert facts.logged == {
        date(2026, 10, 1): DayStatus.PRACTICED,
        date(2026, 10, 2): DayStatus.PRACTICED,
        date(2026, 10, 3): DayStatus.PRACTICED,
        MOON: DayStatus.MOON,
    }
    assert (facts.led, facts.self_) == ((date(2026, 10, 1),), (date(2026, 10, 2),))
    assert facts.starts == ((date(2026, 10, 2), time(5, 30)),)
    assert facts.covered == {date(2026, 10, 20), date(2026, 10, 21), date(2026, 10, 22)}
    assert facts.moon == {MOON}
    assert facts.kept_counts == {100}
    assert [(e.kind, e.occurred_on, e.after, e.item) for e in facts.events] == [
        (EventKind.START, date(2026, 10, 1), navasana, None),
        (EventKind.ITEM_GIVEN, date(2026, 10, 2), None, "drop-backs"),
        (EventKind.ITEM_REMOVED, date(2026, 10, 3), None, "drop-backs"),
        (EventKind.GIVEN, date(2026, 10, 4), kurmasana, None),
    ]


async def test_undo_deletes_the_event_and_the_badge_goes(engine: AsyncEngine) -> None:
    from tests.domain.test_badges import ASANAS, track
    from tristhana.domain.badges import earned
    from tristhana.domain.rest_days import NEVER_CHOSEN

    me = await _account(engine, "7")
    progression = SqlProgressionRepository(engine)
    navasana, supta = Position("primary", "navasana"), Position("primary", "supta-kurmasana")
    start = await progression.apply(
        me, Change(EventKind.START, date(2026, 10, 1), Progression(navasana), after=navasana),
        None, me, before=None,
    )  # fmt: skip
    assert start is not None
    given = await progression.apply(
        me, Change(EventKind.GIVEN, date(2026, 10, 2), Progression(supta), navasana, supta),
        start.id, me, before=navasana,
    )  # fmt: skip
    assert given is not None
    repo = SqlBadgeFactsRepository(engine)

    def keys(facts: BadgeFacts) -> set[str]:
        found = earned(ASANAS, facts, track(), off=NEVER_CHOSEN, joined=TODAY, today=TODAY)
        return {e.key for e in found}

    assert "supta-kurmasana" in keys(await repo.facts(me, "mysuru", TODAY))
    assert await progression.undo(me, given.id)
    after = await repo.facts(me, "mysuru", TODAY)
    assert [e.kind for e in after.events] == [EventKind.START]
    assert "supta-kurmasana" not in keys(after)


async def test_an_empty_account_has_empty_facts(engine: AsyncEngine) -> None:
    me = await _account(engine, "3")
    await _moon(engine, "mysuru", MOON)

    facts = await SqlBadgeFactsRepository(engine).facts(me, "mysuru", TODAY)

    assert (facts.logged, facts.moon, facts.events, facts.covered) == ({}, frozenset(), (), set())


async def test_a_rest_day_and_a_sealed_ladies_day_read_the_same(engine: AsyncEngine) -> None:
    days = SqlDayLogRepository(engine, FieldCipher(KEYS))
    periods = SqlRestPeriodRepository(engine, FieldCipher(KEYS))
    await _moon(engine, "mysuru", MOON)
    found: list[BadgeFacts] = []
    for telegram_id, kind, period in (
        ("4", DayStatus.REST, DayStatus.SICK),
        ("5", DayStatus.LADIES, DayStatus.LADIES),
    ):
        me = await _account(engine, telegram_id)
        await days.upsert(me, DayLog(date(2026, 11, 1), DayStatus.PRACTICED), ZONE)
        await days.upsert(me, DayLog(MOON, kind), ZONE)
        await periods.place(me, RestPeriod(date(2026, 11, 6), date(2026, 11, 8), period))
        found.append(await SqlBadgeFactsRepository(engine).facts(me, "mysuru", TODAY))

    assert found[0] == found[1]
    assert found[0].logged[MOON] is DayStatus.REST


async def test_9000_days_read_under_30_ms(engine: AsyncEngine) -> None:
    me = await _account(engine, "6")
    start = TODAY - timedelta(days=8999)
    async with engine.connect() as conn:
        await conn.execute(
            text(
                "INSERT INTO tristhana.day_log (account_id, local_date, status, timezone)"
                " SELECT :a, d::date, CASE WHEN extract(dow FROM d) = 6 THEN 'moon'"
                " ELSE 'practiced' END, :z"
                " FROM generate_series(CAST(:s AS date), CAST(:t AS date), '1 day') d"
            ),
            {"a": me, "z": ZONE, "s": start, "t": TODAY},
        )
        await conn.execute(
            text(
                "INSERT INTO tristhana.practice"
                " (account_id, local_date, context, start_time, timezone)"
                " SELECT account_id, local_date, 'mysore', '05:45', :z"
                " FROM tristhana.day_log WHERE account_id = :a AND status = 'practiced'"
            ),
            {"a": me, "z": ZONE},
        )
        await conn.execute(
            text(
                "INSERT INTO tristhana.moon_day (location, date, kind)"
                " SELECT 'mysuru', d::date, 'purnima'"
                " FROM generate_series(CAST(:s AS date), CAST(:t AS date), '15 days') d"
            ),
            {"s": start, "t": TODAY},
        )
        await conn.execute(text("ANALYZE tristhana.day_log, tristhana.practice"))
    repo = SqlBadgeFactsRepository(engine)

    timings: list[float] = []
    facts = await repo.facts(me, "mysuru", TODAY)  # warm
    for _ in range(5):
        began = clock.perf_counter()
        facts = await repo.facts(me, "mysuru", TODAY)
        timings.append((clock.perf_counter() - began) * 1000)

    assert len(facts.logged) == 9000
    print(f"badge facts, 9000 days: best {min(timings):.1f} ms")
    assert min(timings) < 30
