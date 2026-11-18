"""Teacher requests, the pure rules (ID-07 spec §3, §8; ADR-0046): the three predicates on
both sides of the 7 days, the closing note, the ask for every cap, the export's words, and
that nothing a student can observe tells a quiet "no" from waiting.

The moon rule gets no new code: the last tests pin that an approval changes nothing for the
approver, and moves a student's city in two cases only (spec §3)."""

import ast
import itertools
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest

from tests.fakes import cities
from tristhana.domain.moon import FOLLOW_SHALA, FOLLOW_TEACHER, ShalaMoon, TeacherMoon, moon_follow
from tristhana.domain.shalas import main_shala
from tristhana.domain.teacher_links import MAX_STUDENTS, MAX_TEACHERS
from tristhana.domain.teacher_requests import (
    ANSWER_WITHIN,
    KEEP,
    MAX_ASKING,
    MAX_WAITING,
    AskState,
    Closing,
    RequestCaps,
    RequestConsent,
    RequestState,
    answerable,
    ask_state,
    closing_due,
    counts_as_asked,
    exported_state,
    grants_quiet_note,
    kept,
    request_key,
    waiting_for_student,
    waiting_for_teacher,
)

ASKED = datetime(2026, 11, 17, 6, 30, tzinfo=UTC)
JUST_BEFORE = ASKED + ANSWER_WITHIN - timedelta(microseconds=1)
DAY_7 = ASKED + ANSWER_WITHIN
WAITING, DECLINED, WITHDRAWN, APPROVED = (
    RequestState.WAITING,
    RequestState.DECLINED,
    RequestState.WITHDRAWN,
    RequestState.APPROVED,
)
MOMENTS = (ASKED, JUST_BEFORE, DAY_7, ASKED + timedelta(days=20), ASKED + KEEP)


def test_the_numbers_the_owner_chose() -> None:
    assert timedelta(days=7) == ANSWER_WITHIN  # Q318
    assert timedelta(days=30) == KEEP  # Q317
    assert (MAX_ASKING, MAX_WAITING) == (3, 100)  # Q319
    assert RequestCaps() == RequestCaps(3, 100, MAX_TEACHERS, MAX_STUDENTS)


def test_the_stored_states() -> None:
    assert {s.value for s in RequestState} == {"waiting", "declined", "withdrawn", "approved"}


# The three predicates, on both sides of the 7 days


@pytest.mark.parametrize(
    ("state", "student", "teacher", "can_answer"),
    [
        (WAITING, True, True, True),
        (DECLINED, True, False, True),  # a quiet no: the student waits, Undo still works
        (WITHDRAWN, False, False, False),
        (APPROVED, False, False, False),
    ],
)
def test_inside_the_seven_days(
    state: RequestState, student: bool, teacher: bool, can_answer: bool
) -> None:
    for now in (ASKED, JUST_BEFORE):
        assert waiting_for_student(state, ASKED, now) is student
        assert waiting_for_teacher(state, ASKED, now) is teacher
        assert answerable(state, ASKED, now) is can_answer


@pytest.mark.parametrize("state", list(RequestState))
def test_from_day_seven_exactly_nothing_waits(state: RequestState) -> None:
    for now in (DAY_7, DAY_7 + timedelta(days=3)):
        assert not waiting_for_student(state, ASKED, now)
        assert not waiting_for_teacher(state, ASKED, now)
        assert not answerable(state, ASKED, now)


def test_a_row_stands_for_the_pair_for_thirty_days() -> None:
    assert kept(ASKED, ASKED + KEEP - timedelta(microseconds=1))
    assert not kept(ASKED, ASKED + KEEP)


# The student's three asks in any seven days


@pytest.mark.parametrize("state", [WAITING, DECLINED, WITHDRAWN])
def test_an_ask_counts_for_seven_days_however_it_went(state: RequestState) -> None:
    """A withdrawal frees no slot, or "ask three, withdraw three, ask three more" would
    reach any number of teachers; a quiet no counts exactly as waiting does."""
    assert counts_as_asked(state, ASKED, ASKED)
    assert counts_as_asked(state, ASKED, JUST_BEFORE)
    assert not counts_as_asked(state, ASKED, DAY_7)


