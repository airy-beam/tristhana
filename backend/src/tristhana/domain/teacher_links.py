"""Teacher-student links (ID-04, ADR-0030) and the teacher capability (ID-03).

Being a teacher is derived from having students: no role, no toggle. The links form a graph
(cycles are fine, peers teach each other) and rights are one hop, so nothing here walks it.
`primary` is the code's word; the UI says "Main teacher".
"""

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

MAX_TEACHERS = 20  # per student; soft, a race can overshoot by a few
MAX_STUDENTS = 500  # per teacher
CODE_LENGTH = 16  # letters and digits, ~95 bits: a trailing - or _ can drop out of auto-links
_PAYLOAD = re.compile(rf"t_([A-Za-z0-9]{{{CODE_LENGTH}}})")
_BLANK_LETTERS = "\u115f\u1160\u2800\u3164\uffa0"  # Hangul fillers, braille blank: not C/Z/M


class InviteState(StrEnum):
    OPEN = "open"
    OWN = "own"
    ALREADY = "already"
    FULL = "full"


@dataclass(frozen=True, slots=True)
class Linked:
    """The other person on a link. Their name is all that crosses accounts (Q2)."""

    id: UUID
    name: str | None
    chosen_primary: bool  # always False on a student row: a teacher never learns they're main
    linked_at: datetime


def shown_name(name: str | None) -> str | None:
    """None when a name has nothing to see. Names are self-chosen, and Telegram refuses a
    button of blanks, which would break the other person's list."""
    if name and any(
        c not in _BLANK_LETTERS and unicodedata.category(c)[0] not in "CZM" for c in name
    ):
        return name
    return None


def parse_invite(payload: str | None) -> str | None:
    """The code of a `/start t_<code>` payload, or None for any other payload."""
    match = _PAYLOAD.fullmatch(payload or "")
    return match[1] if match else None


def invite_url(bot_username: str, code: str) -> str:
    return f"https://t.me/{bot_username}?start=t_{code}"


def invite_state(
    me: UUID, teacher_id: UUID, linked: bool, my_teachers: int, their_students: int
) -> InviteState:
    if me == teacher_id:
        return InviteState.OWN
    if linked:
        return InviteState.ALREADY
    if my_teachers >= MAX_TEACHERS or their_students >= MAX_STUDENTS:
        return InviteState.FULL
    return InviteState.OPEN


def effective_primary(teachers: Sequence[Linked]) -> UUID | None:
    """The chosen main teacher, else the oldest link. Worked out at read time, so a main
    teacher leaving (or deleting their account) needs no promotion write."""
    if not teachers:
        return None
    chosen = next((t for t in teachers if t.chosen_primary), None)
    return (chosen or min(teachers, key=lambda t: (t.linked_at, t.id))).id


def next_primary(teachers: Sequence[Linked], removing: UUID) -> UUID | None:
    """Who takes over if `removing` goes; None when the main teacher doesn't change."""
    if effective_primary(teachers) != removing:
        return None
    return effective_primary([t for t in teachers if t.id != removing])


def teaches(student_count: int) -> bool:
    """ID-03. SC-01 adds teaching at a shala as a second source."""
    return student_count > 0
