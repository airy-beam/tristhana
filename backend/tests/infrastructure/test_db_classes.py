"""SC-02 on real Postgres (spec §3, §6, §7, §8; ADR-0034): every CHECK; the composite teacher
FK set to NULL on staff removal and on the teacher's account deletion; the shala cascade; the
window read matching the fakes for a seeded mix; one statement per read and per write; the plan
on 40 series; 0022 up/down/up with no drift; the app role; and the SQL guard matching
`can_manage_schedule` over the role matrix.

Assumed adapter: `tristhana.infrastructure.db.classes.SqlScheduleRepository(engine)`, with the
port shapes documented in `tests/schedule_fakes.py`."""

import asyncio
import itertools
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import event, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.fakes import FixedClock, InMemoryMoon, cities
from tests.infrastructure.test_db_shalas import (  # pyright: ignore[reportPrivateUsage]
    _person,  # pyright: ignore[reportPrivateUsage]
    _shala,  # pyright: ignore[reportPrivateUsage]
    _staff,  # pyright: ignore[reportPrivateUsage]
    _student,  # pyright: ignore[reportPrivateUsage]
)
from tests.schedule_fakes import InMemorySchedule
from tests.shala_fakes import InMemoryShalas, ShalaAccounts
from tristhana.application.classes import GetSchedule
from tristhana.application.policies import Principal, can_manage_schedule
from tristhana.application.ports.classes import ClassCaps, ClassDraft
from tristhana.domain.classes import (
    MAX_CLASSES,
    MAX_FUTURE_CLOSURES,
    MAX_FUTURE_SWAPS,
    ClassType,
    Override,
    OverrideStatus,
    Swap,
)
from tristhana.domain.moon import MoonDay, MoonDayKind
from tristhana.domain.shalas import Membership, ShalaRole
from tristhana.infrastructure.db import migrate
from tristhana.infrastructure.db.accounts import SqlAccountRepository
from tristhana.infrastructure.db.classes import SqlScheduleRepository
from tristhana.infrastructure.db.shalas import SqlShalaRepository

pytestmark = pytest.mark.db

TODAY = date(2026, 11, 7)
NOW = datetime(2026, 11, 7, 6, 0, tzinfo=UTC)
CAPS = ClassCaps(classes=MAX_CLASSES, closures=MAX_FUTURE_CLOSURES, swaps=MAX_FUTURE_SWAPS)
NOV = {d: date(2026, 11, d) for d in range(1, 31)}
_n = itertools.count(1)


def _draft(**kw: Any) -> ClassDraft:
    fields: dict[str, Any] = {
        "type": ClassType.MYSORE,
        "title": None,
        "online": False,
        "city": None,
        "teacher_id": None,
        "start": time(6, 0),
        "minutes": 210,
        "weekdays": frozenset({1, 2, 3, 4, 5}),
        "every": 1,
        "starts_on": NOV[2],
        "ends_on": None,
    }
    fields.update(kw)
    return ClassDraft(**fields)


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


async def _owned(engine: AsyncEngine) -> tuple[UUID, UUID]:
    owner, _ = await _person(engine, "Anna")
    return owner.id, await _shala(engine, owner.id)


async def _class(engine: AsyncEngine, shala: UUID, owner: UUID, **kw: Any) -> UUID:
    created = await SqlScheduleRepository(engine).create(shala, owner, _draft(**kw), CAPS, TODAY)
    assert created.done
    assert created.value is not None
    return created.value.id


# CHECKs

_VALID_CLASS = {
    "type": "mysore",
    "title": None,
    "online": False,
    "city": None,
    "start_time": time(6, 0),
    "minutes": 210,
    "weekdays": 31,
    "every": 1,
    "starts_on": NOV[2],
    "ends_on": None,
}


async def _insert_class(engine: AsyncEngine, shala: UUID, **over: Any) -> Any:
    values = _VALID_CLASS | over
    return await _sql(
        engine,
        "INSERT INTO tristhana.shala_class (shala_id, type, title, online, city, start_time,"
        " minutes, weekdays, every, starts_on, ends_on) VALUES (:shala, :type, :title, :online,"
        " :city, :start_time, :minutes, :weekdays, :every, :starts_on, :ends_on) RETURNING id",
        shala=shala,
        **values,
    )