@pytest.mark.parametrize("now", MOMENTS)
def test_a_confirmed_ask_is_a_link_and_not_one_of_the_three(now: datetime) -> None:
    assert not counts_as_asked(APPROVED, ASKED, now)  # the teachers cap counts the link


# The closing note


def test_confirmed_is_due_at_once() -> None:
    assert closing_due(APPROVED, ASKED, True, ASKED) is Closing.CONFIRMED
    assert closing_due(APPROVED, ASKED, True, ASKED + timedelta(days=20)) is Closing.CONFIRMED


@pytest.mark.parametrize("state", [WAITING, DECLINED])
def test_no_answer_is_due_at_day_seven_exactly(state: RequestState) -> None:
    assert closing_due(state, ASKED, False, JUST_BEFORE) is None
    assert closing_due(state, ASKED, False, DAY_7) is Closing.NO_ANSWER


@pytest.mark.parametrize("now", MOMENTS)
def test_no_note_once_linked_another_way_withdrawn_or_unlinked_again(now: datetime) -> None:
    assert closing_due(WAITING, ASKED, True, now) is None  # the personal link won
    assert closing_due(DECLINED, ASKED, True, now) is None
    assert closing_due(WITHDRAWN, ASKED, False, now) is None
    assert closing_due(WITHDRAWN, ASKED, True, now) is None
    assert closing_due(APPROVED, ASKED, False, now) is None  # approved, then the link went


# The ask


def _ask(**facts: object) -> AskState:
    base: dict[str, object] = {
        "linked": False,
        "earlier": None,
        "now": ASKED,
        "my_asked": 0,
        "my_waiting": 0,
        "my_teachers": 0,
        "their_waiting": 0,
        "their_students": 0,
    }
    return ask_state(**(base | facts))  # type: ignore[arg-type]


def test_a_first_ask_is_created() -> None:
    assert _ask() is AskState.CREATED
    facts = {"my_asked": 2, "my_waiting": 2, "their_waiting": 99}
    assert _ask(**facts, my_teachers=17, their_students=400) is AskState.CREATED


def test_a_link_wins_over_everything() -> None:
    assert _ask(linked=True, earlier=(WAITING, ASKED), my_asked=3) is AskState.LINKED


@pytest.mark.parametrize(
    ("facts", "state"),
    [
        ({"my_asked": MAX_ASKING}, AskState.TOO_MANY),
        ({"my_asked": MAX_ASKING, "my_waiting": 0}, AskState.TOO_MANY),  # all three withdrawn
        ({"my_asked": MAX_ASKING - 1, "my_waiting": MAX_ASKING}, AskState.CREATED),  # older asks
        ({"my_teachers": MAX_TEACHERS}, AskState.TOO_MANY),
        ({"my_teachers": MAX_TEACHERS - 2, "my_waiting": 2}, AskState.TOO_MANY),
        ({"their_waiting": MAX_WAITING}, AskState.FULL),
        ({"their_students": MAX_STUDENTS}, AskState.FULL),
        ({"their_students": MAX_STUDENTS - 40, "their_waiting": 40}, AskState.FULL),
        ({"my_asked": MAX_ASKING, "their_waiting": MAX_WAITING}, AskState.TOO_MANY),
    ],
)
def test_every_cap(facts: dict[str, int], state: AskState) -> None:
    assert _ask(**facts) is state


def test_the_caps_can_be_lowered() -> None:
    caps = RequestCaps(asking=1, waiting=1, teachers=2, students=2)

    assert ask_state(
        linked=False, earlier=None, now=ASKED, my_asked=1, my_waiting=0, my_teachers=0,
        their_waiting=0, their_students=0, caps=caps,
    ) is AskState.TOO_MANY  # fmt: skip
    assert ask_state(
        linked=False, earlier=None, now=ASKED, my_asked=0, my_waiting=0, my_teachers=0,
        their_waiting=0, their_students=2, caps=caps,
    ) is AskState.FULL  # fmt: skip


