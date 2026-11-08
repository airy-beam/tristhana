"""Teacher marks, pure (PR-08 Phase 3, spec §2, ADR-0037): the next three stops after the
student's position (across a series boundary, from standing only, fewer near the end, none at the
end, unset or stale), the teacher's change (only from the position the teacher saw, only to one of
those stops, one GIVEN with `before` = what was seen), its celebrations (the range line, the series
lines, the quiet line when held before), who marked an event, and the undo rule: the newest event,
or a teacher's `given` that no later START/GIVEN/CHANGED has moved on from."""

from datetime import date
from functools import cache

import pytest

from tests.domain.test_practice import catalog
from tristhana.domain.progression import (
    STANDING_ONLY,
    TEACHER_STEPS,
    Celebration,
    CelebrationKind,
    Earlier,
    EventKind,
    InvalidProgression,
    Marker,
    NotForward,
    Position,
    Progression,
    ProgressionEvent,
    Track,
    celebrations,
    teacher_change,
    teacher_mark,
    teacher_targets,
    undoable,
)

ON = date(2026, 11, 8)
K = CelebrationKind
SELF, TEACHER = Marker.SELF, Marker.TEACHER


@cache
def track() -> Track:
    return Track(catalog())


def P(series: str, key: str) -> Position:
    return Position(series, key)


KAPOTASANA_B = P("intermediate", "kapotasana-b")
SUPTA_VAJRASANA = P("intermediate", "supta-vajrasana")
BAKASANA_B = P("intermediate", "bakasana-b")
BHARADVAJASANA = P("intermediate", "bharadvajasana")
ARDHA_MATSYENDRASANA = P("intermediate", "ardha-matsyendrasana")
URDHVA_MUKHA = P("primary", "urdhva-mukha-paschimottanasana")
SETU = P("primary", "setu-bandhasana")
PASASANA = P("intermediate", "pasasana")
KROUNCHASANA = P("intermediate", "krounchasana")
SALABHASANA_B = P("intermediate", "salabhasana-b")
NAVASANA = P("primary", "navasana")
BHUJAPIDASANA = P("primary", "bhujapidasana")
KURMASANA = P("primary", "kurmasana")
SUPTA_KURMASANA = P("primary", "supta-kurmasana")
SAMA_KONASANA = P("advanced-b", "sama-konasana")
URDHVA_DANDASANA = P("advanced-b", "urdhva-dandasana")
OMKARASANA = P("advanced-b", "omkarasana")


def at(position: Position, last_event_id: int = 1) -> Progression:
    return Progression(position, last_event_id=last_event_id)


def ev(
    id: int,
    kind: EventKind,
    by: Marker = SELF,
    before: Position | None = None,
    after: Position | None = None,
    item: str | None = None,
    by_name: str | None = None,
) -> ProgressionEvent:
    return ProgressionEvent(
        id=id,
        kind=kind,
        occurred_on=ON,
        before=before,
        after=after,
        item=item,
        by=by,
        by_name=by_name,
    )


def start(id: int, to: Position = NAVASANA) -> ProgressionEvent:
    return ev(id, EventKind.START, after=to)


def give(
    id: int, by: Marker = SELF, before: Position = NAVASANA, after: Position = KURMASANA
) -> ProgressionEvent:
    return ev(id, EventKind.GIVEN, by, before, after, by_name="Лена" if by is TEACHER else None)


def item(id: int, key: str = "drop-backs", given_: bool = True) -> ProgressionEvent:
    kind = EventKind.ITEM_GIVEN if given_ else EventKind.ITEM_REMOVED
    return ev(id, kind, item=key)


def changed(id: int, before: Position = KURMASANA, after: Position = NAVASANA) -> ProgressionEvent:
    return ev(id, EventKind.CHANGED, before=before, after=after)


# teacher_targets


def test_three_is_the_rule() -> None:
    assert TEACHER_STEPS == 3


def test_mid_series_gives_the_next_three_stops_in_catalog_order() -> None:
    assert teacher_targets(track(), at(KAPOTASANA_B)) == (
        SUPTA_VAJRASANA,
        BAKASANA_B,
        BHARADVAJASANA,
    )


