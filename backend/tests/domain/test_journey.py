"""UI-06 (spec §2 M0, §3; Q310): who meets the front door, and what the Menu holds. Pure:
everything comes from the loaded account, so neither needs a read."""

from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

import pytest

from tristhana.domain.accounts import Account
from tristhana.domain.days import DayStatus
from tristhana.domain.journey import OTHER_REASONS, MenuItem, front_door, menu_for
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
