"""Teacher links, the pure rules (ID-04, spec §3, ADR-0030): the `t_<code>` payload, the invite
states, who is the main teacher at read time, who takes over, and the derived "teaches"."""

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from tristhana.domain.teacher_links import (
    CODE_LENGTH,
    MAX_STUDENTS,
    MAX_TEACHERS,
    InviteState,
    Linked,
    effective_primary,
    invite_state,
    invite_url,
    next_primary,
    parse_invite,
    shown_name,
    teaches,
)

ME, ANNA, BORIS, CLARA = UUID(int=1), UUID(int=2), UUID(int=3), UUID(int=4)
T0 = datetime(2026, 11, 1, 6, 0, tzinfo=UTC)
CODE = "aB3dE6gH9jK2mN5p"


def _linked(id_: UUID, days: int = 0, chosen: bool = False) -> Linked:
    return Linked(id_, None, chosen, T0 + timedelta(days=days))


def _teachers(*rows: Linked) -> Sequence[Linked]:
    return rows


def test_the_spec_numbers() -> None:
    assert (MAX_TEACHERS, MAX_STUDENTS, CODE_LENGTH) == (20, 500, 16)


@pytest.mark.parametrize("code", [CODE, "A" * 16, "0123456789abcdef"])
def test_parse_invite_accepts_t_and_16_alphanumerics(code: str) -> None:
    assert parse_invite(f"t_{code}") == code


@pytest.mark.parametrize("prefix", ["s_", "T_", "t-", "t", "", "tt_", " t_"])
def test_parse_invite_rejects_a_wrong_prefix(prefix: str) -> None:
    assert parse_invite(f"{prefix}{CODE}") is None


@pytest.mark.parametrize("length", [1, 15, 17, 64])
def test_parse_invite_rejects_a_wrong_length(length: int) -> None:
    assert parse_invite("t_" + "a" * length) is None


@pytest.mark.parametrize(
    "code",
    [
        "aB3dE6gH9jK2mN5-",  # a trailing - or _ can drop out of auto-linked text
        "aB3dE6gH9jK2mN5_",
        "aB3dE6gH 9jK2mN5",
        "абвгдежзийклмноп",  # letters, but not ours: the DB CHECK is ASCII
        "١٢٣٤٥٦٧٨٩٠١٢٣٤٥٦",  # digits, likewise
        "aB3dE6gH9jK2mN5\n",  # `$` in a regex would let this through
    ],
)
def test_parse_invite_rejects_a_wrong_alphabet(code: str) -> None:
    assert parse_invite(f"t_{code}") is None


@pytest.mark.parametrize("payload", [None, "", "t_"])
def test_parse_invite_rejects_nothing_at_all(payload: str | None) -> None:
    assert parse_invite(payload) is None


def test_invite_url_is_the_bot_deep_link() -> None:
    assert invite_url("tristhana_bot", CODE) == f"https://t.me/tristhana_bot?start=t_{CODE}"


def test_invite_state_open() -> None:
    assert invite_state(ME, ANNA, False, 0, 0) is InviteState.OPEN
    assert invite_state(ME, ANNA, False, MAX_TEACHERS - 1, MAX_STUDENTS - 1) is InviteState.OPEN


def test_invite_state_own() -> None:
    assert invite_state(ME, ME, False, 0, 0) is InviteState.OWN


def test_invite_state_already() -> None:
    assert invite_state(ME, ANNA, True, 1, 1) is InviteState.ALREADY


@pytest.mark.parametrize(
    ("my_teachers", "their_students"),
    [(MAX_TEACHERS, 0), (0, MAX_STUDENTS), (MAX_TEACHERS + 3, MAX_STUDENTS + 3)],
)
def test_invite_state_full_on_either_cap(my_teachers: int, their_students: int) -> None:
    assert invite_state(ME, ANNA, False, my_teachers, their_students) is InviteState.FULL


def test_someone_already_on_a_full_list_is_told_already_not_full() -> None:
    assert invite_state(ME, ANNA, True, MAX_TEACHERS, MAX_STUDENTS) is InviteState.ALREADY


def test_own_code_is_own_whatever_the_caps_say() -> None:
    assert invite_state(ME, ME, False, MAX_TEACHERS, MAX_STUDENTS) is InviteState.OWN


def test_effective_primary_of_no_teachers_is_none() -> None:
    assert effective_primary([]) is None


def test_effective_primary_defaults_to_the_oldest_link() -> None:
    assert effective_primary(_teachers(_linked(ANNA, 2), _linked(BORIS, 1))) == BORIS


def test_a_chosen_main_teacher_wins_over_the_oldest() -> None:
    assert effective_primary(_teachers(_linked(ANNA, 0), _linked(BORIS, 1, chosen=True))) == BORIS


def test_once_the_chosen_one_is_gone_the_oldest_is_main_again() -> None:
    rows = _teachers(_linked(ANNA, 3), _linked(BORIS, 1, chosen=True), _linked(CLARA, 2))

    remaining = [r for r in rows if r.id != BORIS]

    assert effective_primary(remaining) == CLARA


def test_a_tie_on_the_instant_falls_to_the_lowest_teacher_id() -> None:
    assert effective_primary(_teachers(_linked(CLARA), _linked(ANNA), _linked(BORIS))) == ANNA


def test_removing_a_teacher_who_isnt_main_changes_nothing() -> None:
    rows = _teachers(_linked(ANNA, 0), _linked(BORIS, 1))

    assert next_primary(rows, BORIS) is None


def test_removing_the_main_teacher_names_the_next_oldest() -> None:
    rows = _teachers(_linked(ANNA, 3), _linked(BORIS, 1, chosen=True), _linked(CLARA, 2))

    assert next_primary(rows, BORIS) == CLARA


def test_removing_the_automatic_main_teacher_names_the_next_oldest() -> None:
    rows = _teachers(_linked(ANNA, 0), _linked(BORIS, 2), _linked(CLARA, 1))

    assert next_primary(rows, ANNA) == CLARA


def test_removing_the_last_teacher_names_no_one() -> None:
    assert next_primary(_teachers(_linked(ANNA)), ANNA) is None


def test_teaches_means_having_a_student() -> None:
    assert teaches(0) is False
    assert teaches(1) is True


def test_a_cycle_is_valid() -> None:
    """Peers teach each other: A is B's teacher, and B's invite still opens for A. Nothing
    walks the graph, so the function has no way to refuse it."""
    a_on_bs_list = invite_state(BORIS, ANNA, False, 0, 0)
    b_on_as_list = invite_state(ANNA, BORIS, False, 0, 1)

    assert (a_on_bs_list, b_on_as_list) == (InviteState.OPEN, InviteState.OPEN)


@pytest.mark.parametrize("name", ["\u3164", "\u200b\u200b", " \u00a0", "\u2800", ""])
def test_a_name_with_nothing_to_see_is_no_name(name: str) -> None:
    assert shown_name(name) is None


@pytest.mark.parametrize("name", ["Лена", "🌸", "a\u200bb", "李"])
def test_a_visible_name_stays_as_it_is(name: str) -> None:
    assert shown_name(name) == name
