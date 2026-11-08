"""SC-03 on real Postgres (spec §3, §6, §7, §8; ADR-0035): `member_windows` returns, in one
statement, the same window as `window` for every shala where I am a member (staff first, then
by name), my linked teacher ids, and my moon city's `moon_day` dates in the range; the
staff-only variant is SC-02's old `staff_windows`; a tap is 2 statements (the account load and
this read); the statement touches no log, rest or 🌸 table; no migration.

Assumed adapter: `tristhana.infrastructure.db.classes.SqlScheduleRepository(engine)`, with the
port shapes documented in `tests/schedule_fakes.py`."""

from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.fakes import FixedClock, cities
from tests.infrastructure.test_db_shalas import (  # pyright: ignore[reportPrivateUsage]
    _link,  # pyright: ignore[reportPrivateUsage]
    _person,  # pyright: ignore[reportPrivateUsage]
    _shala,  # pyright: ignore[reportPrivateUsage]
    _staff,  # pyright: ignore[reportPrivateUsage]
    _student,  # pyright: ignore[reportPrivateUsage]
)
from tristhana.application.classes import GetMySchedule, Only
from tristhana.application.policies import Principal
from tristhana.domain.classes import ClassType
from tristhana.domain.shalas import ShalaRole
from tristhana.infrastructure.db.accounts import SqlAccountRepository
from tristhana.infrastructure.db.classes import SqlScheduleRepository

pytestmark = pytest.mark.db

NOW = datetime(2026, 11, 9, 3, 0, tzinfo=UTC)  # Mon 9 Nov, 08:00 Almaty
NOV = {d: date(2026, 11, d) for d in range(1, 31)}
START, END = NOV[7], NOV[17]  # a week with the ±2 margin


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


async def _moon_days(engine: AsyncEngine, location: str, *days: date) -> None:
    for day in days:
        await _sql(
            engine,
            "INSERT INTO tristhana.moon_day (location, date, kind) VALUES (:l, :d, 'purnima')"
            " ON CONFLICT DO NOTHING",
            l=location,
            d=day,
        )


async def _draft_class(repo: SqlScheduleRepository, shala: UUID, owner: UUID, **kw: Any) -> UUID:
    from tests.infrastructure.test_db_classes import CAPS, TODAY, _draft  # pyright: ignore[reportPrivateUsage]

    created = await repo.create(shala, owner, _draft(**kw), CAPS, TODAY)
    assert created.value is not None
    return created.value.id


async def _world(engine: AsyncEngine) -> dict[str, Any]:
    """Anna owns "B Student Shala" (Sam studies there) and Olga owns "A Staff Shala" (Sam
    teaches there); Anna also owns "C Hidden" where Sam is no member. Sam follows Anna."""
    anna, _ = await _person(engine, "Anna")
    olga, _ = await _person(engine, "Olga")
    sam, sam_key = await _person(engine, "Sam")
    student = await _shala(engine, anna.id, name="B Student Shala")
    staff = await _shala(engine, olga.id, name="A Staff Shala")
    hidden = await _shala(engine, anna.id, city="berlin", name="C Hidden")
    await _student(engine, student, anna.id, sam.id)
    await _staff(engine, staff, olga.id, sam.id, ShalaRole.TEACHER)
    await _link(engine, sam.id, anna.id)
    repo = SqlScheduleRepository(engine)
    await _draft_class(repo, student, anna.id, teacher_id=anna.id)
    await _draft_class(repo, staff, olga.id, type=ClassType.LED, teacher_id=sam.id)
    await _draft_class(repo, hidden, anna.id, teacher_id=anna.id)
    await _moon_days(engine, "almaty", NOV[13])
    await _moon_days(engine, "mysuru", NOV[12], date(2026, 11, 27))
    return {
        "anna": anna,
        "sam": sam,
        "sam_key": sam_key,
        "student": student,
        "staff": staff,
        "hidden": hidden,
    }


