"""Teacher marks on real Postgres (PR-08 Phase 3, spec §4, §9, ADR-0037).

`for_teacher` in one statement (None when unlinked or reversed); the guarded single-statement
apply (the link `EXISTS` and the position compare-and-set beside `last_event_id`); races (two
teachers, a teacher and the student, a mark and an unlink) leaving one event; the wider undo (a
teacher's mark after later items: back to `from`, items and `last_event_id` kept, the hint
cleared; refused once the position moved on; the student's own marks latest-only); `by` /
`by_name` (the name only while linked, NULL after a deletion and still undoable); the export."""

import asyncio
import base64
import itertools
from collections.abc import Generator
from contextlib import contextmanager
from datetime import date
from uuid import UUID

import pytest
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncEngine

from tristhana.domain.accounts import IdentityKey, IdentityProvider, NewAccount
from tristhana.domain.export import MarkedBy
from tristhana.domain.notifications import DEFAULTS
from tristhana.domain.progression import (
    STANDING_ONLY,
    Change,
    EventKind,
    Marker,
    Position,
    Progression,
    ProgressionEvent,
)
from tristhana.infrastructure.crypto import FieldCipher
from tristhana.infrastructure.db.accounts import SqlAccountRepository
from tristhana.infrastructure.db.export import SqlExportRepository
from tristhana.infrastructure.db.progression import SqlProgressionRepository

pytestmark = pytest.mark.db

KEYS = "1:" + base64.b64encode(b"\x07" * 32).decode()
ON = date(2026, 11, 8)
LINKED = date(2026, 6, 1)
KAPOTASANA_B = Position("intermediate", "kapotasana-b")
SUPTA_VAJRASANA = Position("intermediate", "supta-vajrasana")
BAKASANA_B = Position("intermediate", "bakasana-b")
BHARADVAJASANA = Position("intermediate", "bharadvajasana")
ITEMS = frozenset({"drop-backs"})
_users = itertools.count(95_000)


async def _account(
    engine: AsyncEngine, name: str | None = "A", locale: str = "en"
) -> tuple[UUID, str]:
    telegram_id = str(next(_users))
    account = await SqlAccountRepository(engine).create_with_identity(
        IdentityKey(IdentityProvider.TELEGRAM, telegram_id),
        NewAccount(display_name=name, locale=locale),  # type: ignore[arg-type]
    )
    return account.id, telegram_id


async def _link(engine: AsyncEngine, student: UUID, teacher: UUID) -> None:
    async with engine.connect() as conn:
        await conn.execute(
            text(
                "INSERT INTO tristhana.teacher_link (student_id, teacher_id, linked_on)"
                " VALUES (:s, :t, :on)"
            ),
            {"s": student, "t": teacher, "on": LINKED},
        )


async def _unlink(engine: AsyncEngine, student: UUID, teacher: UUID) -> None:
    async with engine.connect() as conn:
        await conn.execute(
            text("DELETE FROM tristhana.teacher_link WHERE student_id = :s AND teacher_id = :t"),
            {"s": student, "t": teacher},
        )


async def _delete(engine: AsyncEngine, account: UUID) -> None:
    async with engine.connect() as conn:
        await conn.execute(text("DELETE FROM tristhana.account WHERE id = :a"), {"a": account})


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


def _start(target: Position) -> Change:
    return Change(EventKind.START, ON, Progression(target), after=target)


def _given(before: Position, after: Position, items: frozenset[str] = ITEMS) -> Change:
    return Change(EventKind.GIVEN, ON, Progression(after, items), before, after)


def _changed(before: Position, after: Position, items: frozenset[str] = ITEMS) -> Change:
    return Change(EventKind.CHANGED, ON, Progression(after, items), before, after)


def _item(at: Position, item: str, items: frozenset[str]) -> Change:
    return Change(EventKind.ITEM_GIVEN, ON, Progression(at, items), item=item)


class Setup:
    """A student at Kapotasana B with drop-backs, and a linked teacher."""

    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine
        self.repo = SqlProgressionRepository(engine)

    async def build(self, teacher_name: str | None = "Лена") -> "Setup":
        self.student, self.student_tg = await _account(self.engine, "Anna", "ru")
        self.teacher, _ = await _account(self.engine, teacher_name)
        await _link(self.engine, self.student, self.teacher)
        me = self.student
        start = await self.repo.apply(me, _start(KAPOTASANA_B), None, me, before=None)
        assert start is not None
        item = await self.repo.apply(
            me, _item(KAPOTASANA_B, "drop-backs", ITEMS), start.id, me, before=KAPOTASANA_B
        )
        assert item is not None
        self.last = item.id
        return self

    async def mark(
        self,
        target: Position = SUPTA_VAJRASANA,
        seen: Position = KAPOTASANA_B,
        teacher: UUID | None = None,
        expected: int | None = None,
    ) -> ProgressionEvent | None:
        teacher = teacher or self.teacher
        return await self.repo.apply(
            self.student,
            _given(seen, target),
            self.last if expected is None else expected,
            teacher,
            before=seen,
            link_teacher=teacher,
        )

    async def own(self, change: Change, expected: int, before: Position) -> ProgressionEvent:
        found = await self.repo.apply(self.student, change, expected, self.student, before=before)
        assert found is not None
        return found

    async def events(self) -> int:
        async with self.engine.connect() as conn:
            found = await conn.execute(
                text("SELECT count(*) FROM tristhana.progression_event WHERE account_id = :a"),
                {"a": self.student},
            )
            return found.scalar_one()


