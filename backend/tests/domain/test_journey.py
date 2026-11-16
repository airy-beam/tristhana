"""UI-06 (spec §2 M0, §3; Q310): who meets the front door, and what the Menu holds. Pure:
everything comes from the loaded account, so neither needs a read. Stage 2 (spec §6, Q334):
the next step on the Today tab, from the account and one read's facts."""

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

import pytest

from tristhana.domain.accounts import Account
from tristhana.domain.days import DayStatus
from tristhana.domain.journey import (
    INVITE_FRESH_DAYS,
    OTHER_REASONS,
    JourneyFacts,
    MenuItem,
    NextStep,
    OwnedShala,
    Step,
    front_door,
    menu_for,
    next_steps,
)
from tristhana.domain.moon import ShalaMoon, TeacherMoon

NOBODY = Account(
    id=UUID(int=1),
    display_name="Ash",
    locale="en",
    timezone="Asia/Almaty",
    last_seen_at=datetime(2026, 11, 16, tzinfo=UTC),
)
ANNA = TeacherMoon(UUID(int=2), "Anna", "almaty")
STUDENT_OF = ShalaMoon(UUID(int=20), "Ashtanga Almaty", "almaty", False, False)
STAFF_AT = ShalaMoon(UUID(int=21), "Ashtanga Almaty", "almaty", True, False)

M = MenuItem
BASE = (M.TODAY, M.PRACTICE, M.MOON, M.TEACHER, M.SETTINGS, M.HELP)


# The front door


def test_a_new_account_is_not_welcomed() -> None:
    assert NOBODY.welcomed is False


def test_a_new_person_without_activity_meets_the_front_door() -> None:
    assert front_door(NOBODY, has_days=False) is True


def test_the_front_door_is_shown_once() -> None:
    assert front_door(replace(NOBODY, welcomed=True), has_days=False) is False


@pytest.mark.parametrize(
    "account",
    [
        replace(NOBODY, teaches=True),
        replace(NOBODY, main_teacher=ANNA),
        replace(NOBODY, shala=STUDENT_OF),
        replace(NOBODY, shala=STAFF_AT),
    ],
    ids=["student", "link", "shala", "staff"],
)
def test_any_activity_on_the_account_skips_the_front_door(account: Account) -> None:
    assert front_door(account, has_days=False) is False


def test_a_logged_day_skips_the_front_door() -> None:
    assert front_door(NOBODY, has_days=True) is False


# The Menu


def test_the_order_is_the_enums_order() -> None:
    assert list(MenuItem) == [
        M.TODAY, M.PRACTICE, M.MOON, M.CLASSES, M.TEACHER, M.STUDENTS, M.SETTINGS, M.HELP,
        M.TEACH,
    ]  # fmt: skip


def test_nobody() -> None:
    assert menu_for(NOBODY) == (*BASE, M.TEACH)


def test_a_student_with_a_teacher_has_the_same_menu() -> None:
    assert menu_for(replace(NOBODY, main_teacher=ANNA)) == (*BASE, M.TEACH)


def test_a_shala_student_gets_classes_and_keeps_the_quiet_row() -> None:
    """Q310: joining a shala as a student does not hide "For teachers and shalas"."""
    assert menu_for(replace(NOBODY, shala=STUDENT_OF)) == (
        M.TODAY, M.PRACTICE, M.MOON, M.CLASSES, M.TEACHER, M.SETTINGS, M.HELP, M.TEACH,
    )  # fmt: skip


def test_a_teacher_gets_my_students_and_no_quiet_row() -> None:
    assert menu_for(replace(NOBODY, teaches=True)) == (
        M.TODAY, M.PRACTICE, M.MOON, M.TEACHER, M.STUDENTS, M.SETTINGS, M.HELP,
    )  # fmt: skip


def test_staff_without_students_get_classes_and_keep_the_quiet_row() -> None:
    # A teacher on a shala's staff with no students yet still needs the way to the first invite.
    assert menu_for(replace(NOBODY, shala=STAFF_AT)) == (
        M.TODAY, M.PRACTICE, M.MOON, M.CLASSES, M.TEACHER, M.SETTINGS, M.HELP, M.TEACH,
    )  # fmt: skip


