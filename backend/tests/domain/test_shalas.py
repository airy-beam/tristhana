"""Shalas, the pure rules (SC-01 spec §3, ADR-0033): the role set and the numbers, the `h_` and
`hs_` payloads, name cleaning, the join states, who may grant which role, "teaches at a
shala" (ID-03), staff-invite expiry, the main-shala order and every policy as a role by action
matrix. Non-members are None: the use cases turn that into `NotFound`, never `NotAllowed`."""

import itertools
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from tristhana.application.policies import (
    can_delete_shala,
    can_edit_shala,
    can_invite_staff,
    can_remove_staff,
    can_remove_student,
    can_rotate_join_link,
    can_set_roles,
    can_show_join_link,
    can_view_shala,
    can_view_shala_students,
)
from tristhana.domain.moon import ShalaMoon
from tristhana.domain.shalas import (
    CODE_LENGTH,
    MAX_OWNED,
    MAX_PENDING_STAFF_INVITES,
    MAX_STAFF,
    MAX_STAFF_OF,
    MAX_STUDENT_OF,
    MAX_STUDENTS,
    NAME_MAX,
    STAFF_INVITE_TTL,
    JoinState,
    Membership,
    ShalaInvite,
    ShalaRole,
    grantable,
    invite_expired,
    join_state,
    main_shala,
    normalize_shala_name,
    parse_shala_invite,
    shala_join_url,
    staff_invite_url,
    teaches_at_shala,
)

SHALA = UUID(int=7)
CODE = "aB3dE6gH9jK2mN5p"
T0 = datetime(2026, 11, 7, 6, 0, tzinfo=UTC)
ADMIN, TEACHER, ASSISTANT, OFFICE = (
    ShalaRole.ADMIN,
    ShalaRole.TEACHER,
    ShalaRole.ASSISTANT,
    ShalaRole.OFFICE,
)
ALL_ROLES = frozenset(ShalaRole)
NO_ROLES = frozenset[ShalaRole]()


def _staff(*roles: ShalaRole, owner: bool = False) -> Membership:
    return Membership(SHALA, owner, frozenset(roles), False)


OWNER = _staff(owner=True)  # the owner's row may hold no role at all
OWNER_TEACHER = _staff(TEACHER, owner=True)
AN_ADMIN = _staff(ADMIN)
A_TEACHER = _staff(TEACHER)
AN_ASSISTANT = _staff(ASSISTANT)
AN_OFFICE = _staff(OFFICE)
NO_ROLE = _staff()  # staff whose roles were all taken away
A_STUDENT = Membership(SHALA, False, NO_ROLES, True)
NOBODY = None  # not a member


def test_the_spec_numbers() -> None:
    assert (MAX_OWNED, MAX_STAFF, MAX_STUDENTS, MAX_STAFF_OF, MAX_STUDENT_OF) == (
        3,
        30,
        1000,
        10,
        5,
    )
    assert MAX_PENDING_STAFF_INVITES == 10
    assert timedelta(days=7) == STAFF_INVITE_TTL
    assert (NAME_MAX, CODE_LENGTH) == (64, 16)


def test_owner_is_not_a_role_value() -> None:
    """Exactly one owner, by construction: `shala.owner_id`, never a value in `roles`."""
    assert {r.value for r in ShalaRole} == {"admin", "teacher", "assistant", "office"}


def test_staff_and_student_are_the_two_sides_of_a_membership() -> None:
    assert OWNER.staff is True
    assert A_TEACHER.staff is True
    assert A_STUDENT.staff is False


# The payloads


@pytest.mark.parametrize(("prefix", "staff"), [("h_", False), ("hs_", True)])
def test_parse_shala_invite_reads_both_kinds(prefix: str, staff: bool) -> None:
    assert parse_shala_invite(f"{prefix}{CODE}") == ShalaInvite(CODE, staff)


@pytest.mark.parametrize("length", [1, 15, 17, 64])
@pytest.mark.parametrize("prefix", ["h_", "hs_"])
def test_parse_shala_invite_rejects_a_wrong_length(prefix: str, length: int) -> None:
    assert parse_shala_invite(prefix + "a" * length) is None