async def test_a_valid_class_row_inserts(engine: AsyncEngine) -> None:
    _, shala = await _owned(engine)

    await _insert_class(engine, shala)
    await _insert_class(engine, shala, start_time=time(22, 0), minutes=120)  # ends at 24:00


@pytest.mark.parametrize(
    "over",
    [
        {"type": "yoga"},
        {"type": "1:1"},
        {"title": ""},
        {"title": "x" * 49},
        {"minutes": 14},
        {"minutes": 481},
        {"start_time": time(22, 0), "minutes": 121},
        {"weekdays": 128},
        {"weekdays": -1},
        {"every": 0},
        {"every": 5},
        {"ends_on": NOV[1]},
        {"weekdays": 0, "ends_on": NOV[20]},
        {"city": "berlin"},  # only an online class names a city
        {"online": True, "city": "Berlin"},  # a slug
    ],
    ids=str,
)
async def test_the_class_checks(engine: AsyncEngine, over: dict[str, Any]) -> None:
    _, shala = await _owned(engine)

    with pytest.raises((IntegrityError, DBAPIError)):
        await _insert_class(engine, shala, **over)


@pytest.mark.parametrize(
    ("column", "value"), [("days_off", 128), ("days_off", -1), ("moon_policy", "led")]
)
async def test_the_shala_setting_checks(engine: AsyncEngine, column: str, value: Any) -> None:
    _, shala = await _owned(engine)

    statement = f"UPDATE tristhana.shala SET {column} = :v WHERE id = :s"  # noqa: S608

    with pytest.raises((IntegrityError, DBAPIError)):
        await _sql(engine, statement, v=value, s=shala)


async def test_the_shala_defaults(engine: AsyncEngine) -> None:
    _, shala = await _owned(engine)

    row = (
        await _sql(
            engine, "SELECT days_off, moon_policy FROM tristhana.shala WHERE id = :s", s=shala
        )
    ).one()

    assert (row.days_off, row.moon_policy) == (None, "closed")


@pytest.mark.parametrize(
    "over",
    [
        {"moved_to": NOV[16]},  # 7 days
        {"moved_to": NOV[2]},
        {"status": "moved"},
        {"status": "cancelled", "start_time": time(7, 0)},  # a cancel changes nothing else
        {"status": "cancelled", "moved_to": NOV[10]},
    ],
    ids=str,
)
async def test_the_override_checks(engine: AsyncEngine, over: dict[str, Any]) -> None:
    _, shala = await _owned(engine)
    cls = (await _insert_class(engine, shala)).scalar_one()
    values = {"status": None, "moved_to": None, "start_time": None} | over

    with pytest.raises((IntegrityError, DBAPIError)):
        await _sql(
            engine,
            "INSERT INTO tristhana.shala_class_override (class_id, on_date, shala_id, status,"
            " moved_to, start_time) VALUES (:c, :on, :s, :status, :moved_to, :start_time)",
            c=cls,
            on=NOV[9],
            s=shala,
            **values,
        )


@pytest.mark.parametrize(
    ("start", "end"), [(NOV[10], NOV[9]), (NOV[1], NOV[1] + timedelta(days=92))], ids=str
)
async def test_the_closure_checks(engine: AsyncEngine, start: date, end: date) -> None:
    _, shala = await _owned(engine)

    with pytest.raises((IntegrityError, DBAPIError)):
        await _sql(
            engine,
            "INSERT INTO tristhana.shala_closure (id, shala_id, start_date, end_date)"
            " VALUES (gen_random_uuid(), :s, :a, :b)",
            s=shala,
            a=start,
            b=end,
        )


@pytest.mark.parametrize(("a", "b"), [(NOV[13], NOV[13]), (NOV[13], NOV[20]), (NOV[13], NOV[6])])
async def test_the_swap_checks(engine: AsyncEngine, a: date, b: date) -> None:
    _, shala = await _owned(engine)

    with pytest.raises((IntegrityError, DBAPIError)):
        await _sql(
            engine,
            "INSERT INTO tristhana.shala_swap (shala_id, from_date, to_date) VALUES (:s, :a, :b)",
            s=shala,
            a=a,
            b=b,
        )


