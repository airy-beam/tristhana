"""MD-02 on real Postgres (spec §3, §5, §6, §7; ADR-0032): the account load carries `teaches`
and the main teacher in the same statement, identically for every method that returns an
account; its order is `effective_primary`'s; deletion cascades; the tick's candidates carry the
same inputs; `set_moon_location_if_unset` writes only on NULL, once under a race; the
sentinel fits the column; the lookups use the `teacher_link` indexes."""

import asyncio
import itertools
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.fakes import cities
from tristhana.application.ports.teacher_links import Caps
from tristhana.domain.accounts import (
    Account,
    IdentityKey,
    IdentityProvider,
    NewAccount,
    ProfileChange,
    ProfileUpdate,
    moon_follow_of,
)
from tristhana.domain.moon import FOLLOW_TEACHER, TeacherMoon, moon_follow
from tristhana.domain.notifications import DEFAULTS
from tristhana.domain.rest_days import DayOff
from tristhana.domain.teacher_links import MAX_STUDENTS, MAX_TEACHERS, effective_primary
from tristhana.infrastructure.db.accounts import SqlAccountRepository
from tristhana.infrastructure.db.notifications import SqlNotificationRepository
from tristhana.infrastructure.db.teacher_links import SqlTeacherLinkRepository

pytestmark = pytest.mark.db

ON = date(2026, 11, 7)
NOW = datetime(2026, 11, 7, 12, 0, tzinfo=UTC)
CAPS = Caps(teachers=MAX_TEACHERS, students=MAX_STUDENTS)
_users = itertools.count(60_000)
_codes = itertools.count(1)


def _key(tg: str) -> IdentityKey:
    return IdentityKey(IdentityProvider.TELEGRAM, tg)


async def _person(
    engine: AsyncEngine, name: str | None = "Person", moon: str | None = None
) -> tuple[Account, IdentityKey]:
    repo = SqlAccountRepository(engine)
    key = _key(str(next(_users)))
    account = await repo.create_with_identity(key, NewAccount(display_name=name, locale="en"))
    await repo.set_timezone_if_unset(account.id, "Asia/Almaty")
    if moon is not None:
        await _raw_moon(engine, account.id, moon)
    return account, key


async def _raw_moon(engine: AsyncEngine, account_id: UUID, moon: str | None) -> None:
    async with engine.connect() as conn:
        await conn.execute(
            text("UPDATE tristhana.account SET moon_location = :m WHERE id = :id"),
            {"m": moon, "id": account_id},
        )
        await conn.commit()


async def _link(
    engine: AsyncEngine, student: UUID, teacher: UUID, at: datetime | None = None
) -> None:
    repo = SqlTeacherLinkRepository(engine)
    accepted = await repo.accept(
        await repo.invite(teacher, f"code{next(_codes):012d}"), student, CAPS, ON
    )
    assert accepted is not None
    assert accepted.created
    if at is not None:
        async with engine.connect() as conn:
            await conn.execute(
                text(
                    "UPDATE tristhana.teacher_link SET created_at = :at"
                    " WHERE student_id = :s AND teacher_id = :t"
                ),
                {"at": at, "s": student, "t": teacher},
            )
            await conn.commit()


async def _find(engine: AsyncEngine, key: IdentityKey) -> Account:
    found = await SqlAccountRepository(engine).find_by_identity(key)
    assert found is not None
    return found


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


# The account load.


async def test_a_new_person_teaches_no_one_and_has_no_main_teacher(engine: AsyncEngine) -> None:
    me, key = await _person(engine)

    found = await _find(engine, key)

    assert (me.teaches, me.main_teacher) == (False, None)
    assert (found.teaches, found.main_teacher) == (False, None)


async def test_the_load_carries_the_main_teachers_own_stored_value(engine: AsyncEngine) -> None:
    anna, anna_key = await _person(engine, "Anna", "almaty")
    me, key = await _person(engine, "Ash")
    await _link(engine, me.id, anna.id)

    student = await _find(engine, key)
    teacher = await _find(engine, anna_key)

    assert student.main_teacher == TeacherMoon(anna.id, "Anna", "almaty")
    assert student.teaches is False
    assert teacher.teaches is True
    assert teacher.main_teacher is None


