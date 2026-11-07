"""Shalas (SC-01, ADR-0033): a place with staff in roles and students who joined by its link.

The owner is `shala.owner_id`, never a role value, so there is exactly one. Staff and student
are exclusive within a shala (Q107). A membership never grants access to anyone's log.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID

from tristhana.domain.accounts import normalize_display_name
from tristhana.domain.moon import ShalaMoon
from tristhana.domain.teacher_links import CODE_LENGTH

# Q101: soft caps, like ID-04's (a race can overshoot by a few).
MAX_OWNED = 3  # shalas per owner
MAX_STAFF = 30  # per shala
MAX_STUDENTS = 1000  # per shala
MAX_STAFF_OF = 10  # staff memberships per person
MAX_STUDENT_OF = 5  # student memberships per person
MAX_PENDING_STAFF_INVITES = 10  # unexpired staff links per shala
STAFF_INVITE_TTL = timedelta(days=7)
NAME_MAX = 64

_PAYLOAD = re.compile(rf"(hs?)_([A-Za-z0-9]{{{CODE_LENGTH}}})")


class ShalaRole(StrEnum):
    ADMIN = "admin"  # UI "Manager" / «Управляющий»
    TEACHER = "teacher"
    ASSISTANT = "assistant"
    OFFICE = "office"  # UI "Front desk" / «Администратор» (Q104)


class JoinState(StrEnum):
    OPEN = "open"
    ALREADY = "already"
    STAFF = "staff"
    FULL = "full"


class InvalidShalaName(ValueError):
    pass


class _Keep:
    """A patch field that was not sent: leave it as it is."""

    def __repr__(self) -> str:
        return "KEEP"


KEEP = _Keep()


@dataclass(frozen=True, slots=True)
class ShalaPatch:
    """Fields to change; KEEP = not sent. `moon_city` None = same as the city."""

    name: str | _Keep = KEEP
    city: str | _Keep = KEEP
    online: bool | _Keep = KEEP
    moon_city: str | _Keep | None = KEEP


@dataclass(frozen=True, slots=True)
class Membership:
    """The caller's side of one shala. A student has no roles; an owner may have none."""

    shala_id: UUID
    owner: bool
    roles: frozenset[ShalaRole]
    student: bool

    @property
    def staff(self) -> bool:
        return not self.student


@dataclass(frozen=True, slots=True)
class ShalaInvite:
    """A `/start` payload: `h_<code>` joins as a student, `hs_<code>` accepts a staff link."""

    code: str
    staff: bool


def parse_shala_invite(payload: str | None) -> ShalaInvite | None:
    match = _PAYLOAD.fullmatch(payload or "")
    return ShalaInvite(match[2], match[1] == "hs") if match else None


def shala_join_url(bot_username: str, code: str) -> str:
    return f"https://t.me/{bot_username}?start=h_{code}"


def staff_invite_url(bot_username: str, code: str) -> str:
    return f"https://t.me/{bot_username}?start=hs_{code}"


def normalize_shala_name(raw: str | None) -> str | None:
    """Cleaned exactly like a display name (same length too); blank becomes None."""
    return normalize_display_name(raw)


def join_state(membership: Membership | None, students: int, my_student_of: int) -> JoinState:
    """A membership wins over a cap: someone already in sees that, not "full"."""
    if membership is not None:
        return JoinState.STAFF if membership.staff else JoinState.ALREADY
    if students >= MAX_STUDENTS or my_student_of >= MAX_STUDENT_OF:
        return JoinState.FULL
    return JoinState.OPEN


def grantable(actor: Membership) -> frozenset[ShalaRole]:
    """The roles this member may give: the owner all; a manager all but manager."""
    if actor.owner:
        return frozenset(ShalaRole)
    if actor.staff and ShalaRole.ADMIN in actor.roles:
        return frozenset(ShalaRole) - {ShalaRole.ADMIN}
    return frozenset()


def teaches_at_shala(membership: Membership) -> bool:
    """ID-03: teaching at a shala, the second source of the teacher capability."""
    return membership.staff and bool(membership.roles & {ShalaRole.TEACHER, ShalaRole.ASSISTANT})


def invite_expired(expires_at: datetime, now: datetime) -> bool:
    return now >= expires_at


def main_shala(memberships: Sequence[tuple[ShalaMoon, datetime]]) -> ShalaMoon | None:
    """Staff first, then a student shala where the main teacher is staff (Q108), then the
    oldest, then the id. Among staff rows the teacher doesn't count. The account load's
    subquery orders the same way."""
    if not memberships:
        return None
    return min(
        memberships,
        key=lambda m: (
            not m[0].staff,
            not m[0].staff and not m[0].teacher_on_staff,
            m[1],
            m[0].id,
        ),
    )[0]