async def test_one_swap_per_target_day(engine: AsyncEngine) -> None:
    _, shala = await _owned(engine)
    insert = "INSERT INTO tristhana.shala_swap (shala_id, from_date, to_date) VALUES (:s, :a, :b)"
    await _sql(engine, insert, s=shala, a=NOV[13], b=NOV[14])

    with pytest.raises(IntegrityError):
        await _sql(engine, insert, s=shala, a=NOV[15], b=NOV[14])


# The teacher FK and the cascades


async def test_removing_a_teacher_leaves_the_class_untaught(engine: AsyncEngine) -> None:
    owner, shala = await _owned(engine)
    boris, _ = await _person(engine, "Boris")
    await _staff(engine, shala, owner, boris.id, ShalaRole.TEACHER)
    cls = await _class(engine, shala, owner, teacher_id=boris.id)
    await SqlScheduleRepository(engine).set_override(
        shala,
        owner,
        cls,
        Override(
            on_date=NOV[9],
            status=None,
            moved_to=None,
            start=None,
            minutes=None,
            teacher_id=boris.id,
        ),
    )

    removed = await SqlShalaRepository(engine).remove_staff(shala, owner, boris.id)

    assert removed.done
    teacher = await _sql(
        engine, "SELECT teacher_id FROM tristhana.shala_class WHERE id = :c", c=cls
    )
    assert teacher.scalar_one() is None
    sub = await _sql(
        engine, "SELECT teacher_id FROM tristhana.shala_class_override WHERE class_id = :c", c=cls
    )
    assert sub.scalar_one() is None


async def test_deleting_the_teachers_account_leaves_the_class_untaught(engine: AsyncEngine) -> None:
    owner, shala = await _owned(engine)
    boris, _ = await _person(engine, "Boris")
    await _staff(engine, shala, owner, boris.id, ShalaRole.TEACHER)
    cls = await _class(engine, shala, owner, teacher_id=boris.id)

    assert await SqlAccountRepository(engine).delete(boris.id)

    row = await _sql(engine, "SELECT teacher_id FROM tristhana.shala_class WHERE id = :c", c=cls)
    assert row.scalar_one() is None


async def test_a_non_staff_teacher_is_refused(engine: AsyncEngine) -> None:
    _, shala = await _owned(engine)
    stranger, _ = await _person(engine, "Stranger")

    with pytest.raises((IntegrityError, DBAPIError)):
        await _sql(
            engine,
            "INSERT INTO tristhana.shala_class (shala_id, type, start_time, minutes, weekdays,"
            " starts_on, teacher_id) VALUES (:s, 'led', '07:00', 90, 1, :d, :t)",
            s=shala,
            d=NOV[2],
            t=stranger.id,
        )


async def test_deleting_a_shala_takes_every_class_row(engine: AsyncEngine) -> None:
    owner, shala = await _owned(engine)
    repo = SqlScheduleRepository(engine)
    cls = await _class(engine, shala, owner)
    await repo.set_override(
        shala,
        owner,
        cls,
        Override(NOV[9], OverrideStatus.CANCELLED, None, None, None, None),
    )
    await repo.add_closure(shala, owner, NOV[20], NOV[22], CAPS, TODAY)
    await _sql(engine, "UPDATE tristhana.shala SET days_off = 32 WHERE id = :s", s=shala)
    await repo.add_swap(shala, owner, Swap(NOV[13], NOV[14]), CAPS, TODAY)

    assert (await SqlShalaRepository(engine).delete(shala, owner)).done

    for table in ("shala_class", "shala_class_override", "shala_closure", "shala_swap"):
        left = await _sql(engine, f"SELECT count(*) FROM tristhana.{table}")  # noqa: S608
        assert left.scalar_one() == 0, table


# The window: the same occurrences as the fakes, in one statement