@pytest.mark.parametrize("stored", [None, FOLLOW_TEACHER, "atlantis"])
async def test_the_teachers_raw_value_comes_through_and_the_rule_makes_it_nothing(
    engine: AsyncEngine, stored: str | None
) -> None:
    """One hop is the domain's job: the load returns what is stored, the rule gives Mysuru."""
    anna, _ = await _person(engine, "Anna")
    await _raw_moon(engine, anna.id, stored)
    me, key = await _person(engine, "Ash")
    await _link(engine, me.id, anna.id)

    student = await _find(engine, key)

    assert student.main_teacher == TeacherMoon(anna.id, "Anna", stored)
    assert moon_follow_of(student, cities()).city is cities().default


async def test_every_method_returning_an_account_carries_the_same_inputs(
    engine: AsyncEngine,
) -> None:
    anna, _ = await _person(engine, "Anna", "almaty")
    me, key = await _person(engine, "Ash")
    await _link(engine, me.id, anna.id)
    student, _ = await _person(engine, "Student")
    await _link(engine, student.id, me.id)
    repo = SqlAccountRepository(engine)
    expected = (True, TeacherMoon(anna.id, "Anna", "almaty"))

    returned = [
        await _find(engine, key),
        await repo.update_profile(me.id, ProfileUpdate("Ash", "en"), NOW),
        await repo.update_settings(
            me.id, ProfileChange("Ash", False, "en", False, "Asia/Almaty", frozenset({"name"}))
        ),
        await repo.set_moon_location(me.id, "moscow"),
        await repo.set_timezone_if_unset(me.id, "Europe/Moscow"),
        await repo.set_day_off(me.id, DayOff(frozenset({6}), ON)),
    ]
    await _raw_moon(engine, me.id, None)
    kept = await repo.set_moon_location_if_unset(me.id, "almaty")
    assert kept is not None
    returned.append(kept)

    assert [(a.teaches, a.main_teacher) for a in returned] == [expected] * len(returned)


async def test_create_with_identity_carries_the_inputs_too(engine: AsyncEngine) -> None:
    created, _ = await _person(engine)

    assert (created.teaches, created.main_teacher) == (False, None)


async def test_the_main_teacher_is_the_chosen_one_else_the_oldest_link(
    engine: AsyncEngine,
) -> None:
    me, key = await _person(engine, "Ash")
    old, _ = await _person(engine, "Old", "almaty")
    new, _ = await _person(engine, "New", "moscow")
    await _link(engine, me.id, new.id, NOW - timedelta(days=1))
    await _link(engine, me.id, old.id, NOW - timedelta(days=5))
    links = SqlTeacherLinkRepository(engine)

    by_default = await _find(engine, key)
    assert by_default.main_teacher is not None
    assert by_default.main_teacher.id == old.id
    assert by_default.main_teacher.id == effective_primary((await links.overview(me.id)).teachers)

    await links.set_primary(me.id, new.id)
    chosen = await _find(engine, key)

    assert chosen.main_teacher == TeacherMoon(new.id, "New", "moscow")
    assert chosen.main_teacher is not None
    assert chosen.main_teacher.id == effective_primary((await links.overview(me.id)).teachers)


async def test_the_order_matches_effective_primary_over_a_mix(engine: AsyncEngine) -> None:
    me, key = await _person(engine, "Ash")
    teachers = [(await _person(engine, f"T{i}", "almaty"))[0] for i in range(5)]
    same = NOW - timedelta(days=3)  # a tie on created_at: teacher_id decides, as in the domain
    for t in teachers:
        await _link(engine, me.id, t.id, same)
    links = SqlTeacherLinkRepository(engine)

    found = await _find(engine, key)

    assert found.main_teacher is not None
    assert found.main_teacher.id == effective_primary((await links.overview(me.id)).teachers)
    assert found.main_teacher.id == min(t.id for t in teachers)


async def test_deleting_the_main_teacher_hands_over_to_the_next_oldest(
    engine: AsyncEngine,
) -> None:
    me, key = await _person(engine, "Ash")
    first, _ = await _person(engine, "First", "almaty")
    second, _ = await _person(engine, "Second", "moscow")
    await _link(engine, me.id, first.id, NOW - timedelta(days=5))
    await _link(engine, me.id, second.id, NOW - timedelta(days=1))

    assert await SqlAccountRepository(engine).delete(first.id)
    found = await _find(engine, key)

    assert found.main_teacher == TeacherMoon(second.id, "Second", "moscow")
    assert moon_follow_of(found, cities()).city.slug == "moscow"