@pytest.fixture
async def setup(engine: AsyncEngine) -> Setup:
    return await Setup(engine).build()


# for_teacher


async def test_for_teacher_reads_the_link_the_student_and_the_view_in_one_statement(
    engine: AsyncEngine, setup: Setup
) -> None:
    with _statements(engine) as seen:
        found = await setup.repo.for_teacher(setup.teacher, setup.student)

    assert len(seen) == 1
    assert found is not None
    assert found.link.teacher_id == setup.teacher
    assert found.link.student_id == setup.student
    assert found.link.locale == "ru"
    assert found.link.timezone is None
    assert found.link.telegram_id == setup.student_tg
    assert found.view.progression == Progression(KAPOTASANA_B, ITEMS, setup.last)
    assert [e.kind for e in found.view.events] == [EventKind.ITEM_GIVEN, EventKind.START]


async def test_for_teacher_is_none_when_unlinked_reversed_or_unknown(
    engine: AsyncEngine, setup: Setup
) -> None:
    stranger, _ = await _account(engine)

    assert await setup.repo.for_teacher(stranger, setup.student) is None
    assert await setup.repo.for_teacher(setup.student, setup.teacher) is None  # reversed
    assert await setup.repo.for_teacher(setup.teacher, UUID(int=0)) is None


async def test_for_teacher_on_an_unset_student_has_no_progression(engine: AsyncEngine) -> None:
    student, _ = await _account(engine)
    teacher, _ = await _account(engine)
    await _link(engine, student, teacher)

    found = await SqlProgressionRepository(engine).for_teacher(teacher, student)

    assert found is not None
    assert found.view.progression is None


# The guarded apply: one statement, the link, the position


async def test_a_mark_is_one_statement_and_reads_back_as_the_teachers(
    engine: AsyncEngine, setup: Setup
) -> None:
    with _statements(engine) as seen:
        mark = await setup.mark(BHARADVAJASANA)

    assert len(seen) == 1
    assert mark is not None
    view = await setup.repo.get(setup.student)
    assert view.progression == Progression(BHARADVAJASANA, ITEMS, mark.id)
    newest = view.events[0]
    assert (newest.kind, newest.before, newest.after) == (
        EventKind.GIVEN,
        KAPOTASANA_B,
        BHARADVAJASANA,
    )
    assert (newest.by, newest.by_name, newest.marked_by_self) == (Marker.TEACHER, "Лена", False)
    assert newest.occurred_on == ON


async def test_without_the_link_nothing_is_written(engine: AsyncEngine, setup: Setup) -> None:
    await _unlink(engine, setup.student, setup.teacher)

    assert await setup.mark() is None
    assert await setup.events() == 2


async def test_the_link_guard_is_the_markers_own_link(engine: AsyncEngine, setup: Setup) -> None:
    """Linked to someone else is no link: the guard names this teacher."""
    other, _ = await _account(engine)
    await _link(engine, other, setup.teacher)  # the teacher has another student

    stranger, _ = await _account(engine)
    assert await setup.mark(teacher=stranger) is None
    assert await setup.events() == 2


async def test_a_position_other_than_before_writes_nothing_even_with_the_same_id(
    engine: AsyncEngine, setup: Setup
) -> None:
    """The position compare-and-set: after a non-latest undo `last_event_id` stays, so the id
    alone can't catch a stale client."""
    assert await setup.mark(BAKASANA_B, seen=SUPTA_VAJRASANA) is None
    assert await setup.events() == 2
    view = await setup.repo.get(setup.student)
    assert view.progression is not None
    assert view.progression.position == KAPOTASANA_B


async def test_a_stale_event_id_writes_nothing(engine: AsyncEngine, setup: Setup) -> None:
    assert await setup.mark(expected=setup.last - 1) is None
    assert await setup.events() == 2


