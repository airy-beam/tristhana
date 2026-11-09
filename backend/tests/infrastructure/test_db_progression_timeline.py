"""ST-04 timeline and the Q159 fix on real Postgres (spec §4, §8).

`timeline` in one statement, oldest first, with `by` / `by_name` (the name only while linked; a
NULL `marked_by` after the teacher's deletion reads as a teacher), only the account's own
events, and `truncated` once there are more than `TIMELINE_LIMIT` (a small limit, and the real
1,000 + 1 inserted in bulk). `get` and `for_teacher` return `position_event` however old (past
the newest 20), still in one statement each."""

from collections.abc import Generator
from contextlib import contextmanager
from uuid import UUID

import pytest
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.infrastructure.test_db_teacher_marks import (
    BHARADVAJASANA,
    ITEMS,
    KAPOTASANA_B,
    ON,
    Setup,
)
from tristhana.domain.progression import (
    HISTORY_LIMIT,
    TIMELINE_LIMIT,
    Change,
    Earlier,
    EventKind,
    Marker,
    Progression,
    ProgressionEvent,
    teacher_mark,
    undoable,
)
from tristhana.infrastructure.db.progression import SqlProgressionRepository

pytestmark = pytest.mark.db


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


async def _sql(engine: AsyncEngine, sql: str, **params: object) -> None:
    async with engine.connect() as conn:
        await conn.execute(text(sql), params)


async def _toggles(setup: Setup, after: int, count: int) -> int:
    """`count` of the student's own item events (standing-up on, off, …); the last id."""
    last, items = after, ITEMS
    for n in range(count):
        given = n % 2 == 0
        items = items | {"standing-up"} if given else items - {"standing-up"}
        kind = EventKind.ITEM_GIVEN if given else EventKind.ITEM_REMOVED
        change = Change(kind, ON, Progression(BHARADVAJASANA, items), item="standing-up")
        last = (await setup.own(change, last, BHARADVAJASANA)).id
    return last


async def _bulk(engine: AsyncEngine, account: UUID, count: int) -> None:
    """`count` of the account's own item events in one INSERT."""
    await _sql(
        engine,
        "INSERT INTO tristhana.progression_event (account_id, kind, item, occurred_on, marked_by)"
        " SELECT :a, 'item_given', 'drop-backs', :on, :a FROM generate_series(1, :n)",
        a=account,
        on=ON,
        n=count,
    )


@pytest.fixture
async def setup(engine: AsyncEngine) -> Setup:
    return await Setup(engine).build()


# timeline


async def test_unset_is_empty_in_one_statement(engine: AsyncEngine, setup: Setup) -> None:
    with _statements(engine) as seen:
        found = await setup.repo.timeline(setup.teacher)  # the teacher has no record

    assert len(seen) == 1
    assert found == ((), False, Earlier())


async def test_the_timeline_is_one_statement_oldest_first_with_who_marked_it(
    engine: AsyncEngine, setup: Setup
) -> None:
    mark = await setup.mark(BHARADVAJASANA)
    assert mark is not None

    with _statements(engine) as seen:
        events, truncated, _ = await setup.repo.timeline(setup.student)

    assert len(seen) == 1
    assert truncated is False
    assert [e.kind for e in events] == [EventKind.START, EventKind.ITEM_GIVEN, EventKind.GIVEN]
    assert [e.id for e in events] == sorted(e.id for e in events)
    start, item, given = events
    assert (start.after, start.by, start.by_name, start.occurred_on) == (
        KAPOTASANA_B,
        Marker.SELF,
        None,
        ON,
    )
    assert (item.item, item.by) == ("drop-backs", Marker.SELF)
    assert given == ProgressionEvent(
        mark.id, EventKind.GIVEN, ON, KAPOTASANA_B, BHARADVAJASANA, None, Marker.TEACHER, "Лена"
    )


async def test_the_timeline_has_only_the_accounts_own_events(
    engine: AsyncEngine, setup: Setup
) -> None:
    other = await Setup(engine).build()

    events, _, _ = await setup.repo.timeline(setup.student)

    assert len(events) == 2
    assert all(e.by is Marker.SELF for e in events)
    assert len((await other.repo.timeline(other.student))[0]) == 2


async def test_after_an_unlink_the_name_is_gone(engine: AsyncEngine, setup: Setup) -> None:
    assert await setup.mark() is not None
    await _sql(
        engine,
        "DELETE FROM tristhana.teacher_link WHERE student_id = :s AND teacher_id = :t",
        s=setup.student,
        t=setup.teacher,
    )

    newest = (await setup.repo.timeline(setup.student))[0][-1]

    assert (newest.by, newest.by_name) == (Marker.TEACHER, None)


async def test_a_deleted_teachers_null_marked_by_reads_as_a_teacher(
    engine: AsyncEngine, setup: Setup
) -> None:
    mark = await setup.mark()
    assert mark is not None

    await _sql(engine, "DELETE FROM tristhana.account WHERE id = :a", a=setup.teacher)

    async with engine.connect() as conn:
        marked_by = await conn.execute(
            text("SELECT marked_by FROM tristhana.progression_event WHERE id = :i"),
            {"i": mark.id},
        )
        assert marked_by.scalar_one() is None
    events, _, _ = await setup.repo.timeline(setup.student)
    assert (events[-1].id, events[-1].by, events[-1].by_name) == (mark.id, Marker.TEACHER, None)
    assert {(e.by, e.by_name) for e in events[:-1]} == {(Marker.SELF, None)}