async def test_losing_the_last_student_stops_teaching(engine: AsyncEngine) -> None:
    me, key = await _person(engine, "Ash")
    student, _ = await _person(engine, "Student")
    await _link(engine, student.id, me.id)
    assert (await _find(engine, key)).teaches

    await SqlTeacherLinkRepository(engine).unlink(student.id, me.id)

    assert not (await _find(engine, key)).teaches


async def test_the_account_load_stays_one_statement(engine: AsyncEngine) -> None:
    anna, _ = await _person(engine, "Anna", "almaty")
    me, key = await _person(engine, "Ash")
    await _link(engine, me.id, anna.id)
    repo = SqlAccountRepository(engine)

    with _statements(engine) as seen:
        await repo.find_by_identity(key)
        await repo.set_moon_location(me.id, FOLLOW_TEACHER)
        await repo.set_moon_location_if_unset(me.id, "almaty")

    assert len(seen) == 3


# Storing.


async def test_the_sentinel_is_stored_and_read_back(engine: AsyncEngine) -> None:
    me, key = await _person(engine)

    saved = await SqlAccountRepository(engine).set_moon_location(me.id, FOLLOW_TEACHER)

    assert saved.moon_location == FOLLOW_TEACHER
    assert (await _find(engine, key)).moon_location == FOLLOW_TEACHER


async def test_set_if_unset_writes_only_on_null(engine: AsyncEngine) -> None:
    repo = SqlAccountRepository(engine)
    me, key = await _person(engine)

    kept = await repo.set_moon_location_if_unset(me.id, "almaty")
    again = await repo.set_moon_location_if_unset(me.id, "moscow")

    assert kept is not None
    assert kept.moon_location == "almaty"
    assert again is None
    assert (await _find(engine, key)).moon_location == "almaty"


@pytest.mark.parametrize("chosen", ["moscow", FOLLOW_TEACHER, "mysuru"])
async def test_set_if_unset_leaves_any_choice(engine: AsyncEngine, chosen: str) -> None:
    repo = SqlAccountRepository(engine)
    me, key = await _person(engine, moon=chosen)

    assert await repo.set_moon_location_if_unset(me.id, "almaty") is None
    assert (await _find(engine, key)).moon_location == chosen


async def test_two_keep_taps_at_once_write_once(engine: AsyncEngine) -> None:
    repo = SqlAccountRepository(engine)
    me, key = await _person(engine)

    results = await asyncio.gather(
        repo.set_moon_location_if_unset(me.id, "almaty"),
        repo.set_moon_location_if_unset(me.id, "moscow"),
    )

    assert sorted(r is None for r in results) == [False, True]
    [winner] = [r for r in results if r is not None]
    assert (await _find(engine, key)).moon_location == winner.moon_location


# The tick.


async def _candidate_inputs(engine: AsyncEngine) -> dict[UUID, Any]:
    repo = SqlNotificationRepository(engine)
    return {
        c.account_id: c
        for c in await repo.candidates(NOW - timedelta(days=12), NOW.date(), DEFAULTS)
    }


async def test_the_tick_candidates_resolve_as_the_account_load(engine: AsyncEngine) -> None:
    """A seeded mix: never chose, chose, follow, a teacher who never chose, one hop, a chosen
    main teacher over an older link."""
    almaty, _ = await _person(engine, "Almaty", "almaty")
    moscow, _ = await _person(engine, "Moscow", "moscow")
    unset, _ = await _person(engine, "Unset")
    follows, _ = await _person(engine, "Follows", FOLLOW_TEACHER)
    people = [
        await _person(engine, "A"),
        await _person(engine, "B", "moscow"),
        await _person(engine, "C", FOLLOW_TEACHER),
        await _person(engine, "D"),
        await _person(engine, "E", FOLLOW_TEACHER),
        await _person(engine, "F"),
    ]
    (a, _), (b, _), (c, _), (d, _), (e, _), (f, _) = people
    await _link(engine, a.id, almaty.id)
    await _link(engine, b.id, almaty.id)
    await _link(engine, c.id, unset.id)
    await _link(engine, d.id, follows.id)
    await _link(engine, unset.id, almaty.id)  # `unset` teaches c and never chose: own
    await _link(engine, e.id, almaty.id, NOW - timedelta(days=9))
    await _link(engine, e.id, moscow.id, NOW - timedelta(days=1))
    await SqlTeacherLinkRepository(engine).set_primary(e.id, moscow.id)
    await _link(engine, f.id, a.id)  # f follows a, who follows almaty: one hop gives Mysuru
    candidates = await _candidate_inputs(engine)
    expected = {
        a.id: "mysuru",  # a teaches f and never chose: own (Q76)
        b.id: "moscow",
        c.id: "mysuru",
        d.id: "mysuru",
        e.id: "moscow",
        f.id: "mysuru",
        unset.id: "mysuru",
    }

    for account, key in [*people, (unset, None)]:
        cand = candidates[account.id]
        rule = moon_follow(
            cand.location,
            cand.teaches,
            TeacherMoon(UUID(int=0), None, cand.teacher_location)
            if cand.teacher_location
            else None,
            None,
            cities(),
        )
        assert rule.city.slug == expected[account.id], account.display_name
        if key is not None:
            loaded = moon_follow_of(await _find(engine, key), cities())
            assert loaded.city.slug == rule.city.slug, account.display_name