def test_a_teacher_on_staff_gets_all_eight_rows() -> None:
    both = replace(NOBODY, teaches=True, shala=STAFF_AT)

    assert menu_for(both) == tuple(m for m in MenuItem if m is not M.TEACH)
    assert len(menu_for(both)) == 8


def test_a_teacher_who_is_a_student_of_a_shala_has_no_quiet_row() -> None:
    assert M.TEACH not in menu_for(replace(NOBODY, teaches=True, shala=STUDENT_OF))


@pytest.mark.parametrize("teaches", [False, True])
@pytest.mark.parametrize("teacher", [None, ANNA])
@pytest.mark.parametrize("shala", [None, STUDENT_OF, STAFF_AT])
@pytest.mark.parametrize("welcomed", [False, True])
def test_at_most_eight_rows_plus_the_quiet_one_in_the_fixed_order(
    teaches: bool, teacher: TeacherMoon | None, shala: ShalaMoon | None, welcomed: bool
) -> None:
    account = replace(NOBODY, teaches=teaches, main_teacher=teacher, shala=shala, welcomed=welcomed)

    menu = menu_for(account)

    order = list(MenuItem)
    assert sorted(menu, key=order.index) == list(menu)
    assert len(set(menu)) == len(menu)
    assert len([m for m in menu if m is not M.TEACH]) <= 8
    assert set(BASE) <= set(menu)
    assert (M.TEACH in menu) == (not teaches)
    assert (M.TEACH in menu) != (M.STUDENTS in menu)
    if M.TEACH in menu:
        assert menu[-1] is M.TEACH


# "Other reason" (T1)


def test_other_reasons_are_the_statuses_behind_the_third_button() -> None:
    assert OTHER_REASONS == (
        DayStatus.MOON,
        DayStatus.LADIES,
        DayStatus.SICK,
        DayStatus.TRAVEL,
        DayStatus.SKIPPED,
    )
    assert DayStatus.PRACTICED not in OTHER_REASONS
    assert DayStatus.REST not in OTHER_REASONS
    assert set(OTHER_REASONS) | {DayStatus.PRACTICED, DayStatus.REST} == set(DayStatus)


# The next step (stage 2, spec §6)

TODAY = date(2026, 11, 16)
N = NextStep
SETTLED = JourneyFacts(has_days=True, reminder_answered=True, position_set=True)
FIRST, SECOND = UUID(int=31), UUID(int=32)


def kinds(account: Account, facts: JourneyFacts) -> list[NextStep]:
    return [s.kind for s in next_steps(account, facts, TODAY)]


def test_the_offer_order_is_the_enums_order() -> None:
    assert list(NextStep) == [
        N.ADD_CLASS, N.INVITE_SHALA_STUDENTS, N.INVITE_STUDENT, N.REMINDER, N.POSITION,
    ]  # fmt: skip
    assert [n.value for n in NextStep] == [
        "add_class", "invite_shala_students", "invite_student", "reminder", "position",
    ]  # fmt: skip


def test_nobody_before_the_first_logged_day_has_no_step() -> None:
    """The day card is the step: nothing competes with it."""
    assert next_steps(NOBODY, JourneyFacts(), TODAY) == ()


def test_nothing_before_the_first_day_even_with_a_teacher_and_a_shala() -> None:
    student = replace(NOBODY, main_teacher=ANNA, shala=STUDENT_OF)

    assert next_steps(student, JourneyFacts(), TODAY) == ()


def test_a_student_after_the_first_day_gets_the_reminder_then_the_position() -> None:
    assert next_steps(NOBODY, JourneyFacts(has_days=True), TODAY) == (
        Step(N.REMINDER),
        Step(N.POSITION),
    )


def test_an_answered_reminder_leaves_the_position() -> None:
    """ "Yes" and "no" both answer it: the fact is that it was chosen, not what."""
    facts = JourneyFacts(has_days=True, reminder_answered=True)

    assert next_steps(NOBODY, facts, TODAY) == (Step(N.POSITION),)