def test_from_standing_only_the_targets_are_the_first_three_primary_stops() -> None:
    assert teacher_targets(track(), at(STANDING_ONLY)) == (
        P("primary", "utthita-hasta-padangusthasana"),
        P("primary", "ardha-baddha-padmottanasana"),
        P("primary", "utkatasana"),
    )


def test_from_setu_bandhasana_the_targets_cross_into_intermediate() -> None:
    """Full Primary → the first three Intermediate stops (catalog order)."""
    assert teacher_targets(track(), at(SETU)) == (PASASANA, KROUNCHASANA, SALABHASANA_B)


@pytest.mark.parametrize(
    ("position", "targets"),
    [
        (
            P("intermediate", "baddha-hasta-sirsasana-d"),
            (
                P("advanced-a", "vasisthasana"),
                P("advanced-a", "visvamitrasana"),
                P("advanced-a", "kasyapasana"),
            ),
        ),
        (
            P("primary", "janu-sirsasana-c"),
            (
                P("primary", "marichyasana-a"),
                P("primary", "marichyasana-b"),
                P("primary", "marichyasana-c"),
            ),
        ),
        (
            P("primary", "marichyasana-c"),
            (P("primary", "marichyasana-d"), NAVASANA, BHUJAPIDASANA),
        ),
        (
            P("intermediate", "laghu-vajrasana"),
            (KAPOTASANA_B, SUPTA_VAJRASANA, BAKASANA_B),
        ),
    ],
    ids=["bhs-d-into-advanced-a", "janu-c", "marichyasana-c", "laghu-vajrasana"],
)
def test_named_positions_give_the_expected_next_three(
    position: Position, targets: tuple[Position, ...]
) -> None:
    """Spot checks against the catalog (ashtanga-expert review)."""
    assert teacher_targets(track(), at(position)) == targets


def test_a_range_can_straddle_the_series_boundary() -> None:
    assert teacher_targets(track(), at(URDHVA_MUKHA)) == (SETU, PASASANA, KROUNCHASANA)


def test_near_the_end_of_the_confirmed_series_there_are_fewer() -> None:
    """Advanced C is pending, so Advanced B's last stop ends the track."""
    assert teacher_targets(track(), at(URDHVA_DANDASANA)) == (SAMA_KONASANA, OMKARASANA)
    assert teacher_targets(track(), at(SAMA_KONASANA)) == (OMKARASANA,)


def test_at_the_end_unset_or_stale_there_are_none() -> None:
    assert teacher_targets(track(), at(OMKARASANA)) == ()
    assert teacher_targets(track(), None) == ()
    assert teacher_targets(track(), at(P("primary", "renamed-asana"))) == ()


def _every_position() -> list[Position]:
    return [STANDING_ONLY, *(P(s.slug, x.key) for s in catalog().series for x in s.stops)]


@pytest.mark.parametrize("position", _every_position(), ids=str)
def test_targets_are_always_the_next_ranks_in_order(position: Position) -> None:
    """Every position of the track: at most 3, each one rank after the one before, starting
    right after the position, and as many as the track has left."""
    found = teacher_targets(track(), at(position))
    ranks = [track().rank(p) for p in found]
    base = track().rank(position)
    assert base is not None
    left = len(_every_position()) - 2 - base
    assert len(found) == min(TEACHER_STEPS, left)
    assert ranks == list(range(base + 1, base + 1 + len(found)))


# teacher_change


def test_a_change_is_one_given_from_what_the_teacher_saw() -> None:
    progression = Progression(KAPOTASANA_B, frozenset({"drop-backs"}), last_event_id=9)

    change = teacher_change(track(), progression, KAPOTASANA_B, SUPTA_VAJRASANA, ON)

    assert change.kind is EventKind.GIVEN
    assert change.before == KAPOTASANA_B
    assert change.after == SUPTA_VAJRASANA
    assert change.occurred_on == ON
    assert change.state.position == SUPTA_VAJRASANA
    assert change.state.items == {"drop-backs"}  # a teacher never touches the items


def test_a_three_stop_pick_is_still_one_given_starting_where_the_teacher_saw_it() -> None:
    change = teacher_change(track(), at(KAPOTASANA_B), KAPOTASANA_B, BHARADVAJASANA, ON)

    assert change.kind is EventKind.GIVEN
    assert (change.before, change.after) == (KAPOTASANA_B, BHARADVAJASANA)