async def test_member_windows_reads_every_shala_of_mine_in_one_statement(
    engine: AsyncEngine,
) -> None:
    w = await _world(engine)
    repo = SqlScheduleRepository(engine)

    with _statements(engine) as seen:
        mine = await repo.member_windows(w["sam"].id, START, END, moon_city="mysuru")

    assert len(seen) == 1
    assert [x.shala_id for x in mine.windows] == [w["staff"], w["student"]]  # staff first
    assert mine.windows[0] == await repo.window(w["staff"], w["sam"].id, START, END)
    assert mine.windows[1] == await repo.window(w["student"], w["sam"].id, START, END)
    assert mine.windows[0].me.roles == frozenset({ShalaRole.TEACHER})
    assert mine.windows[1].me.student is True
    assert mine.teachers == frozenset({w["anna"].id})
    assert mine.my_moon == frozenset({NOV[12]})  # Mysuru's, within the range only


async def test_staff_first_then_by_name(engine: AsyncEngine) -> None:
    w = await _world(engine)
    olga2, _ = await _person(engine, "Olga Two")
    first = await _shala(engine, olga2.id, name="0 First By Name")
    await _student(engine, first, olga2.id, w["sam"].id)

    mine = await SqlScheduleRepository(engine).member_windows(w["sam"].id, START, END)

    assert [x.shala_id for x in mine.windows] == [w["staff"], first, w["student"]]


async def test_the_staff_only_variant_is_the_old_staff_windows(engine: AsyncEngine) -> None:
    w = await _world(engine)
    repo = SqlScheduleRepository(engine)

    with _statements(engine) as seen:
        mine = await repo.member_windows(w["sam"].id, START, END, staff_only=True)

    assert len(seen) == 1
    assert mine.windows == (await repo.window(w["staff"], w["sam"].id, START, END),)


async def test_without_a_moon_city_there_are_no_moon_dates(engine: AsyncEngine) -> None:
    w = await _world(engine)

    mine = await SqlScheduleRepository(engine).member_windows(w["sam"].id, START, END)

    assert mine.my_moon == frozenset()


async def test_no_membership_reads_nothing(engine: AsyncEngine) -> None:
    await _world(engine)
    stranger, _ = await _person(engine, "Stranger")

    mine = await SqlScheduleRepository(engine).member_windows(stranger.id, START, END)

    assert (mine.windows, mine.teachers) == ((), frozenset())


async def test_the_statement_touches_no_log_rest_or_private_table(engine: AsyncEngine) -> None:
    w = await _world(engine)

    with _statements(engine) as seen:
        await SqlScheduleRepository(engine).member_windows(
            w["sam"].id, START, END, moon_city="almaty"
        )

    [statement] = seen
    for table in ("day_log", "rest_period", "check_in", "diary", "practice", "progression"):
        assert f"tristhana.{table}" not in statement, table
    assert "tristhana.moon_day" in statement
    assert "tristhana.teacher_link" in statement


async def test_a_tap_is_two_statements(engine: AsyncEngine) -> None:
    """The account load (with MD-02's inputs) and `member_windows`: nothing else."""
    w = await _world(engine)
    use_case = GetMySchedule(SqlScheduleRepository(engine), FixedClock(NOW), cities())

    with _statements(engine) as seen:
        account = await SqlAccountRepository(engine).find_by_identity(w["sam_key"])
        assert account is not None
        out = await use_case.execute(Principal(account), None)

    assert len(seen) == 2
    assert {s.id for s in out.shalas} == {w["staff"], w["student"]}
    assert w["hidden"] not in {r.shala_id for r in out.rows}


async def test_the_use_case_on_postgres_matches_the_week(engine: AsyncEngine) -> None:
    w = await _world(engine)
    account = await SqlAccountRepository(engine).find_by_identity(w["sam_key"])
    assert account is not None
    use_case = GetMySchedule(SqlScheduleRepository(engine), FixedClock(NOW), cities())

    every = await use_case.execute(Principal(account), None)
    teachers = await use_case.execute(Principal(account), None, only=Only.TEACHERS)
    mine = await use_case.execute(Principal(account), None, only=Only.MINE)

    assert (every.zone, every.today) == ("Asia/Almaty", NOV[9])
    assert len(every.rows) == 10  # Mon-Fri in both shalas
    assert {r.shala_id for r in teachers.rows} == {w["student"]}
    assert {r.occurrence.type for r in mine.rows} == {ClassType.LED}
    # Sam never chose and is staff at an Almaty shala: its city (MD-02).
    assert [d.date for d in every.days if d.my_moon] == [NOV[13]]