def test_a_set_position_leaves_the_reminder() -> None:
    facts = JourneyFacts(has_days=True, position_set=True)

    assert next_steps(NOBODY, facts, TODAY) == (Step(N.REMINDER),)


def test_answers_given_before_the_first_day_offer_nothing_later() -> None:
    assert next_steps(NOBODY, JourneyFacts(reminder_answered=True, position_set=True), TODAY) == ()


def test_a_person_to_whom_nothing_applies_has_no_step() -> None:
    assert next_steps(NOBODY, SETTLED, TODAY) == ()
    assert next_steps(replace(NOBODY, teaches=True, shala=STAFF_AT), SETTLED, TODAY) == ()


# "Invite your first student" (Q334)


def test_a_teacher_with_a_link_and_nobody_on_it_is_offered_the_invite() -> None:
    facts = JourneyFacts(invite_made_on=TODAY)

    assert next_steps(NOBODY, facts, TODAY) == (Step(N.INVITE_STUDENT),)


def test_the_invite_comes_before_the_students_own_steps() -> None:
    facts = JourneyFacts(has_days=True, invite_made_on=TODAY - timedelta(days=3))

    assert kinds(NOBODY, facts) == [N.INVITE_STUDENT, N.REMINDER, N.POSITION]


def test_the_invite_goes_when_the_first_student_joins() -> None:
    """Then as a student: `teaches` comes with the account."""
    facts = JourneyFacts(has_days=True, invite_made_on=TODAY)

    assert kinds(replace(NOBODY, teaches=True), facts) == [N.REMINDER, N.POSITION]


def test_no_link_no_invite_step() -> None:
    assert N.INVITE_STUDENT not in kinds(NOBODY, JourneyFacts(has_days=True))


@pytest.mark.parametrize(
    ("age", "offered"),
    [(0, True), (1, True), (29, True), (30, True), (31, False), (400, False)],
)
def test_the_invite_is_offered_while_the_link_is_at_most_30_days_old(
    age: int, offered: bool
) -> None:
    assert INVITE_FRESH_DAYS == 30
    facts = JourneyFacts(invite_made_on=TODAY - timedelta(days=age))

    assert (N.INVITE_STUDENT in kinds(NOBODY, facts)) is offered


def test_a_link_dated_after_today_counts_as_fresh() -> None:
    """The link's date is UTC, `today` the person's: west of UTC it can be "tomorrow"."""
    facts = JourneyFacts(invite_made_on=TODAY + timedelta(days=1))

    assert kinds(NOBODY, facts) == [N.INVITE_STUDENT]


def test_a_shala_owner_is_never_offered_the_teachers_invite() -> None:
    """Q334: the shala steps cover it, also once they are done."""
    done = OwnedShala(FIRST, classes=2, students=5)
    empty = OwnedShala(FIRST, classes=0, students=0)

    assert kinds(NOBODY, JourneyFacts(invite_made_on=TODAY, owned=(done,))) == []
    assert kinds(NOBODY, JourneyFacts(invite_made_on=TODAY, owned=(empty,))) == [N.ADD_CLASS]


# The shala owner


def test_an_owner_with_no_class_is_offered_to_add_one() -> None:
    facts = JourneyFacts(owned=(OwnedShala(FIRST, classes=0, students=0),))

    assert next_steps(replace(NOBODY, shala=STAFF_AT), facts, TODAY) == (Step(N.ADD_CLASS, FIRST),)


def test_students_without_a_class_still_ask_for_the_class() -> None:
    facts = JourneyFacts(owned=(OwnedShala(FIRST, classes=0, students=4),))

    assert next_steps(NOBODY, facts, TODAY) == (Step(N.ADD_CLASS, FIRST),)


def test_an_owner_with_classes_and_no_students_is_offered_to_invite_them() -> None:
    facts = JourneyFacts(owned=(OwnedShala(FIRST, classes=3, students=0),))

    assert next_steps(NOBODY, facts, TODAY) == (Step(N.INVITE_SHALA_STUDENTS, FIRST),)