@pytest.mark.parametrize("target", [SUPTA_VAJRASANA, BAKASANA_B, BHARADVAJASANA])
def test_each_of_the_next_three_is_allowed(target: Position) -> None:
    assert teacher_change(track(), at(KAPOTASANA_B), KAPOTASANA_B, target, ON).after == target


def test_a_stale_card_is_refused() -> None:
    """The student moved on (or changed back) after the teacher opened the card."""
    with pytest.raises(NotForward):
        teacher_change(track(), at(SUPTA_VAJRASANA), KAPOTASANA_B, BAKASANA_B, ON)


@pytest.mark.parametrize(
    "target",
    [
        KAPOTASANA_B,  # the same stop
        P("intermediate", "laghu-vajrasana"),  # earlier: a teacher never marks back
        STANDING_ONLY,
        ARDHA_MATSYENDRASANA,  # a 4th stop
        P("intermediate", "eka-pada-sirsasana"),  # further still
    ],
)
def test_only_the_next_three_are_allowed(target: Position) -> None:
    with pytest.raises(NotForward):
        teacher_change(track(), at(KAPOTASANA_B), KAPOTASANA_B, target, ON)


@pytest.mark.parametrize(
    "target",
    [
        P("intermediate", "kapotasana-a"),  # a posture, not a stop
        P("primary", "utthita-trikonasana-b"),  # standing, not a series stop
        P("advanced-c", "anything"),  # not a confirmed series
    ],
)
def test_a_non_stop_is_refused(target: Position) -> None:
    with pytest.raises(InvalidProgression):
        teacher_change(track(), at(KAPOTASANA_B), KAPOTASANA_B, target, ON)


def test_an_unset_student_is_refused() -> None:
    """A teacher never starts a record."""
    with pytest.raises(InvalidProgression):
        teacher_change(track(), None, STANDING_ONLY, P("primary", "utkatasana"), ON)


def test_a_stale_position_is_refused() -> None:
    stale = P("primary", "renamed-asana")
    with pytest.raises(InvalidProgression):
        teacher_change(track(), at(stale), stale, NAVASANA, ON)


# Celebrations of a teacher's pick (the existing rule, unchanged)


def _celebrate(
    seen: Position, target: Position, earlier: frozenset[Position] | None = None
) -> tuple[Celebration, ...]:
    change = teacher_change(track(), at(seen), seen, target, ON)
    return celebrations(track(), Earlier(earlier or frozenset({seen})), change)


def test_one_stop_celebrates_the_new_asana() -> None:
    assert _celebrate(KAPOTASANA_B, SUPTA_VAJRASANA) == (
        Celebration(K.NEW_ASANA, "intermediate", "supta-vajrasana"),
    )


def test_a_three_stop_pick_carries_the_first_new_stop_for_the_range_line() -> None:
    assert _celebrate(KAPOTASANA_B, BHARADVAJASANA) == (
        Celebration(K.NEW_ASANA, "intermediate", "bharadvajasana", first=SUPTA_VAJRASANA),
    )


def test_a_range_into_intermediate_completes_primary_and_begins_intermediate() -> None:
    got = _celebrate(URDHVA_MUKHA, KROUNCHASANA)

    assert got == (
        Celebration(K.NEW_ASANA, "intermediate", "krounchasana", first=SETU),
        Celebration(K.SERIES_COMPLETE, "primary"),
        Celebration(K.SERIES_BEGINS, "intermediate"),
    )


def test_from_setu_bandhasana_pasasana_begins_intermediate() -> None:
    assert _celebrate(SETU, PASASANA) == (
        Celebration(K.NEW_ASANA, "intermediate", "pasasana"),
        Celebration(K.SERIES_BEGINS, "intermediate"),
    )


def test_a_pick_ending_at_a_stop_held_before_is_quiet() -> None:
    """Was at Bharadvajasana, changed back to Kapotasana (injury); the teacher gives it again."""
    assert _celebrate(KAPOTASANA_B, BAKASANA_B, frozenset({KAPOTASANA_B, BHARADVAJASANA})) == ()