@pytest.mark.parametrize(
    "payload",
    [
        None,
        "",
        "h_",
        "hs_",
        f"t_{CODE}",  # a teacher invite stays the teacher-link parser's
        f"H_{CODE}",
        f"hs{CODE}",
        f"h-{CODE}",
        f" h_{CODE}",
        f"h_{CODE}\n",
        f"hh_{CODE}",
        "h_aB3dE6gH9jK2mN5-",
        "h_абвгдежзийклмноп",
    ],
)
def test_parse_shala_invite_rejects_anything_else(payload: str | None) -> None:
    assert parse_shala_invite(payload) is None


def test_the_teacher_link_parser_is_untouched_by_shala_payloads() -> None:
    from tristhana.domain.teacher_links import parse_invite

    assert parse_invite(f"h_{CODE}") is None
    assert parse_invite(f"hs_{CODE}") is None
    assert parse_invite(f"t_{CODE}") == CODE


def test_the_urls_are_bot_deep_links() -> None:
    assert shala_join_url("tristhana_bot", CODE) == f"https://t.me/tristhana_bot?start=h_{CODE}"
    assert staff_invite_url("tristhana_bot", CODE) == f"https://t.me/tristhana_bot?start=hs_{CODE}"


def test_every_payload_fits_telegrams_start_parameter() -> None:
    """`start` takes at most 64 characters of [A-Za-z0-9_-]."""
    assert len(f"hs_{CODE}") <= 64


# Names


@pytest.mark.parametrize(
    ("raw", "clean"),
    [
        ("Ashtanga Almaty", "Ashtanga Almaty"),
        ("  Ashtanga   Almaty  ", "Ashtanga Almaty"),
        ("Ashtanga\nAlmaty", "Ashtanga Almaty"),
        ("Ashtanga‮Almaty", "AshtangaAlmaty"),  # a bidi control could reorder the card
        ("Шала Йоги", "Шала Йоги"),
        ("x" * 70, "x" * NAME_MAX),
        ("   ", None),
        ("", None),
        (None, None),
    ],
)
def test_names_are_cleaned_like_display_names(raw: str | None, clean: str | None) -> None:
    assert normalize_shala_name(raw) == clean


def test_a_name_matches_display_name_cleaning_exactly() -> None:
    from tristhana.domain.accounts import normalize_display_name

    for raw in ["  a\tb  ", "⁦x⁩", "y" * 80, "\u0000z"]:
        assert normalize_shala_name(raw) == normalize_display_name(raw)


# Join states (a student's /start h_)


@pytest.mark.parametrize(
    ("membership", "students", "mine", "state"),
    [
        (None, 0, 0, JoinState.OPEN),
        (None, MAX_STUDENTS - 1, MAX_STUDENT_OF - 1, JoinState.OPEN),
        (A_STUDENT, 10, 1, JoinState.ALREADY),
        (A_TEACHER, 10, 0, JoinState.STAFF),
        (OWNER, 10, 0, JoinState.STAFF),
        (None, MAX_STUDENTS, 0, JoinState.FULL),
        (None, 0, MAX_STUDENT_OF, JoinState.FULL),
        # Membership wins over a cap: someone already in sees that, not "full".
        (A_STUDENT, MAX_STUDENTS, MAX_STUDENT_OF, JoinState.ALREADY),
        (A_TEACHER, MAX_STUDENTS, MAX_STUDENT_OF, JoinState.STAFF),
    ],
)
def test_join_state(
    membership: Membership | None, students: int, mine: int, state: JoinState
) -> None:
    assert join_state(membership, students, mine) is state


# Grants


@pytest.mark.parametrize(
    ("actor", "roles"),
    [
        (OWNER, ALL_ROLES),
        (OWNER_TEACHER, ALL_ROLES),
        (AN_ADMIN, frozenset({TEACHER, ASSISTANT, OFFICE})),
        (_staff(ADMIN, TEACHER), frozenset({TEACHER, ASSISTANT, OFFICE})),
        (A_TEACHER, NO_ROLES),
        (AN_ASSISTANT, NO_ROLES),
        (AN_OFFICE, NO_ROLES),
        (NO_ROLE, NO_ROLES),
        (A_STUDENT, NO_ROLES),
    ],
)
def test_grantable(actor: Membership, roles: frozenset[ShalaRole]) -> None:
    assert grantable(actor) == roles


