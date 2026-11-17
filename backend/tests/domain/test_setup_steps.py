"""UI-06 stage 4 (spec §5, Q340): a shala's setup list, and the Today card built on the same
rule so the two cannot disagree. Pure: three counts in, the steps still due out."""

from dataclasses import replace
from datetime import UTC, date, datetime
from uuid import UUID

import pytest

from tristhana.domain.accounts import Account
from tristhana.domain.journey import (
    JourneyFacts,
    NextStep,
    OwnedShala,
    SetupStep,
    Step,
    next_steps,
    setup_steps,
)

S = SetupStep
TODAY = date(2026, 11, 16)
OWNER = Account(
    id=UUID(int=1),
    display_name="Anna",
    locale="en",
    timezone="Asia/Almaty",
    last_seen_at=datetime(2026, 11, 16, tzinfo=UTC),
)
SHALA = UUID(int=31)


def test_the_list_order_is_the_enums_order() -> None:
    assert list(SetupStep) == [S.ADD_CLASS, S.INVITE_STUDENTS, S.INVITE_STAFF]
    assert [s.value for s in SetupStep] == ["add_class", "invite_students", "invite_staff"]


@pytest.mark.parametrize(
    ("classes", "students", "staff", "due"),
    [
        (0, 0, 1, [S.ADD_CLASS, S.INVITE_STUDENTS, S.INVITE_STAFF]),  # a new shala
        (1, 0, 1, [S.INVITE_STUDENTS, S.INVITE_STAFF]),
        (0, 1, 1, [S.ADD_CLASS, S.INVITE_STAFF]),  # students came before the first class
        (1, 1, 1, [S.INVITE_STAFF]),  # the optional step alone (Q340)
        (0, 0, 2, [S.ADD_CLASS, S.INVITE_STUDENTS]),
        (1, 0, 2, [S.INVITE_STUDENTS]),
        (0, 1, 2, [S.ADD_CLASS]),
        (1, 1, 2, []),  # set up: the list leaves
    ],
)
def test_each_step_is_due_until_its_own_data_exists(
    classes: int, students: int, staff: int, due: list[SetupStep]
) -> None:
    assert list(setup_steps(classes, students, staff)) == due


def test_more_of_anything_changes_nothing() -> None:
    assert setup_steps(12, 300, 9) == ()
    assert setup_steps(40, 0, 30) == (S.INVITE_STUDENTS,)


def test_a_step_done_comes_back_when_its_data_goes() -> None:
    """Nothing is stored: the last class deleted, the list asks for a class again."""
    assert setup_steps(0, 5, 3) == (S.ADD_CLASS,)


# The Today card reads the same rule

_CARD = {S.ADD_CLASS: NextStep.ADD_CLASS, S.INVITE_STUDENTS: NextStep.INVITE_SHALA_STUDENTS}


@pytest.mark.parametrize("classes", [0, 1, 3])
@pytest.mark.parametrize("students", [0, 1, 40])
@pytest.mark.parametrize("staff", [1, 2])
def test_the_today_card_is_the_lists_first_step(classes: int, students: int, staff: int) -> None:
    facts = JourneyFacts(owned=(OwnedShala(SHALA, classes, students),))

    card = next_steps(OWNER, facts, TODAY)

    first = next(iter(setup_steps(classes, students, staff)), None)
    expected = _CARD.get(first) if first is not None else None
    assert card == (() if expected is None else (Step(expected, SHALA),))


def test_inviting_teachers_is_never_a_today_card() -> None:
    """The optional third step lives on the shala's own list only."""
    facts = JourneyFacts(has_days=True, owned=(OwnedShala(SHALA, classes=2, students=3),))

    kinds = [s.kind for s in next_steps(replace(OWNER, teaches=True), facts, TODAY)]

    assert kinds == [NextStep.REMINDER, NextStep.POSITION]