async def _seed_mix(repo: Any, shala: UUID, owner: UUID) -> None:
    mysore = await repo.create(shala, owner, _draft(), CAPS, TODAY)
    led = await repo.create(
        shala,
        owner,
        _draft(type=ClassType.LED, weekdays=frozenset({5}), start=time(18, 30), minutes=90),
        CAPS,
        TODAY,
    )
    await repo.create(
        shala,
        owner,
        _draft(type=ClassType.PRIVATE, weekdays=frozenset({2}), start=time(12, 0), minutes=60),
        CAPS,
        TODAY,
    )
    await repo.create(
        shala,
        owner,
        _draft(
            type=ClassType.LED,
            online=True,
            city="berlin",
            weekdays=frozenset({1, 3}),
            every=2,
            start=time(7, 0),
            minutes=90,
        ),
        CAPS,
        TODAY,
    )
    await repo.set_override(
        shala,
        owner,
        mysore.value.id,
        Override(NOV[10], OverrideStatus.CANCELLED, None, None, None, None),
    )
    await repo.set_override(
        shala, owner, mysore.value.id, Override(NOV[11], None, NOV[12], time(7, 0), 90, None)
    )
    await repo.set_override(
        shala, owner, led.value.id, Override(NOV[20], OverrideStatus.HELD, None, None, None, None)
    )
    await repo.add_closure(shala, owner, NOV[23], NOV[24], CAPS, TODAY)
    await repo.add_swap(shala, owner, Swap(NOV[13], NOV[14]), CAPS, TODAY)


def _shape(occurrences: Any) -> list[tuple[Any, ...]]:
    return [
        (
            o.key,
            o.on,
            o.start,
            o.end,
            o.starts_at,
            o.type,
            o.online,
            o.cancelled,
            o.moved,
            o.swapped_from,
        )
        for o in occurrences
    ]


async def test_the_window_matches_the_fakes_for_a_seeded_mix(engine: AsyncEngine) -> None:
    anna, key = await _person(engine, "Anna")
    owner = anna.id
    shala = await _shala(engine, owner)
    await _sql(engine, "UPDATE tristhana.shala SET days_off = 32 WHERE id = :s", s=shala)
    await _sql(
        engine,
        "INSERT INTO tristhana.moon_day (location, date, kind) VALUES ('almaty', :a, 'purnima'),"
        " ('almaty', :b, 'amavasya') ON CONFLICT DO NOTHING",
        a=NOV[13],
        b=NOV[20],
    )
    sql = SqlScheduleRepository(engine)
    await _seed_mix(sql, shala, owner)
    account = await SqlAccountRepository(engine).find_by_identity(key)
    assert account is not None

    clock = FixedClock(NOW)
    accounts = ShalaAccounts(clock=clock)
    shalas = InMemoryShalas(accounts)
    accounts.shalas = shalas
    accounts.accounts[owner] = account
    fake_shala = shalas.add_shala(owner, days_off=frozenset({6})).id
    moon = InMemoryMoon()
    moon.days_by_location["almaty"] = [
        MoonDay(NOV[13], MoonDayKind.PURNIMA),
        MoonDay(NOV[20], MoonDayKind.AMAVASYA),
    ]
    fake = InMemorySchedule(shalas, moon)
    await _seed_mix(fake, fake_shala, owner)

    me = Principal(account)
    real = await GetSchedule(sql, clock, cities()).execute(me, shala, NOV[9], 21)
    expected = await GetSchedule(fake, clock, cities()).execute(me, fake_shala, NOV[9], 21)

    assert _shape(real.occurrences) == _shape(expected.occurrences)
    assert [(d.date, d.moon, d.day_off, d.swap_from) for d in real.days] == [
        (d.date, d.moon, d.day_off, d.swap_from) for d in expected.days
    ]


async def test_the_window_is_one_statement(engine: AsyncEngine) -> None:
    owner, shala = await _owned(engine)
    await _seed_mix(SqlScheduleRepository(engine), shala, owner)

    with _statements(engine) as seen:
        window = await SqlScheduleRepository(engine).window(shala, owner, NOV[9], NOV[15])

    assert window is not None
    assert len(seen) == 1


async def test_every_write_is_one_statement(engine: AsyncEngine) -> None:
    owner, shala = await _owned(engine)
    repo = SqlScheduleRepository(engine)
    cls = await _class(engine, shala, owner)
    cancel = Override(NOV[9], OverrideStatus.CANCELLED, None, None, None, None)
    calls = [
        lambda: repo.create(shala, owner, _draft(), CAPS, TODAY),
        lambda: repo.update(shala, owner, cls, _draft(minutes=180), None),
        lambda: repo.set_override(shala, owner, cls, cancel),
        lambda: repo.clear_override(shala, owner, cls, NOV[9]),
        lambda: repo.add_closure(shala, owner, NOV[20], NOV[21], CAPS, TODAY),
        lambda: repo.delete(shala, owner, cls),
    ]

    for call in calls:
        with _statements(engine) as seen:
            await call()
        assert len(seen) == 1, seen