@pytest.mark.parametrize(
    ("membership", "teaches"),
    [
        (A_TEACHER, True),
        (AN_ASSISTANT, True),
        (_staff(ADMIN, ASSISTANT), True),
        (OWNER_TEACHER, True),
        (OWNER, False),  # an owner who only runs the place
        (AN_ADMIN, False),
        (AN_OFFICE, False),
        (NO_ROLE, False),
        (A_STUDENT, False),
    ],
)
def test_teaches_at_shala_is_teacher_or_assistant(membership: Membership, teaches: bool) -> None:
    assert teaches_at_shala(membership) is teaches


# Staff invite expiry: a UTC instant, valid strictly before it


@pytest.mark.parametrize(
    ("now", "expired"),
    [
        (T0, False),
        (T0 + STAFF_INVITE_TTL - timedelta(microseconds=1), False),
        (T0 + STAFF_INVITE_TTL, True),
        (T0 + STAFF_INVITE_TTL + timedelta(seconds=1), True),
    ],
)
def test_invite_expiry_boundary(now: datetime, expired: bool) -> None:
    assert invite_expired(T0 + STAFF_INVITE_TTL, now) is expired


# The main shala: staff first, then where the main teacher is staff, then the oldest


def _moon(n: int, *, staff: bool = False, teacher_on_staff: bool = False) -> ShalaMoon:
    return ShalaMoon(UUID(int=n), f"S{n}", "almaty", staff, teacher_on_staff)


def test_no_membership_is_no_main_shala() -> None:
    assert main_shala([]) is None


def test_staff_beats_an_older_student_membership() -> None:
    student, staff = _moon(1), _moon(2, staff=True)

    assert main_shala([(student, T0), (staff, T0 + timedelta(days=9))]) == staff


def test_a_shala_where_the_main_teacher_is_staff_beats_an_older_one() -> None:
    """Q108: a student in two shalas, the teacher on the staff of the newer one."""
    older, newer = _moon(1), _moon(2, teacher_on_staff=True)

    assert main_shala([(older, T0), (newer, T0 + timedelta(days=3))]) == newer


def test_otherwise_the_oldest_then_the_id() -> None:
    a, b, c = _moon(3), _moon(1), _moon(2)

    assert main_shala([(a, T0 + timedelta(days=1)), (b, T0 + timedelta(days=2)), (c, T0)]) == c
    assert main_shala([(a, T0), (b, T0), (c, T0)]) == b  # a tie on created_at: the id


def test_among_staff_the_teacher_flag_never_reorders() -> None:
    """Review fix: staff rows are ordered by age alone, like the account load's subquery."""
    old, new = _moon(1, staff=True), _moon(2, staff=True, teacher_on_staff=True)

    assert main_shala([(old, T0), (new, T0 + timedelta(days=1))]) == old


def test_staff_oldest_first_among_staff() -> None:
    old, new = _moon(9, staff=True), _moon(1, staff=True)

    assert main_shala([(new, T0 + timedelta(days=1)), (old, T0)]) == old


# Policies: every role by every action. None = not a member.

_ACTORS: dict[str, Membership | None] = {
    "owner": OWNER,
    "admin": AN_ADMIN,
    "teacher": A_TEACHER,
    "assistant": AN_ASSISTANT,
    "office": AN_OFFICE,
    "no-role": NO_ROLE,
    "student": A_STUDENT,
    "nobody": NOBODY,
}
_STAFF = {"owner", "admin", "teacher", "assistant", "office", "no-role"}
_MATRIX = {
    can_view_shala: _STAFF | {"student"},
    can_view_shala_students: _STAFF,
    can_show_join_link: _STAFF,
    can_edit_shala: {"owner", "admin"},
    can_rotate_join_link: {"owner", "admin"},
    can_delete_shala: {"owner"},
}


@pytest.mark.parametrize(
    ("policy", "actor"),
    list(itertools.product(_MATRIX, _ACTORS)),
    ids=lambda v: getattr(v, "__name__", v),
)
def test_the_read_and_manage_policies(policy: object, actor: str) -> None:
    allowed = actor in _MATRIX[policy]  # type: ignore[index]

    assert policy(_ACTORS[actor]) is allowed  # type: ignore[operator]