def test_the_pairs_own_row_blocks_a_new_ask_for_thirty_days() -> None:
    week = ASKED + ANSWER_WITHIN

    assert _ask(earlier=(WAITING, ASKED), now=JUST_BEFORE) is AskState.WAITING
    assert _ask(earlier=(WAITING, ASKED), now=week) is AskState.RECENT
    assert _ask(earlier=(WITHDRAWN, ASKED), now=ASKED) is AskState.RECENT
    assert _ask(earlier=(APPROVED, ASKED), now=week) is AskState.RECENT  # unlinked since
    assert _ask(earlier=(WITHDRAWN, ASKED), now=ASKED + KEEP) is AskState.CREATED
    assert _ask(earlier=(DECLINED, ASKED), now=ASKED + KEEP) is AskState.CREATED


def test_after_a_rejoin_the_old_row_blocks_but_no_longer_waits() -> None:
    for state in (WAITING, DECLINED):
        assert _ask(earlier=(state, ASKED), still_valid=False) is AskState.RECENT
        assert _ask(earlier=(state, ASKED), still_valid=True) is AskState.WAITING
    assert _ask(earlier=(WAITING, ASKED), now=ASKED + KEEP, still_valid=False) is AskState.CREATED


# The export's words (ST-09)


def test_the_student_reads_four_words_and_never_a_refusal() -> None:
    words = {exported_state(True, state, ASKED, now) for state in RequestState for now in MOMENTS}

    assert words == {"waiting", "no_answer", "confirmed", "withdrawn"}


def test_the_teacher_reads_their_own_answer() -> None:
    assert exported_state(False, WAITING, ASKED, ASKED) == "waiting"
    assert exported_state(False, WAITING, ASKED, DAY_7) == "closed"
    assert exported_state(False, WITHDRAWN, ASKED, ASKED) == "closed"
    assert exported_state(False, DECLINED, ASKED, ASKED) == "declined"
    assert exported_state(False, DECLINED, ASKED, DAY_7) == "declined"
    assert exported_state(False, APPROVED, ASKED, DAY_7) == "confirmed"


# A quiet "no" and silence look the same (spec §7, ADR-0046)


@pytest.mark.parametrize("now", MOMENTS)
def test_every_student_facing_function_is_equal_for_waiting_and_declined(now: datetime) -> None:
    assert waiting_for_student(DECLINED, ASKED, now) == waiting_for_student(WAITING, ASKED, now)
    assert exported_state(True, DECLINED, ASKED, now) == exported_state(True, WAITING, ASKED, now)
    for linked in (False, True):
        assert closing_due(DECLINED, ASKED, linked, now) == closing_due(WAITING, ASKED, linked, now)
    assert _ask(earlier=(DECLINED, ASKED), now=now) == _ask(earlier=(WAITING, ASKED), now=now)
    assert counts_as_asked(DECLINED, ASKED, now) == counts_as_asked(WAITING, ASKED, now)


def test_the_ledger_key() -> None:
    id = UUID("4b1d9b0e-6a56-4d0c-8f55-0d3c7f1a2b3c")

    assert request_key(id) == "req:4b1d9b0e-6a56-4d0c-8f55-0d3c7f1a2b3c"
    assert len(request_key(id)) == 40


def test_the_module_is_pure() -> None:
    source = Path(__file__).resolve().parents[2] / "src/tristhana/domain/teacher_requests.py"
    tree = ast.parse(source.read_text())

    imported = {
        node.module or "" if isinstance(node, ast.ImportFrom) else alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import | ast.ImportFrom)
        for alias in node.names
    }

    assert imported <= {
        "dataclasses",
        "datetime",
        "enum",
        "uuid",
        "tristhana.domain.teacher_links",
    }


# Moon (MD-02, ADR-0032/0033): no write, no Keep offer, and two promised moves

TEACHERS = (
    None,
    TeacherMoon(UUID(int=1), "Anna", "almaty"),
    TeacherMoon(UUID(int=2), "Boris", None),
    TeacherMoon(UUID(int=3), "Clara", FOLLOW_TEACHER),
    TeacherMoon(UUID(int=4), "Dana", FOLLOW_SHALA),
)
STAFF_SHALAS = (
    ShalaMoon(UUID(int=20), "Ashtanga Kyiv", "kyiv", True, False, "kyiv"),
    ShalaMoon(UUID(int=21), "Almaty Shala", "atlantis", True, False, "almaty"),  # Q111
)