async def test_the_students_own_writes_pass_their_position_too(
    engine: AsyncEngine, setup: Setup
) -> None:
    stale = await setup.repo.apply(
        setup.student,
        _given(SUPTA_VAJRASANA, BAKASANA_B),
        setup.last,
        setup.student,
        before=SUPTA_VAJRASANA,
    )
    assert stale is None
    fresh = await setup.own(_given(KAPOTASANA_B, SUPTA_VAJRASANA), setup.last, KAPOTASANA_B)
    assert fresh.by is Marker.SELF


async def test_standing_only_compares_as_a_null_pair(engine: AsyncEngine) -> None:
    student, _ = await _account(engine)
    teacher, _ = await _account(engine)
    await _link(engine, student, teacher)
    repo = SqlProgressionRepository(engine)
    start = await repo.apply(student, _start(STANDING_ONLY), None, student, before=None)
    assert start is not None
    first = Position("primary", "utthita-hasta-padangusthasana")

    mark = await repo.apply(
        student,
        _given(STANDING_ONLY, first, frozenset()),
        start.id,
        teacher,
        before=STANDING_ONLY,
        link_teacher=teacher,
    )

    assert mark is not None


# Races: exactly one wins, one event is written


async def test_two_teachers_marking_at_once_leave_one_event(
    engine: AsyncEngine, setup: Setup
) -> None:
    second, _ = await _account(engine, "Dmitry")
    await _link(engine, setup.student, second)

    results = await asyncio.gather(
        setup.mark(SUPTA_VAJRASANA, teacher=setup.teacher),
        setup.mark(BAKASANA_B, teacher=second),
    )

    assert sum(r is not None for r in results) == 1
    assert await setup.events() == 3
    winner = next(r for r in results if r is not None)
    view = await setup.repo.get(setup.student)
    assert view.progression is not None
    assert view.progression.last_event_id == winner.id
    assert view.progression.position == winner.after


async def test_a_teacher_and_the_student_at_once_leave_one_event(
    engine: AsyncEngine, setup: Setup
) -> None:
    own = setup.repo.apply(
        setup.student,
        _given(KAPOTASANA_B, SUPTA_VAJRASANA),
        setup.last,
        setup.student,
        before=KAPOTASANA_B,
    )

    results = await asyncio.gather(setup.mark(BHARADVAJASANA), own)

    assert sum(r is not None for r in results) == 1
    assert await setup.events() == 3


async def test_a_mark_and_an_unlink_at_once_leave_a_linked_mark_or_nothing(
    engine: AsyncEngine,
) -> None:
    for _ in range(5):
        setup = await Setup(engine).build()
        mark, _ = await asyncio.gather(setup.mark(), _unlink(engine, setup.student, setup.teacher))
        assert await setup.events() == (3 if mark is not None else 2)
        view = await setup.repo.get(setup.student)
        assert view.progression is not None
        assert view.progression.position == (SUPTA_VAJRASANA if mark else KAPOTASANA_B)


# Undo: a teacher's mark until the position moves on


async def test_a_teachers_mark_after_items_goes_back_to_from_keeping_the_items(
    engine: AsyncEngine, setup: Setup
) -> None:
    mark = await setup.mark(BHARADVAJASANA)  # three stops at once
    assert mark is not None
    more = ITEMS | {"standing-up"}
    item = await setup.own(_item(BHARADVAJASANA, "standing-up", more), mark.id, BHARADVAJASANA)
    await setup.repo.dismiss_hint(setup.student, Position("intermediate", "ardha-matsyendrasana"))

    with _statements(engine) as seen:
        assert await setup.repo.undo(setup.student, mark.id)

    assert len(seen) == 1
    view = await setup.repo.get(setup.student)
    assert view.progression == Progression(KAPOTASANA_B, more, item.id)  # id kept, hint cleared
    assert mark.id not in {e.id for e in view.events}
    assert BHARADVAJASANA not in view.earlier.targets  # a real give later celebrates


async def test_after_a_retract_a_stale_item_write_is_refused_and_a_fresh_give_works(
    engine: AsyncEngine, setup: Setup
) -> None:
    mark = await setup.mark()
    assert mark is not None
    more = ITEMS | {"standing-up"}
    item = await setup.own(_item(SUPTA_VAJRASANA, "standing-up", more), mark.id, SUPTA_VAJRASANA)
    assert await setup.repo.undo(setup.student, mark.id)

    stale = await setup.repo.apply(
        setup.student,
        _item(SUPTA_VAJRASANA, "viparita-chakrasana", more | {"viparita-chakrasana"}),
        item.id,
        setup.student,
        before=SUPTA_VAJRASANA,
    )
    assert stale is None
    again = await setup.own(_given(KAPOTASANA_B, SUPTA_VAJRASANA, more), item.id, KAPOTASANA_B)
    assert again.after == SUPTA_VAJRASANA