@pytest.mark.parametrize(("actor", "role"), list(itertools.product(_ACTORS, ShalaRole)))
def test_can_invite_staff_is_grantable(actor: str, role: ShalaRole) -> None:
    membership = _ACTORS[actor]
    expected = membership is not None and role in grantable(membership)

    assert can_invite_staff(membership, role) is expected


def test_only_the_owner_invites_a_manager() -> None:
    assert can_invite_staff(OWNER, ADMIN)
    assert not can_invite_staff(AN_ADMIN, ADMIN)
    assert can_invite_staff(AN_ADMIN, TEACHER)


@pytest.mark.parametrize(
    ("actor", "target", "roles", "allowed"),
    [
        (OWNER, A_TEACHER, frozenset({TEACHER, ADMIN}), True),
        (OWNER, AN_ADMIN, frozenset({TEACHER}), True),  # the owner can demote a manager
        (OWNER, A_TEACHER, NO_ROLES, True),  # staff with no role stays staff
        (AN_ADMIN, A_TEACHER, frozenset({TEACHER, ASSISTANT}), True),
        (AN_ADMIN, AN_OFFICE, frozenset({OFFICE, TEACHER}), True),
        (AN_ADMIN, A_TEACHER, frozenset({ADMIN}), False),  # admins are made by the owner
        (AN_ADMIN, _staff(ADMIN), frozenset({TEACHER}), False),  # admin can't touch admin
        (AN_ADMIN, _staff(ADMIN), frozenset({ADMIN, TEACHER}), False),
        (AN_ADMIN, OWNER, frozenset({TEACHER}), False),  # never on the owner
        (_staff(ADMIN, TEACHER), OWNER_TEACHER, NO_ROLES, False),
        (A_TEACHER, AN_ASSISTANT, frozenset({TEACHER}), False),
        (AN_OFFICE, A_TEACHER, frozenset({OFFICE}), False),
        (NO_ROLE, A_TEACHER, NO_ROLES, False),
        (OWNER, A_STUDENT, frozenset({TEACHER}), False),  # a student becomes staff by a link
        (A_STUDENT, A_TEACHER, NO_ROLES, False),
        (NOBODY, A_TEACHER, frozenset({TEACHER}), False),
    ],
)
def test_can_set_roles(
    actor: Membership | None, target: Membership, roles: frozenset[ShalaRole], allowed: bool
) -> None:
    assert can_set_roles(actor, target, roles) is allowed


@pytest.mark.parametrize(
    ("actor", "target", "own", "allowed"),
    [
        # The owner removes anyone else; an admin removes non-admins.
        (OWNER, AN_ADMIN, False, True),
        (OWNER, A_TEACHER, False, True),
        (OWNER, NO_ROLE, False, True),
        (AN_ADMIN, A_TEACHER, False, True),
        (AN_ADMIN, AN_OFFICE, False, True),
        (AN_ADMIN, _staff(ADMIN), False, False),
        (AN_ADMIN, OWNER, False, False),
        (A_TEACHER, AN_ASSISTANT, False, False),
        (AN_OFFICE, A_TEACHER, False, False),  # office removes students, not staff
        (A_STUDENT, A_TEACHER, False, False),
        (NOBODY, A_TEACHER, False, False),
        # Anyone leaves, except the owner (Q102).
        (A_TEACHER, A_TEACHER, True, True),
        (AN_ADMIN, AN_ADMIN, True, True),
        (NO_ROLE, NO_ROLE, True, True),
        (OWNER, OWNER, True, False),
        (OWNER_TEACHER, OWNER_TEACHER, True, False),
    ],
)
def test_can_remove_staff(
    actor: Membership | None, target: Membership, own: bool, allowed: bool
) -> None:
    assert can_remove_staff(actor, target, own=own) is allowed


@pytest.mark.parametrize(
    ("actor", "own", "allowed"),
    [
        (OWNER, False, True),
        (AN_ADMIN, False, True),
        (AN_OFFICE, False, True),
        (A_TEACHER, False, False),
        (AN_ASSISTANT, False, False),
        (NO_ROLE, False, False),
        (A_STUDENT, False, False),  # a student never removes another student
        (A_STUDENT, True, True),  # leaving
        (NOBODY, False, False),
        (NOBODY, True, False),
    ],
)
def test_can_remove_student(actor: Membership | None, own: bool, allowed: bool) -> None:
    assert can_remove_student(actor, own=own) is allowed
