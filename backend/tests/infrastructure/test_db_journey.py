"""UI-06 stage 2 on real Postgres (spec §6, §10): `AccountRepository.journey_facts` is one
statement over the account's own rows. A logged day of any status; the practice reminder
answered by "yes" and by "no", never by a settings row that leaves it unchosen; a set position
("standing only" included), gone again with its undo; the invite link's UTC date, renewed by a
rotation; and only the shalas the account owns, oldest first, each with its own class and
student counts. Nobody else's rows, and no shala the account merely works or studies at."""

from collections.abc import Generator
from contextlib import contextmanager
from datetime import date, datetime, time
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.infrastructure.test_db_shalas import (  # pyright: ignore[reportPrivateUsage]
    KEYS,
    TEACHER,
    _code,  # pyright: ignore[reportPrivateUsage]
    _link,  # pyright: ignore[reportPrivateUsage]
    _person,  # pyright: ignore[reportPrivateUsage]
    _shala,  # pyright: ignore[reportPrivateUsage]
    _staff,  # pyright: ignore[reportPrivateUsage]
    _student,  # pyright: ignore[reportPrivateUsage]
)
from tristhana.application.ports.classes import ClassCaps, ClassDraft
from tristhana.application.ports.notifications import ReminderPatch
from tristhana.domain.classes import MAX_CLASSES, MAX_FUTURE_CLOSURES, MAX_FUTURE_SWAPS, ClassType
from tristhana.domain.days import DayLog, DayStatus
from tristhana.domain.journey import JourneyFacts, OwnedShala
from tristhana.domain.notifications import DEFAULTS
from tristhana.domain.progression import Change, EventKind, Position, Progression
from tristhana.infrastructure.crypto import FieldCipher
from tristhana.infrastructure.db.accounts import SqlAccountRepository, journey_statement
from tristhana.infrastructure.db.classes import SqlScheduleRepository
from tristhana.infrastructure.db.days import SqlDayLogRepository
from tristhana.infrastructure.db.notifications import SqlNotificationRepository
from tristhana.infrastructure.db.progression import SqlProgressionRepository
from tristhana.infrastructure.db.shalas import SqlShalaRepository
from tristhana.infrastructure.db.teacher_links import SqlTeacherLinkRepository

pytestmark = pytest.mark.db

ON = date(2026, 11, 7)
ZONE = "Asia/Almaty"
CLASS_CAPS = ClassCaps(classes=MAX_CLASSES, closures=MAX_FUTURE_CLOSURES, swaps=MAX_FUTURE_SWAPS)
STANDING = Position(None, None)


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


async def _sql(engine: AsyncEngine, statement: str, **params: Any) -> None:
    async with engine.connect() as conn:
        await conn.execute(text(statement), params)
        await conn.commit()


async def _me(engine: AsyncEngine) -> UUID:
    account, _ = await _person(engine, "Anna")
    return account.id


async def _log(engine: AsyncEngine, who: UUID, status: DayStatus = DayStatus.PRACTICED) -> None:
    await SqlDayLogRepository(engine, FieldCipher(KEYS)).upsert(who, DayLog(ON, status), ZONE)


async def _class(engine: AsyncEngine, shala: UUID, owner: UUID) -> UUID:
    draft = ClassDraft(
        type=ClassType.MYSORE,
        title=None,
        online=False,
        city=None,
        teacher_id=None,
        start=time(6, 0),
        minutes=210,
        weekdays=frozenset({1, 2, 3, 4, 5}),
        every=1,
        starts_on=ON,
        ends_on=None,
    )
    created = await SqlScheduleRepository(engine).create(shala, owner, draft, CLASS_CAPS, ON)
    assert created.done
    assert created.value is not None
    return created.value.id


async def _start(engine: AsyncEngine, who: UUID, position: Position) -> int:
    change = Change(EventKind.START, ON, Progression(position), after=position)
    applied = await SqlProgressionRepository(engine).apply(who, change, None, who, before=None)
    assert applied is not None
    return applied.id


async def _facts(engine: AsyncEngine, who: UUID) -> JourneyFacts:
    return await SqlAccountRepository(engine).journey_facts(who)


# Nobody


async def test_a_new_account_has_no_facts_in_one_statement(engine: AsyncEngine) -> None:
    me = await _me(engine)

    with _statements(engine) as seen:
        facts = await _facts(engine, me)

    assert len(seen) == 1
    assert seen[0].lstrip().startswith("SELECT")
    assert facts == JourneyFacts()