async def test_a_non_member_reads_nothing(engine: AsyncEngine) -> None:
    owner, shala = await _owned(engine)
    stranger, _ = await _person(engine, "Stranger")
    await _class(engine, shala, owner)

    assert await SqlScheduleRepository(engine).window(shala, stranger.id, NOV[9], NOV[15]) is None


async def test_the_window_plan_on_40_series_uses_the_indexes(engine: AsyncEngine) -> None:
    owner, shala = await _owned(engine)
    for i in range(40):
        await _class(engine, shala, owner, start=time(5 + i % 15, 0), minutes=60)
    loads: list[tuple[str, Any]] = []

    def record(_conn: object, _cursor: object, statement: str, params: Any, *_: object) -> None:
        loads.append((statement, params))

    event.listen(engine.sync_engine, "before_cursor_execute", record)
    try:
        await SqlScheduleRepository(engine).window(shala, owner, NOV[9], NOV[15])
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", record)
    [(statement, params)] = loads
    async with engine.connect() as conn:
        await conn.exec_driver_sql("SET enable_seqscan = off")
        plan = "\n".join(
            str(row[0]) for row in await conn.exec_driver_sql("EXPLAIN " + statement, params)
        )

    assert "shala_class" in plan
    assert "Seq Scan on shala_class " not in plan
    assert "Seq Scan on shala_class_override" not in plan


# The SQL guard matches the policy


_ROLES: dict[str, ShalaRole | None] = {
    "admin": ShalaRole.ADMIN,
    "teacher": ShalaRole.TEACHER,
    "assistant": ShalaRole.ASSISTANT,
    "office": ShalaRole.OFFICE,
    "student": None,
}


@pytest.mark.parametrize("role", list(_ROLES))
async def test_the_create_guard_matches_can_manage_schedule(engine: AsyncEngine, role: str) -> None:
    owner, shala = await _owned(engine)
    who, _ = await _person(engine, f"P{next(_n)}")
    if _ROLES[role] is None:
        await _student(engine, shala, owner, who.id)
        membership = Membership(shala, False, frozenset(), True)
    else:
        await _staff(engine, shala, owner, who.id, _ROLES[role])  # type: ignore[arg-type]
        membership = Membership(shala, False, frozenset({_ROLES[role]}), False)  # type: ignore[arg-type]

    created = await SqlScheduleRepository(engine).create(shala, who.id, _draft(), CAPS, TODAY)

    assert created.me is not None
    assert created.done is can_manage_schedule(membership)


async def test_the_class_cap_holds(engine: AsyncEngine) -> None:
    owner, shala = await _owned(engine)
    for _ in range(MAX_CLASSES):
        await _class(engine, shala, owner)

    capped = await SqlScheduleRepository(engine).create(shala, owner, _draft(), CAPS, TODAY)

    assert (capped.done, capped.value) == (True, None)


# Migration 0022 and the app role


async def test_0022_up_down_up_and_no_drift(migrated_url: str, engine: AsyncEngine) -> None:
    tables = text(
        "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'tristhana'"
        " AND table_name IN ('shala_class', 'shala_class_override', 'shala_closure', 'shala_swap')"
    )
    await asyncio.to_thread(migrate.downgrade, migrated_url, "0021")
    try:
        async with engine.connect() as conn:
            assert (await conn.execute(tables)).scalar_one() == 0
    finally:
        await asyncio.to_thread(migrate.upgrade, migrated_url)
    async with engine.connect() as conn:
        assert (await conn.execute(tables)).scalar_one() == 4
    await asyncio.to_thread(migrate.check, migrated_url)


async def test_class_writes_work_as_the_app_role(engine: AsyncEngine) -> None:
    async with engine.connect() as conn:
        missing = await conn.execute(
            text(
                "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace"
                " WHERE n.nspname = 'tristhana' AND c.relname IN ('shala_class',"
                " 'shala_class_override', 'shala_closure', 'shala_swap') AND c.relkind = 'r'"
                " AND EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'tristhana_app')"
                " AND NOT has_table_privilege('tristhana_app', c.oid,"
                " 'SELECT, INSERT, UPDATE, DELETE')"
            )
        )
        assert missing.scalars().all() == []


# Review fixes


