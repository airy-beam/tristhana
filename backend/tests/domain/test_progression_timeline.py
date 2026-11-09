"""ST-04 timeline, pure (spec §3, §8): the history replayed through `celebrations`, newest first;
markers only the first time; quiet when given again; stale keys never celebrate. Plus the Q159
rule: `undoable` / `teacher_mark` from the event that set the position, however old."""

from datetime import date

import pytest

from tests.domain.test_teacher_marks import (
    KAPOTASANA_B,
    KURMASANA,
    NAVASANA,
    PASASANA,
    SELF,
    SETU,
    TEACHER,
    URDHVA_MUKHA,
    P,
    changed,
    ev,
    give,
    item,
    start,
    track,
)
from tristhana.domain.progression import (
    STANDING_ONLY,
    TIMELINE_LIMIT,
    Celebration,
    CelebrationKind,
    Earlier,
    EventKind,
    ProgressionEvent,
    TimelineEntry,
    teacher_mark,
    timeline,
    undoable,
)

K = CelebrationKind


def kinds(entry: TimelineEntry) -> list[CelebrationKind]:
    return [c.kind for c in entry.celebrations]


def test_the_limit_is_a_thousand() -> None:
    assert TIMELINE_LIMIT == 1000


def test_empty_history_is_empty() -> None:
    assert timeline(track(), []) == ()


def test_start_never_celebrates_and_gives_celebrate_newest_first() -> None:
    events = [
        start(1, NAVASANA),
        give(2, SELF, NAVASANA, P("primary", "bhujapidasana")),
        give(3, SELF, P("primary", "bhujapidasana"), KURMASANA),
    ]

    got = timeline(track(), events)

    assert [e.event.id for e in got] == [3, 2, 1]
    assert got[0].celebrations == (Celebration(K.NEW_ASANA, "primary", "kurmasana"),)
    assert got[1].celebrations == (Celebration(K.NEW_ASANA, "primary", "bhujapidasana"),)
    assert got[2].celebrations == ()


def test_a_jump_carries_the_first_new_stop() -> None:
    got = timeline(track(), [start(1, NAVASANA), give(2, TEACHER, NAVASANA, KURMASANA)])

    assert got[0].celebrations[0].first == P("primary", "bhujapidasana")


def test_from_setu_bandhasana_pasasana_begins_intermediate_only() -> None:
    got = timeline(track(), [start(1, SETU), give(2, SELF, SETU, PASASANA)])

    assert kinds(got[0]) == [K.NEW_ASANA, K.SERIES_BEGINS]


def test_a_jump_across_the_boundary_completes_primary_then_begins_intermediate() -> None:
    """Practice order inside one entry: Full Primary, then Intermediate begins."""
    events = [start(1, URDHVA_MUKHA), give(2, SELF, URDHVA_MUKHA, PASASANA)]

    got = timeline(track(), events)

    assert kinds(got[0]) == [K.NEW_ASANA, K.SERIES_COMPLETE, K.SERIES_BEGINS]
    assert got[0].celebrations[0].first == SETU


def test_given_again_after_a_change_back_is_quiet_with_no_markers() -> None:
    events = [
        start(1, URDHVA_MUKHA),
        give(2, SELF, URDHVA_MUKHA, SETU),
        give(3, SELF, SETU, PASASANA),
        changed(4, PASASANA, SETU),
        give(5, SELF, SETU, PASASANA),
    ]

    got = {e.event.id: e for e in timeline(track(), events)}

    assert kinds(got[2]) == [K.NEW_ASANA, K.SERIES_COMPLETE]
    assert kinds(got[3]) == [K.NEW_ASANA, K.SERIES_BEGINS]
    assert got[4].celebrations == ()
    assert got[5].celebrations == ()