async def test_the_tick_candidates_keep_their_statements(engine: AsyncEngine) -> None:
    """Spec §6: unchanged (accounts, deliveries, logged and paused days)."""
    anna, _ = await _person(engine, "Anna", "almaty")
    for _ in range(3):
        student, _ = await _person(engine)
        await _link(engine, student.id, anna.id)
    repo = SqlNotificationRepository(engine)

    with _statements(engine) as seen:
        await repo.candidates(NOW - timedelta(days=12), NOW.date(), DEFAULTS)

    assert len(seen) == 3


# The plan (spec §5): 500 students and 20 teachers, the lookups use `teacher_link` indexes.


async def test_the_lookups_use_the_teacher_link_indexes(engine: AsyncEngine) -> None:
    async with engine.connect() as conn:
        await conn.execute(
            text(
                "INSERT INTO tristhana.account (display_name, locale)"
                " SELECT 'p' || g, 'en' FROM generate_series(1, 520) g"
            )
        )
        await conn.execute(
            text(
                "WITH people AS (SELECT id, row_number() OVER (ORDER BY id) n"
                " FROM tristhana.account)"
                " INSERT INTO tristhana.teacher_link (student_id, teacher_id, linked_on)"
                " SELECT s.id, t.id, DATE '2026-11-01' FROM people s JOIN people t"
                " ON t.n <= 20 AND s.n > 20"
            )
        )
        await conn.execute(text("ANALYZE tristhana.teacher_link"))
        await conn.execute(text("ANALYZE tristhana.account"))
        await conn.commit()
        teacher = (
            await conn.execute(text("SELECT teacher_id FROM tristhana.teacher_link LIMIT 1"))
        ).scalar_one()
        student = (
            await conn.execute(text("SELECT student_id FROM tristhana.teacher_link LIMIT 1"))
        ).scalar_one()
    async with engine.connect() as conn:
        await conn.execute(
            text(
                "INSERT INTO tristhana.identity (provider, provider_user_id, account_id)"
                " VALUES ('telegram', 'plan-t', :t), ('telegram', 'plan-s', :s)"
            ),
            {"t": teacher, "s": student},
        )
        await conn.commit()
    loads: list[tuple[str, Any]] = []

    def record(_conn: object, _cursor: object, statement: str, params: Any, *_: object) -> None:
        loads.append((statement, params))

    repo = SqlAccountRepository(engine)
    for who in ("plan-t", "plan-s"):
        event.listen(engine.sync_engine, "before_cursor_execute", record)
        try:
            await repo.find_by_identity(_key(who))
        finally:
            event.remove(engine.sync_engine, "before_cursor_execute", record)
    assert all("teacher_link" in statement for statement, _ in loads)
    for statement, params in loads:
        async with engine.connect() as conn:
            await conn.exec_driver_sql("SET enable_seqscan = off")  # ask what the plan can use
            plan = "\n".join(
                str(row[0]) for row in await conn.exec_driver_sql("EXPLAIN " + statement, params)
            )
        assert "Seq Scan on teacher_link" not in plan, plan
        assert any(
            name in plan
            for name in (
                "teacher_link_pkey",
                "teacher_link_teacher_id_student_id_idx",
                "teacher_link_one_primary",
            )
        ), plan