async def test_an_unknown_account_has_no_facts(engine: AsyncEngine) -> None:
    assert await _facts(engine, uuid4()) == JourneyFacts()


def test_the_statement_reads_no_sealed_column_and_writes_nothing() -> None:
    sql = str(journey_statement(UUID(int=1)).compile(dialect=postgresql.dialect())).lower()

    assert "sealed" not in sql
    assert not any(word in sql for word in ("insert", "update ", "delete"))
    # The link's date is a UTC date whatever the connection's zone is.
    assert "timezone(" in sql


# Everything at once


async def test_every_fact_in_one_statement_and_only_the_callers_own(engine: AsyncEngine) -> None:
    me = await _me(engine)
    other = await _me(engine)
    student = await _me(engine)
    await _log(engine, me)
    await SqlNotificationRepository(engine).patch_practice(me, ReminderPatch(on=True), DEFAULTS)
    await _start(engine, me, Position("primary", "navasana"))
    await SqlTeacherLinkRepository(engine).invite(me, _code("T"))
    mine = await _shala(engine, me)
    await _class(engine, mine, me)
    await _class(engine, mine, me)
    await _student(engine, mine, me, student)
    # Somebody else's shala, where I am on the staff: its classes and students are theirs.
    theirs = await _shala(engine, other, name="Other shala")
    await _staff(engine, theirs, other, me, TEACHER)
    await _class(engine, theirs, other)
    await _student(engine, theirs, other, student)

    with _statements(engine) as seen:
        facts = await _facts(engine, me)

    assert len(seen) == 1
    assert facts.has_days is True
    assert facts.reminder_answered is True
    assert facts.position_set is True
    assert facts.invite_made_on is not None
    assert facts.owned == (OwnedShala(mine, classes=2, students=1),)
    # The others: the owner sees only their shala, the student owns nothing.
    assert await _facts(engine, other) == JourneyFacts(
        owned=(OwnedShala(theirs, classes=1, students=1),)
    )
    assert await _facts(engine, student) == JourneyFacts()


# A logged day


@pytest.mark.parametrize("status", [DayStatus.PRACTICED, DayStatus.REST, DayStatus.LADIES])
async def test_a_logged_day_of_any_status_counts(engine: AsyncEngine, status: DayStatus) -> None:
    me = await _me(engine)
    other = await _me(engine)
    await _log(engine, me, status)

    assert (await _facts(engine, me)).has_days is True
    assert (await _facts(engine, other)).has_days is False


async def test_a_cleared_day_no_longer_counts(engine: AsyncEngine) -> None:
    me = await _me(engine)
    await _log(engine, me)
    await SqlDayLogRepository(engine, FieldCipher(KEYS)).delete(me, ON)

    assert (await _facts(engine, me)).has_days is False


# The reminder


@pytest.mark.parametrize("answer", [True, False])
async def test_yes_and_no_both_answer_the_reminder(engine: AsyncEngine, answer: bool) -> None:
    me = await _me(engine)
    await SqlNotificationRepository(engine).patch_practice(me, ReminderPatch(on=answer), DEFAULTS)

    assert (await _facts(engine, me)).reminder_answered is True


async def test_a_settings_row_without_the_choice_is_not_an_answer(engine: AsyncEngine) -> None:
    """Other settings create the row too (moon reminders, quiet hours, the reminder's time)."""
    me = await _me(engine)
    repo = SqlNotificationRepository(engine)
    await repo.patch(me, {"daily_cap": 2}, DEFAULTS)
    await repo.patch_practice(me, ReminderPatch(at=time(6, 30)), DEFAULTS)

    assert (await _facts(engine, me)).reminder_answered is False


# The position


async def test_standing_only_is_a_set_position(engine: AsyncEngine) -> None:
    me = await _me(engine)
    other = await _me(engine)
    await _start(engine, me, STANDING)

    assert (await _facts(engine, me)).position_set is True
    assert (await _facts(engine, other)).position_set is False


async def test_an_undone_first_position_is_not_set(engine: AsyncEngine) -> None:
    me = await _me(engine)
    first = await _start(engine, me, Position("primary", "navasana"))
    assert await SqlProgressionRepository(engine).undo(me, first)

    assert (await _facts(engine, me)).position_set is False


# The invite link