def test_a_complete_shala_offers_nothing() -> None:
    facts = JourneyFacts(owned=(OwnedShala(FIRST, classes=1, students=1),))

    assert next_steps(NOBODY, facts, TODAY) == ()


def test_the_oldest_shala_without_a_class_is_the_one_named() -> None:
    """`owned` is oldest first; one step of a kind, never a list of shalas."""
    facts = JourneyFacts(
        owned=(
            OwnedShala(UUID(int=30), classes=1, students=1),
            OwnedShala(FIRST, classes=0, students=0),
            OwnedShala(SECOND, classes=0, students=0),
        )
    )

    assert next_steps(NOBODY, facts, TODAY) == (Step(N.ADD_CLASS, FIRST),)


def test_two_shalas_at_different_steps_give_both_class_first() -> None:
    facts = JourneyFacts(
        owned=(
            OwnedShala(FIRST, classes=2, students=0),
            OwnedShala(SECOND, classes=0, students=0),
        )
    )

    assert next_steps(NOBODY, facts, TODAY) == (
        Step(N.ADD_CLASS, SECOND),
        Step(N.INVITE_SHALA_STUDENTS, FIRST),
    )


def test_an_owner_who_also_practices_gets_the_shala_step_first() -> None:
    facts = JourneyFacts(has_days=True, owned=(OwnedShala(FIRST, classes=0, students=0),))

    assert kinds(NOBODY, facts) == [N.ADD_CLASS, N.REMINDER, N.POSITION]


def test_an_owner_and_teacher_at_once_gets_every_due_step_in_order() -> None:
    """Owns two shalas, has a fresh link and students of their own, and practices."""
    facts = JourneyFacts(
        has_days=True,
        invite_made_on=TODAY,
        owned=(
            OwnedShala(FIRST, classes=0, students=0),
            OwnedShala(SECOND, classes=1, students=0),
        ),
    )
    both = replace(NOBODY, teaches=True, shala=STAFF_AT)

    assert next_steps(both, facts, TODAY) == (
        Step(N.ADD_CLASS, FIRST),
        Step(N.INVITE_SHALA_STUDENTS, SECOND),
        Step(N.REMINDER),
        Step(N.POSITION),
    )


@pytest.mark.parametrize("has_days", [False, True])
@pytest.mark.parametrize("reminder", [False, True])
@pytest.mark.parametrize("position", [False, True])
@pytest.mark.parametrize("age", [None, 0, 30, 31])
@pytest.mark.parametrize("teaches", [False, True])
@pytest.mark.parametrize(
    "owned",
    [
        (),
        (OwnedShala(FIRST, 0, 0),),
        (OwnedShala(FIRST, 1, 0),),
        (OwnedShala(FIRST, 1, 1),),
        (OwnedShala(FIRST, 1, 0), OwnedShala(SECOND, 0, 3)),
    ],
)
def test_steps_are_unique_in_the_fixed_order_and_name_only_owned_shalas(
    has_days: bool,
    reminder: bool,
    position: bool,
    age: int | None,
    teaches: bool,
    owned: tuple[OwnedShala, ...],
) -> None:
    made = None if age is None else TODAY - timedelta(days=age)
    facts = JourneyFacts(has_days, reminder, position, made, owned)

    steps = next_steps(replace(NOBODY, teaches=teaches), facts, TODAY)

    order = list(NextStep)
    found = [s.kind for s in steps]
    assert sorted(found, key=order.index) == found
    assert len(set(found)) == len(found)
    shala_kinds = {N.ADD_CLASS, N.INVITE_SHALA_STUDENTS}
    for step in steps:
        if step.kind in shala_kinds:
            assert step.shala_id in {s.id for s in owned}
        else:
            assert step.shala_id is None
    if owned or teaches:
        assert N.INVITE_STUDENT not in found
    if not has_days:
        assert N.REMINDER not in found
        assert N.POSITION not in found