def test_an_item_celebrates_only_the_first_time() -> None:
    events = [
        start(1, SETU),
        item(2, "drop-backs"),
        item(3, "drop-backs", given_=False),
        item(4, "drop-backs"),
    ]

    got = {e.event.id: e for e in timeline(track(), events)}

    assert got[2].celebrations == (Celebration(K.ITEM, key="drop-backs"),)
    assert got[3].celebrations == ()
    assert got[4].celebrations == ()


def test_a_correction_upward_counts_as_held_so_a_later_give_below_it_is_quiet() -> None:
    events = [
        start(1, NAVASANA),
        changed(2, NAVASANA, KAPOTASANA_B),
        changed(3, KAPOTASANA_B, SETU),
    ]
    events.append(give(4, SELF, SETU, PASASANA))

    got = timeline(track(), events)

    assert [e.celebrations for e in got] == [(), (), (), ()]


def test_stale_keys_never_celebrate() -> None:
    stale = P("primary", "no-such-asana")
    events = [start(1, NAVASANA), give(2, SELF, NAVASANA, stale), give(3, SELF, stale, KURMASANA)]

    got = {e.event.id: e for e in timeline(track(), events)}

    assert got[2].celebrations == ()
    assert got[3].celebrations == ()


def test_the_entry_keeps_the_event_as_is() -> None:
    mark = give(2, TEACHER, NAVASANA, KURMASANA)

    got = timeline(track(), [start(1, NAVASANA), mark])

    assert got[0].event is mark
    assert got[0].event.by_name == "Лена"


# Q159: the event that set the position, however old


def _items_after_a_mark(n: int) -> tuple[list[ProgressionEvent], ProgressionEvent]:
    mark = give(2, TEACHER, NAVASANA, KURMASANA)
    items = [
        item(3 + i, "drop-backs" if i % 2 == 0 else "standing-up", given_=i % 4 < 2)
        for i in range(n)
    ]
    newest_20 = [*reversed(items), mark, start(1)][:20]
    return newest_20, mark


def test_a_teachers_mark_stays_undoable_beyond_the_newest_20_events() -> None:
    newest, mark = _items_after_a_mark(25)
    assert mark not in newest

    assert undoable(newest, mark) == {newest[0].id, mark.id}
    assert teacher_mark(newest, mark) == mark


def test_without_the_position_event_only_the_window_counts() -> None:
    newest, _ = _items_after_a_mark(25)

    assert undoable(newest) == {newest[0].id}
    assert teacher_mark(newest) is None


@pytest.mark.parametrize(
    "position",
    [
        start(1, NAVASANA),
        give(2, SELF, NAVASANA, KURMASANA),
        ev(2, EventKind.CHANGED, TEACHER, NAVASANA, KURMASANA),
    ],
    ids=["start", "self-given", "teacher-changed"],
)
def test_a_position_set_otherwise_adds_nothing(position: ProgressionEvent) -> None:
    newest = [item(9)]

    assert undoable(newest, position) == {9}
    assert teacher_mark(newest, position) is None


def test_dates_are_kept_as_logged() -> None:
    first = ev(1, EventKind.START, after=NAVASANA)
    got = timeline(track(), [first])
    assert got[0].event.occurred_on == date(2026, 11, 8)


def test_a_cut_history_starts_from_what_was_reached_before() -> None:
    """With `before`, the first kept entries aren't first times (a history over the limit)."""
    events = [give(5, SELF, NAVASANA, KURMASANA), item(6, "drop-backs")]
    before = Earlier(frozenset({KURMASANA}), frozenset({"drop-backs"}))

    assert [e.celebrations for e in timeline(track(), events, before)] == [(), ()]
    assert [kinds(e) for e in timeline(track(), events)] == [[K.ITEM], [K.NEW_ASANA]]


def test_from_standing_only_the_first_asana_begins_primary() -> None:
    first = P("primary", "utthita-hasta-padangusthasana")
    got = timeline(track(), [start(1, STANDING_ONLY), give(2, SELF, STANDING_ONLY, first)])

    assert kinds(got[0]) == [K.NEW_ASANA, K.SERIES_BEGINS]
    assert got[0].celebrations[1].series == "primary"
