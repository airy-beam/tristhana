"""Who may see and manage a shala's schedule (SC-02 spec §3, Q118, Q121): a role by action
matrix. Any member views; staff see 1:1 classes; the owner, a manager, a teacher and the front
desk manage classes, exceptions, closures and swaps; the day off and the moon policy stay with
`can_edit_shala` (owner, manager). None = not a member (`NotFound` in the use cases)."""

import itertools
from uuid import UUID

import pytest

from tristhana.application.policies import (
    can_edit_shala,
    can_manage_schedule,
    can_view_private_classes,
    can_view_schedule,
)
from tristhana.domain.shalas import Membership, ShalaRole

SHALA = UUID(int=7)


def _staff(*roles: ShalaRole, owner: bool = False) -> Membership:
    return Membership(SHALA, owner, frozenset(roles), False)


_ACTORS: dict[str, Membership | None] = {
    "owner": _staff(owner=True),
    "owner-teacher": _staff(ShalaRole.TEACHER, owner=True),
    "admin": _staff(ShalaRole.ADMIN),
    "teacher": _staff(ShalaRole.TEACHER),
    "assistant": _staff(ShalaRole.ASSISTANT),
    "office": _staff(ShalaRole.OFFICE),
    "assistant-office": _staff(ShalaRole.ASSISTANT, ShalaRole.OFFICE),
    "no-role": _staff(),
    "student": Membership(SHALA, False, frozenset(), True),
    "nobody": None,
}
_STAFF = {
    "owner",
    "owner-teacher",
    "admin",
    "teacher",
    "assistant",
    "office",
    "assistant-office",
    "no-role",
}
_MATRIX = {
    can_view_schedule: _STAFF | {"student"},
    can_view_private_classes: _STAFF,
    can_manage_schedule: {
        "owner",
        "owner-teacher",
        "admin",
        "teacher",
        "office",
        "assistant-office",
    },
    can_edit_shala: {"owner", "owner-teacher", "admin"},  # day off and moon policy
}


@pytest.mark.parametrize(
    ("policy", "actor"),
    list(itertools.product(_MATRIX, _ACTORS)),
    ids=lambda v: getattr(v, "__name__", v),
)
def test_the_schedule_policies(policy: object, actor: str) -> None:
    allowed = actor in _MATRIX[policy]  # type: ignore[index]

    assert policy(_ACTORS[actor]) is allowed  # type: ignore[operator]


def test_an_assistant_views_but_does_not_manage() -> None:
    assistant = _ACTORS["assistant"]

    assert can_view_schedule(assistant)
    assert can_view_private_classes(assistant)
    assert not can_manage_schedule(assistant)