async def test_the_invite_date_is_the_links_utc_date(engine: AsyncEngine) -> None:
    me = await _me(engine)
    other = await _me(engine)
    await SqlTeacherLinkRepository(engine).invite(me, _code("T"))
    # 2 Oct, 01:00 in Almaty (UTC+5) is still 1 Oct in UTC.
    await _sql(
        engine,
        "UPDATE tristhana.teacher_invite SET created_at = :at WHERE account_id = :a",
        at=datetime.fromisoformat("2026-10-02 01:00+05:00"),
        a=me,
    )

    assert (await _facts(engine, me)).invite_made_on == date(2026, 10, 1)
    assert (await _facts(engine, other)).invite_made_on is None


async def test_showing_the_link_again_keeps_its_date_and_a_rotation_renews_it(
    engine: AsyncEngine,
) -> None:
    me = await _me(engine)
    links = SqlTeacherLinkRepository(engine)
    await links.invite(me, _code("T"))
    await _sql(
        engine,
        "UPDATE tristhana.teacher_invite SET created_at = :at WHERE account_id = :a",
        at=datetime.fromisoformat("2026-01-05 12:00+00:00"),
        a=me,
    )

    await links.invite(me, _code("T"))
    assert (await _facts(engine, me)).invite_made_on == date(2026, 1, 5)

    await links.rotate(me, _code("T"))
    renewed = (await _facts(engine, me)).invite_made_on
    assert renewed is not None
    assert renewed > date(2026, 1, 5)


async def test_a_student_on_the_link_does_not_change_the_fact(engine: AsyncEngine) -> None:
    """Who teaches comes with the account (`Account.teaches`), not with this read."""
    me = await _me(engine)
    student = await _me(engine)
    await _link(engine, student, me)

    assert (await _facts(engine, me)).invite_made_on is not None
    assert (await _facts(engine, student)).invite_made_on is None


# Owned shalas


async def test_owned_shalas_come_oldest_first_each_with_its_own_counts(
    engine: AsyncEngine,
) -> None:
    me = await _me(engine)
    one, two = await _me(engine), await _me(engine)
    newer = await _shala(engine, me, name="Newer")
    older = await _shala(engine, me, name="Older")
    empty = await _shala(engine, me, name="Empty")
    await _sql(
        engine,
        "UPDATE tristhana.shala SET created_at = '2026-01-01 00:00+00' WHERE id = :s",
        s=older,
    )
    await _sql(
        engine,
        "UPDATE tristhana.shala SET created_at = '2026-06-01 00:00+00' WHERE id = :s",
        s=newer,
    )
    await _class(engine, older, me)
    await _student(engine, newer, me, one)
    await _student(engine, newer, me, two)

    facts = await _facts(engine, me)

    assert facts.owned == (
        OwnedShala(older, classes=1, students=0),
        OwnedShala(newer, classes=0, students=2),
        OwnedShala(empty, classes=0, students=0),
    )


async def test_staff_are_not_students_and_an_admin_is_not_the_owner(engine: AsyncEngine) -> None:
    owner = await _me(engine)
    admin = await _me(engine)
    shala = await _shala(engine, owner)
    await _staff(engine, shala, owner, admin, TEACHER)

    assert (await _facts(engine, owner)).owned == (OwnedShala(shala, classes=0, students=0),)
    assert (await _facts(engine, admin)).owned == ()


async def test_a_shala_i_study_at_is_not_mine(engine: AsyncEngine) -> None:
    owner = await _me(engine)
    me = await _me(engine)
    shala = await _shala(engine, owner)
    await _class(engine, shala, owner)
    await _student(engine, shala, owner, me)

    assert (await _facts(engine, me)).owned == ()


async def test_a_deleted_class_and_a_removed_student_no_longer_count(engine: AsyncEngine) -> None:
    me = await _me(engine)
    student = await _me(engine)
    shala = await _shala(engine, me)
    class_id = await _class(engine, shala, me)
    await _student(engine, shala, me, student)
    assert (await _facts(engine, me)).owned == (OwnedShala(shala, classes=1, students=1),)

    assert (await SqlScheduleRepository(engine).delete(shala, me, class_id)).done
    assert (await SqlShalaRepository(engine).remove_student(shala, me, student)).done

    assert (await _facts(engine, me)).owned == (OwnedShala(shala, classes=0, students=0),)


async def test_a_deleted_shala_is_gone(engine: AsyncEngine) -> None:
    me = await _me(engine)
    shala = await _shala(engine, me)
    assert (await SqlShalaRepository(engine).delete(shala, me)).done

    assert (await _facts(engine, me)).owned == ()
