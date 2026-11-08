"""Shalas (SC-01, ADR-0033). No exception here carries a code: a code must never reach a log.

Every guarded write reads the caller's membership in the same statement (`Guarded`): `me`
None = not a member, nothing written (`NotFound`); `done` False = the policy said no, nothing
written (`NotAllowed`). The SQL guard mirrors `application/policies.py`.
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol
from uuid import UUID

from tristhana.domain.classes import MoonPolicy
from tristhana.domain.locale import Locale
from tristhana.domain.moon import City, MoonFollow
from tristhana.domain.shalas import JoinState, Membership, ShalaPatch, ShalaRole


class CapReached(Exception):
    """A cap of Q101: owned shalas, staff memberships or pending staff links."""


@dataclass(frozen=True, slots=True)
class ShalaCaps:
    owned: int
    staff: int
    students: int
    staff_of: int
    student_of: int
    pending_invites: int


@dataclass(frozen=True, slots=True)
class NewShala:
    name: str
    city: str
    online: bool
    roles: frozenset[ShalaRole]  # the owner's own
    join_code: str


@dataclass(frozen=True, slots=True)
class StaffMember:
    id: UUID
    name: str | None
    owner: bool
    roles: frozenset[ShalaRole]


@dataclass(frozen=True, slots=True)
class ShalaCard:
    """What a member sees. `students_total` None: hidden from the caller (a student)."""

    id: UUID
    name: str
    city: str
    moon_city: str | None  # None = same as the city
    online: bool
    owner_id: UUID
    staff: tuple[StaffMember, ...]  # oldest first, at most MAX_STAFF
    students_total: int | None
    me: Membership
    days_off: frozenset[int] | None = None  # SC-02: None = not set
    moon_policy: MoonPolicy = MoonPolicy.CLOSED  # SC-02 (Q117)


@dataclass(frozen=True, slots=True)
class MyShala:
    id: UUID
    name: str
    city: str
    online: bool
    me: Membership


@dataclass(frozen=True, slots=True)
class ShalaStudent:
    id: UUID
    name: str | None


@dataclass(frozen=True, slots=True)
class StudentsPage:
    students: tuple[ShalaStudent, ...]
    total: int
    me: Membership | None = None  # the caller's, set by `GetShalaStudents`


@dataclass(frozen=True, slots=True)
class MemberLookup:
    """One person in a shala, with the card. `found` False: not in it (or a student the
    caller may not see)."""

    card: ShalaCard
    found: bool
    name: str | None = None
    staff: bool = False


@dataclass(frozen=True, slots=True)
class ShalaPreview:
    """A student link's preview: the shala alone, never a person."""

    shala_id: UUID
    name: str
    city: str
    me: Membership | None
    students: int
    my_student_of: int


@dataclass(frozen=True, slots=True)
class StaffPreview:
    """A staff link's preview: the shala, the role and who sent it."""

    shala_id: UUID
    shala_name: str
    city: str
    role: ShalaRole
    inviter_name: str | None
    me: Membership | None


@dataclass(frozen=True, slots=True)
class Joined:
    """`created` False: already a member (`state`) or a cap (FULL, no card)."""

    created: bool
    state: JoinState
    card: ShalaCard | None
    moon: MoonFollow | None = None  # set by `JoinShala`: the caller's new city, if it moved


@dataclass(frozen=True, slots=True)
class StaffAccepted:
    created: bool
    state: JoinState
    card: ShalaCard | None
    role: ShalaRole
    was_student: bool
    inviter_telegram_id: str | None
    inviter_locale: Locale
    moon: MoonFollow | None = None  # set by `AcceptStaffInvite`
    keep: City | None = None  # Q98: the shala city a never-chose teacher can keep as their own


@dataclass(frozen=True, slots=True)
class StaffInvite:
    code: str
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class Guarded[T]:
    me: Membership | None
    done: bool
    value: T | None = None


class ShalaRepository(Protocol):
    async def create(
        self, me: UUID, new: NewShala, caps: ShalaCaps, joined_on: date
    ) -> ShalaCard | None:
        """The shala and the owner's staff row. None: a cap (owned or staff memberships)."""
        ...

    async def mine(self, me: UUID) -> tuple[MyShala, ...]:
        """Staff memberships first, then student ones, each oldest first."""
        ...

    async def card(self, shala: UUID, me: UUID) -> ShalaCard | None:
        """None: no such shala, or not a member."""
        ...

    async def update(self, shala: UUID, me: UUID, patch: ShalaPatch) -> Guarded[ShalaCard]: ...

    async def delete(self, shala: UUID, me: UUID) -> Guarded[None]: ...

    async def students(
        self, shala: UUID, me: UUID, offset: int, limit: int
    ) -> Guarded[StudentsPage]: ...

    async def member(self, shala: UUID, me: UUID, target: UUID) -> MemberLookup | None:
        """One statement: the card and one person's side. None: not a member."""
        ...

    async def preview(self, code: str, me: UUID) -> ShalaPreview | None:
        """None: no such join code (or it was rotated)."""
        ...

    async def preview_staff(self, code: str, me: UUID) -> StaffPreview | None:
        """None: no such staff code, used or expired."""
        ...

    async def join(self, code: str, me: UUID, caps: ShalaCaps, joined_on: date) -> Joined | None:
        """One statement. None: no such join code."""
        ...

    async def invite_staff(
        self,
        shala: UUID,
        me: UUID,
        role: ShalaRole,
        code: str,
        expires_at: datetime,
        caps: ShalaCaps,
    ) -> Guarded[StaffInvite]:
        """`done` with no value: allowed, but the pending cap was reached."""
        ...

    async def accept_staff(
        self, code: str, me: UUID, caps: ShalaCaps, joined_on: date
    ) -> StaffAccepted | None:
        """One statement, `DELETE … RETURNING` the unexpired invite, so a link works once
        under a double tap. A student of the shala becomes staff. None: used or expired."""
        ...

    async def set_roles(
        self, shala: UUID, me: UUID, target: UUID, roles: frozenset[ShalaRole]
    ) -> Guarded[ShalaCard]: ...

    async def remove_staff(self, shala: UUID, me: UUID, target: UUID) -> Guarded[None]:
        """Idempotent: someone already gone is done."""
        ...

    async def remove_student(self, shala: UUID, me: UUID, target: UUID) -> Guarded[None]:
        """Idempotent: someone already gone is done."""
        ...

    async def join_link(self, shala: UUID, me: UUID) -> Guarded[str]: ...

    async def rotate_join(self, shala: UUID, me: UUID, code: str) -> Guarded[str]:
        """The old link and QR die; members stay."""
        ...

    async def prune_invites(self, now: datetime) -> int:
        """Expired staff links (the tick's pruning step)."""
        ...