@pytest.mark.parametrize("later", ["changed", "self-given", "teacher-given"])
async def test_once_the_position_moved_on_the_mark_cant_be_undone(
    engine: AsyncEngine, setup: Setup, later: str
) -> None:
    mark = await setup.mark()
    assert mark is not None
    match later:
        case "changed":
            await setup.own(_changed(SUPTA_VAJRASANA, KAPOTASANA_B), mark.id, SUPTA_VAJRASANA)
        case "self-given":
            await setup.own(_given(SUPTA_VAJRASANA, BAKASANA_B), mark.id, SUPTA_VAJRASANA)
        case _:
            second = await setup.mark(BAKASANA_B, seen=SUPTA_VAJRASANA, expected=mark.id)
            assert second is not None

    assert not await setup.repo.undo(setup.student, mark.id)
    assert await setup.events() == 4


async def test_the_students_own_give_stays_latest_only(engine: AsyncEngine, setup: Setup) -> None:
    mine = await setup.own(_given(KAPOTASANA_B, SUPTA_VAJRASANA), setup.last, KAPOTASANA_B)
    more = ITEMS | {"standing-up"}
    item = await setup.own(_item(SUPTA_VAJRASANA, "standing-up", more), mine.id, SUPTA_VAJRASANA)

    assert not await setup.repo.undo(setup.student, mine.id)
    assert await setup.repo.undo(setup.student, item.id)
    assert await setup.repo.undo(setup.student, mine.id)  # latest again


async def test_a_latest_teacher_mark_undoes_as_before(engine: AsyncEngine, setup: Setup) -> None:
    mark = await setup.mark()
    assert mark is not None

    assert await setup.repo.undo(setup.student, mark.id)

    view = await setup.repo.get(setup.student)
    assert view.progression == Progression(KAPOTASANA_B, ITEMS, setup.last)


async def test_no_one_undoes_someone_elses_event(engine: AsyncEngine, setup: Setup) -> None:
    mark = await setup.mark()
    assert mark is not None

    assert not await setup.repo.undo(setup.teacher, mark.id)  # the teacher can't (Q5)
    assert await setup.events() == 3


# by / by_name


async def test_the_name_shows_only_while_linked(engine: AsyncEngine, setup: Setup) -> None:
    mark = await setup.mark()
    assert mark is not None

    await _unlink(engine, setup.student, setup.teacher)

    newest = (await setup.repo.get(setup.student)).events[0]
    assert (newest.by, newest.by_name) == (Marker.TEACHER, None)


async def test_the_students_own_events_read_self(engine: AsyncEngine, setup: Setup) -> None:
    view = await setup.repo.get(setup.student)

    assert {(e.by, e.by_name) for e in view.events} == {(Marker.SELF, None)}


async def test_a_deleted_teachers_mark_stays_a_teachers_and_undoable(
    engine: AsyncEngine, setup: Setup
) -> None:
    mark = await setup.mark()
    assert mark is not None
    more = ITEMS | {"standing-up"}
    await setup.own(_item(SUPTA_VAJRASANA, "standing-up", more), mark.id, SUPTA_VAJRASANA)

    await _delete(engine, setup.teacher)

    given = next(e for e in (await setup.repo.get(setup.student)).events if e.id == mark.id)
    assert (given.by, given.by_name) == (Marker.TEACHER, None)
    assert await setup.repo.undo(setup.student, mark.id)
    view = await setup.repo.get(setup.student)
    assert view.progression is not None
    assert view.progression.position == KAPOTASANA_B


async def test_a_nameless_teacher_reads_with_no_name(engine: AsyncEngine) -> None:
    setup = await Setup(engine).build(teacher_name=None)
    assert await setup.mark() is not None

    newest = (await setup.repo.get(setup.student)).events[0]
    assert (newest.by, newest.by_name) == (Marker.TEACHER, None)


# Export (ST-09): no change, and nothing of the teacher


async def test_the_export_says_teacher_and_names_no_one(engine: AsyncEngine, setup: Setup) -> None:
    mark = await setup.mark()
    assert mark is not None
    export = SqlExportRepository(engine, FieldCipher(KEYS))

    owned = await export.snapshot(setup.student, DEFAULTS, ON)
    theirs = await export.snapshot(setup.teacher, DEFAULTS, ON)

    assert owned is not None
    assert theirs is not None
    given = next(e for e in owned.events if e.event.id == mark.id)
    assert given.marked_by is MarkedBy.TEACHER
    assert str(setup.teacher) not in repr(owned.events)
    assert "Лена" not in repr(owned.events)
    assert not theirs.events  # the teacher's own export holds none of their marks

    await _delete(engine, setup.teacher)
    owned = await export.snapshot(setup.student, DEFAULTS, ON)
    assert owned is not None
    assert next(e for e in owned.events if e.event.id == mark.id).marked_by is MarkedBy.UNKNOWN