# Who marked it


def test_an_event_says_who_marked_it_and_keeps_marked_by_self() -> None:
    mine, theirs, gone = give(1), give(2, TEACHER), ev(3, EventKind.GIVEN, TEACHER, NAVASANA, SETU)

    assert (mine.by, mine.marked_by_self, mine.by_name) == (SELF, True, None)
    assert (theirs.by, theirs.marked_by_self, theirs.by_name) == (TEACHER, False, "Лена")
    assert (gone.by, gone.marked_by_self, gone.by_name) == (TEACHER, False, None)


# undoable (events newest first, as `ProgressionView.events`)


def test_the_newest_event_is_always_undoable() -> None:
    assert undoable([]) == frozenset()
    assert undoable([start(1)]) == {1}
    assert undoable([give(2), start(1)]) == {2}
    assert undoable([item(3), give(2), start(1)]) == {3}
    assert undoable([changed(3), give(2, TEACHER), start(1)]) == {3}


def test_a_teachers_mark_followed_only_by_items_stays_undoable() -> None:
    events = [item(5, "standing-up"), item(4, "drop-backs", False), item(3), give(2, TEACHER)]

    assert undoable([*events, start(1)]) == {5, 2}


@pytest.mark.parametrize(
    "later",
    [
        changed(3, KURMASANA, NAVASANA),  # ✏️ Change
        give(3, SELF, KURMASANA, SUPTA_KURMASANA),  # the student's own give
        give(3, TEACHER, KURMASANA, SUPTA_KURMASANA),  # another teacher's give
    ],
    ids=["changed", "self-given", "teacher-given"],
)
def test_a_teachers_mark_is_not_undoable_once_the_position_moved_on(
    later: ProgressionEvent,
) -> None:
    events = [item(4), later, give(2, TEACHER), start(1)]

    assert undoable(events) == {4} | ({3} if later.by is TEACHER else set())


def test_the_students_own_give_keeps_latest_only_undo() -> None:
    assert undoable([item(3), give(2, SELF), start(1)]) == {3}


def test_a_mark_from_a_deleted_teacher_is_still_a_teachers() -> None:
    """`marked_by` NULL reads as TEACHER with no name, and stays undoable."""
    deleted = ev(2, EventKind.GIVEN, TEACHER, NAVASANA, KURMASANA)

    assert undoable([item(3), deleted, start(1)]) == {3, 2}


def test_a_teachers_start_or_change_isnt_a_mark() -> None:
    """Only a `given` by a teacher is retractable; other kinds never come from one, and if a row
    said so they would keep latest-only undo."""
    odd_start = ev(1, EventKind.START, TEACHER, after=NAVASANA)
    odd_change = ev(2, EventKind.CHANGED, TEACHER, NAVASANA, KURMASANA)

    assert undoable([item(3), odd_change, odd_start]) == {3}


# teacher_mark: the event that set the current position, if a teacher's `given`


def test_the_current_position_by_a_teacher_is_found_past_items() -> None:
    mark = give(2, TEACHER)

    assert teacher_mark([item(4), item(3, "standing-up"), mark, start(1)]) == mark
    assert teacher_mark([mark, start(1)]) == mark


@pytest.mark.parametrize(
    "events",
    [
        [],
        [start(1)],
        [give(2, SELF), start(1)],
        [changed(3), give(2, TEACHER), start(1)],
        [give(3, SELF, KURMASANA, SUPTA_KURMASANA), give(2, TEACHER), start(1)],
    ],
    ids=["empty", "start", "self-given", "changed-after", "self-given-after"],
)
def test_no_teacher_mark_when_the_position_was_set_otherwise(
    events: list[ProgressionEvent],
) -> None:
    assert teacher_mark(events) is None


def test_undoing_a_three_stop_pick_restores_where_it_started() -> None:
    """Undo restores the event's `from`: the whole range goes, not one stop."""
    change = teacher_change(track(), at(KAPOTASANA_B), KAPOTASANA_B, BHARADVAJASANA, ON)
    mark = ev(2, EventKind.GIVEN, TEACHER, change.before, change.after)

    assert 2 in undoable([item(3), mark])
    assert mark.before == KAPOTASANA_B