async def test_a_one_off_class_inserts(engine: AsyncEngine) -> None:
    """`ends_on` NULL with no weekdays: NULL AND FALSE must not reject it."""
    owner, shala = await _owned(engine)

    created = await SqlScheduleRepository(engine).create(
        shala, owner, _draft(type=ClassType.WORKSHOP, weekdays=frozenset()), CAPS, TODAY
    )

    assert created.value is not None


async def _overrides(engine: AsyncEngine, cls: UUID) -> set[date]:
    rows = await _sql(
        engine, "SELECT on_date FROM tristhana.shala_class_override WHERE class_id = :c", c=cls
    )
    return {r.on_date for r in rows}


@pytest.mark.parametrize("every", [1, 2])
async def test_an_all_dates_update_keeps_every_override_its_rule_still_makes(
    engine: AsyncEngine, every: int
) -> None:
    """The `_produces` SQL (integer weeks) agrees with `rule_dates` on every weekday."""
    owner, shala = await _owned(engine)
    repo = SqlScheduleRepository(engine)
    days = frozenset(range(1, 8))
    cls = await _class(engine, shala, owner, weekdays=days, every=every)
    kept = {NOV[2] + timedelta(days=i) for i in range(7)}  # Mon 2 .. Sun 8: week 0
    for day in kept | {NOV[9] + timedelta(days=i) for i in range(7)}:
        await repo.set_override(shala, owner, cls, Override(day, OverrideStatus.CANCELLED))

    await repo.update(shala, owner, cls, _draft(weekdays=days, every=every, minutes=180), None)

    expected = kept if every == 2 else kept | {NOV[9] + timedelta(days=i) for i in range(7)}
    assert await _overrides(engine, cls) == expected


async def test_a_split_moves_later_overrides_on_every_weekday(engine: AsyncEngine) -> None:
    owner, shala = await _owned(engine)
    repo = SqlScheduleRepository(engine)
    days = frozenset(range(1, 8))
    cls = await _class(engine, shala, owner, weekdays=days)
    later = {NOV[16] + timedelta(days=i) for i in range(7)}  # Mon 16 .. Sun 22
    for day in {NOV[10], *later}:
        await repo.set_override(shala, owner, cls, Override(day, OverrideStatus.CANCELLED))

    split = await repo.update(shala, owner, cls, _draft(weekdays=days, start=time(7)), NOV[16])

    assert split.value is not None
    assert await _overrides(engine, cls) == {NOV[10]}
    assert await _overrides(engine, split.value.id) == later


async def test_hold_anyway_keeps_a_move_and_a_substitute(engine: AsyncEngine) -> None:
    owner, shala = await _owned(engine)
    repo = SqlScheduleRepository(engine)
    cls = await _class(engine, shala, owner)
    moved = Override(NOV[10], None, NOV[13], time(7), 90, None)
    await repo.set_override(shala, owner, cls, moved)

    await repo.set_override(shala, owner, cls, Override(NOV[10], OverrideStatus.HELD), keep=True)

    row = (
        await _sql(
            engine,
            "SELECT status, moved_to, start_time, minutes FROM tristhana.shala_class_override"
            " WHERE class_id = :c",
            c=cls,
        )
    ).one()
    assert tuple(row) == ("held", NOV[13], time(7), 90)


async def test_a_held_write_replaces_unless_it_keeps(engine: AsyncEngine) -> None:
    owner, shala = await _owned(engine)
    teacher, _ = await _person(engine, "Tara")
    await _staff(engine, shala, owner, teacher.id, ShalaRole.TEACHER)
    repo = SqlScheduleRepository(engine)
    cls = await _class(engine, shala, owner)
    await repo.set_override(shala, owner, cls, Override(NOV[10], OverrideStatus.HELD))

    sub = Override(NOV[10], OverrideStatus.HELD, teacher_id=teacher.id)
    query = "SELECT status, teacher_id FROM tristhana.shala_class_override WHERE class_id = :c"
    await repo.set_override(shala, owner, cls, sub)
    await repo.set_override(shala, owner, cls, Override(NOV[10], OverrideStatus.HELD), keep=True)
    kept = (await _sql(engine, query, c=cls)).one()
    await repo.set_override(shala, owner, cls, Override(NOV[10], OverrideStatus.HELD))
    replaced = (await _sql(engine, query, c=cls)).one()

    assert tuple(kept) == ("held", teacher.id)
    assert tuple(replaced) == ("held", None)