@pytest.mark.parametrize(
    ("own", "teacher", "shala"),
    list(itertools.product((None, "moscow", FOLLOW_SHALA, FOLLOW_TEACHER), TEACHERS, STAFF_SHALAS)),
)
def test_a_first_student_changes_nothing_for_an_approver(
    own: str | None, teacher: TeacherMoon | None, shala: ShalaMoon
) -> None:
    """An approver is always on a shala's staff, so their main shala is a staff row, and the
    rule returns before `teaches` is read: no Keep offer is owed (ADR-0046)."""
    before = moon_follow(own, False, teacher, shala, cities())
    after = moon_follow(own, True, teacher, shala, cities())

    assert after == before


HERE = UUID(int=30)  # the shala the request came through: the teacher is on its staff
ELSEWHERE = UUID(int=31)
OLDER, NEWER = datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 6, 1, tzinfo=UTC)


def _student_city(
    own: str | None, teaches: bool, teacher: TeacherMoon | None, other: str | None
) -> str:
    """The student's moon city, as the account load would give it: a member of HERE (Kyiv)
    and maybe of an older shala ELSEWHERE (Moscow), as a student or on its staff."""
    on_staff = teacher is not None
    memberships = [(ShalaMoon(HERE, "Kyiv Shala", "kyiv", False, on_staff, "kyiv"), NEWER)]
    if other is not None:
        elsewhere = ShalaMoon(ELSEWHERE, "Moscow Shala", "moscow", other == "staff", False)
        memberships.append((elsewhere, OLDER))
    return moon_follow(own, teaches, teacher, main_shala(memberships), cities()).city.slug


def test_an_approval_moves_a_students_city_only_through_the_main_shala_or_follow_my_teacher() -> (
    None
):
    """A first teacher through a request moves the student's city in these cases only:
    (1) a member of an older, main shala elsewhere now has the shala their teacher teaches at
    as the main one (Q108), whether they never chose or chose "Follow my shala"; (2) a stored
    "Follow my teacher" finds a teacher with a city of their own. The spec names (1) for
    never-chose students; "Follow my shala" is the same switch of the main shala. A second
    teacher is never main, so it moves nothing."""
    moved: set[tuple[str | None, str | None, bool]] = set()
    for own, teaches, teacher, other in itertools.product(
        (None, "almaty", FOLLOW_SHALA, FOLLOW_TEACHER),
        (False, True),
        TEACHERS[1:],
        (None, "student", "staff"),
    ):
        before = _student_city(own, teaches, None, other)
        after = _student_city(own, teaches, teacher, other)
        if after != before:
            moved.add((own, other, cities().find(teacher.moon_location) is not None))

    assert moved == {
        (None, "student", True),  # Q108, whatever the teacher's own setting
        (None, "student", False),
        (FOLLOW_SHALA, "student", True),  # the same switch, under a stored "Follow my shala"
        (FOLLOW_SHALA, "student", False),
        (FOLLOW_TEACHER, None, True),  # the teacher has a listed city of their own
        (FOLLOW_TEACHER, "student", True),
        (FOLLOW_TEACHER, "staff", True),
    }


# The consent a request names (ADR-0049)


def test_the_first_request_consent_grants_the_quiet_note() -> None:
    """Both layers of `request-consent` name the note, and `request-1` is what they promise."""
    assert RequestConsent.FIRST.value == "request-1"
    assert grants_quiet_note(RequestConsent.FIRST) is True


@pytest.mark.parametrize("consent", list(RequestConsent))
def test_every_request_consent_is_mapped(consent: RequestConsent) -> None:
    """A new value is a new set of promises: it must say what it grants, never fall through."""
    assert isinstance(grants_quiet_note(consent), bool)


def test_a_consent_is_named_by_its_value_and_nothing_else() -> None:
    assert RequestConsent("request-1") is RequestConsent.FIRST
    with pytest.raises(ValueError, match="request-0"):
        RequestConsent("request-0")