async def test_truncated_past_a_small_limit_keeps_the_newest_oldest_first(
    engine: AsyncEngine, setup: Setup, monkeypatch: pytest.MonkeyPatch
) -> None:
    mark = await setup.mark(BHARADVAJASANA)
    assert mark is not None
    monkeypatch.setattr("tristhana.infrastructure.db.progression.TIMELINE_LIMIT", 3)

    exact, cut, _ = await setup.repo.timeline(setup.student)  # 3 events: not cut
    last = await _toggles(setup, mark.id, 2)
    with _statements(engine) as seen:
        kept, truncated, earlier = await setup.repo.timeline(setup.student)

    assert (len(exact), cut) == (3, False)
    # What the left-out events reached comes back too (same statement), never the kept mark's.
    left_out = [e for e in exact if e.id < kept[0].id]
    assert earlier.targets == {e.after for e in left_out if e.after is not None}
    assert earlier.items == {e.item for e in left_out if e.kind is EventKind.ITEM_GIVEN}
    assert BHARADVAJASANA not in earlier.targets
    assert len(seen) == 1
    assert truncated is True
    assert [e.id for e in kept] == sorted(e.id for e in kept)
    assert (kept[0].id, kept[-1].id) == (mark.id, last)
    assert [e.kind for e in kept] == [EventKind.GIVEN, EventKind.ITEM_GIVEN, EventKind.ITEM_REMOVED]


async def test_truncated_at_the_real_limit_plus_one(engine: AsyncEngine, setup: Setup) -> None:
    await _bulk(engine, setup.student, TIMELINE_LIMIT - 2)  # + start and item = the limit

    full, cut, _ = await setup.repo.timeline(setup.student)
    await _bulk(engine, setup.student, 1)
    kept, truncated, _ = await setup.repo.timeline(setup.student)

    assert (len(full), cut) == (TIMELINE_LIMIT, False)
    assert full[0].kind is EventKind.START
    assert (len(kept), truncated) == (TIMELINE_LIMIT, True)
    assert [e.id for e in kept] == [e.id for e in full[1:]] + [kept[-1].id]
    assert kept[-1].id > full[-1].id


# Q159: position_event however old


async def test_unset_and_start_only_position_events(engine: AsyncEngine, setup: Setup) -> None:
    assert (await setup.repo.get(setup.teacher)).position_event is None

    found = (await setup.repo.get(setup.student)).position_event

    assert found is not None
    assert (found.kind, found.after) == (EventKind.START, KAPOTASANA_B)


async def test_get_returns_a_mark_past_the_newest_20_in_one_statement(
    engine: AsyncEngine, setup: Setup
) -> None:
    mark = await setup.mark(BHARADVAJASANA)
    assert mark is not None
    await _toggles(setup, mark.id, HISTORY_LIMIT + 5)

    with _statements(engine) as seen:
        view = await setup.repo.get(setup.student)

    assert len(seen) == 1
    assert len(view.events) == HISTORY_LIMIT
    assert mark.id not in {e.id for e in view.events}
    assert view.position_event == ProgressionEvent(
        mark.id, EventKind.GIVEN, ON, KAPOTASANA_B, BHARADVAJASANA, None, Marker.TEACHER, "Лена"
    )
    assert teacher_mark(view.events, view.position_event) == view.position_event
    assert mark.id in undoable(view.events, view.position_event)


async def test_for_teacher_returns_the_position_event_in_one_statement(
    engine: AsyncEngine, setup: Setup
) -> None:
    mark = await setup.mark(BHARADVAJASANA)
    assert mark is not None
    await _toggles(setup, mark.id, HISTORY_LIMIT + 5)

    with _statements(engine) as seen:
        found = await setup.repo.for_teacher(setup.teacher, setup.student)

    assert len(seen) == 1
    assert found is not None
    assert found.view.position_event is not None
    assert found.view.position_event.id == mark.id
    assert found.view.position_event.by_name == "Лена"


async def test_the_position_event_is_the_newest_positional_one(
    engine: AsyncEngine, setup: Setup
) -> None:
    """A later own CHANGED replaces the mark; its own items never do."""
    mark = await setup.mark(BHARADVAJASANA)
    assert mark is not None
    last = await _toggles(setup, mark.id, 3)
    change = Change(
        EventKind.CHANGED, ON, Progression(KAPOTASANA_B, ITEMS), BHARADVAJASANA, KAPOTASANA_B
    )
    changed = await setup.own(change, last, BHARADVAJASANA)

    view = await SqlProgressionRepository(engine).get(setup.student)

    assert view.position_event is not None
    assert (view.position_event.id, view.position_event.by) == (changed.id, Marker.SELF)
    assert teacher_mark(view.events, view.position_event) is None
