"""In-memory `ShalaRepository` and the account load with the shala input (SC-01 spec §3).

Its own module (like `teacher_link_fakes.py`) so the existing suites keep collecting before
SC-01 exists: `InMemoryStorage.shalas` loads it on first use.

The port shapes the spec leaves open are assumed here, and are the ones to adjust with the
port (`tristhana.application.ports.shalas`):

- `ShalaCaps(owned, staff, students, staff_of, student_of, pending_invites)`;
- `NewShala(name, city, online, roles, join_code)`;
- `ShalaCard(id, name, city, moon_city, online, owner_id, staff, students_total, me)`,
  `StaffMember(id, name, owner, roles)`, `MyShala(id, name, city, online, me)`,
  `ShalaStudent(id, name)`, `StudentsPage(students, total)`;
- `ShalaPreview(shala_id, name, city, me, students, my_student_of)` (no people);
  `StaffPreview(shala_id, shala_name, city, role, inviter_name, me)`;
- `Joined(created, state, card)`; `StaffAccepted(created, state, card, role, was_student,
  inviter_telegram_id, inviter_locale)`, both with `moon` (and `keep` on the staff side) set
  by the use case;
- `StaffInvite(code, expires_at)`;
- `Guarded(me, done, value)`: one statement reads the caller's membership with the write.
  `me` None = not a member (nothing written, `NotFound`); `done` False = the policy said no
  (nothing written, `NotAllowed`). The SQL guard mirrors `application/policies.py`; this fake
  calls the policies themselves, and `test_db_shalas.py` pins the SQL to the same matrix;
- `ShalaRepository`: `create`, `mine`, `card`, `update`, `delete`, `students`, `preview`,
  `preview_staff`, `join`, `invite_staff`, `accept_staff`, `set_roles`, `remove_staff`,
  `remove_student`, `join_link`, `rotate_join`, `main_of` is test-only;
- `Notifier.tell_staff_joined(recipient, name, shala, role) -> DeliveryResult`;
- `Accepted.teacher_shala: ShalaMoon | None` (ID-04's accept carries the teacher's shala input
  for `_keep_offer`).
"""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field, fields, replace
from datetime import date, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from tests.fakes import FakeNotifier, InMemoryDays, InMemoryStorage
from tests.moon_follow_fakes import (
    FollowingAccounts,
    FollowingExport,
    FollowingLinks,
    FollowingNotifications,
)
from tristhana.application.policies import (
    can_delete_shala,
    can_edit_shala,
    can_invite_staff,
    can_remove_staff,
    can_remove_student,
    can_rotate_join_link,
    can_set_roles,
    can_show_join_link,
    can_view_shala_students,
)
from tristhana.application.ports.notifications import (
    DeliveryResult,
    DeliveryStatus,
    Recipient,
    ReminderCandidate,
)
from tristhana.application.ports.shalas import (
    Guarded,
    Joined,
    MemberLookup,
    MyShala,
    NewShala,
    ShalaCaps,
    ShalaCard,
    ShalaPreview,
    ShalaStudent,
    StaffAccepted,
    StaffInvite,
    StaffMember,
    StaffPreview,
    StudentsPage,
)
from tristhana.application.ports.teacher_links import Accepted, Caps
from tristhana.domain.accounts import Account
from tristhana.domain.moon import ShalaMoon
from tristhana.domain.shalas import (
    MAX_OWNED,
    MAX_PENDING_STAFF_INVITES,
    MAX_STAFF,
    MAX_STAFF_OF,
    MAX_STUDENT_OF,
    MAX_STUDENTS,
    JoinState,
    Membership,
    ShalaRole,
    main_shala,
)

CAPS = ShalaCaps(
    owned=MAX_OWNED,
    staff=MAX_STAFF,
    students=MAX_STUDENTS,
    staff_of=MAX_STAFF_OF,
    student_of=MAX_STUDENT_OF,
    pending_invites=MAX_PENDING_STAFF_INVITES,
)
JOINED_ON = date(2026, 11, 1)


@dataclass
class ShalaRow:
    id: UUID
    name: str
    city: str
    moon_city: str | None
    online: bool
    owner_id: UUID
    join_code: str
    created_at: datetime
    days_off: frozenset[int] | None = None  # SC-02: None = not set
    moon_policy: str = "closed"  # SC-02 (Q117)


@dataclass
class MemberRow:
    roles: frozenset[ShalaRole] | None  # None: a student row
    joined_on: date
    created_at: datetime


@dataclass
class InviteRow:
    shala_id: UUID
    role: ShalaRole
    created_by: UUID
    expires_at: datetime


@dataclass
class InMemoryShalas:
    accounts: FollowingAccounts
    links: FollowingLinks | None = None
    shalas: dict[UUID, ShalaRow] = field(default_factory=dict[UUID, ShalaRow])
    staff: dict[tuple[UUID, UUID], MemberRow] = field(
        default_factory=dict[tuple[UUID, UUID], MemberRow]
    )
    students_rows: dict[tuple[UUID, UUID], MemberRow] = field(
        default_factory=dict[tuple[UUID, UUID], MemberRow]
    )
    invites: dict[str, InviteRow] = field(default_factory=dict[str, InviteRow])
    fail_with: Exception | None = None
    writes: list[str] = field(default_factory=list[str])  # finished writes, in order
    reads: list[str] = field(default_factory=list[str])  # every port call, in order
    # SC-05 (Q186): leaving or a removal deletes the person's attendance at the shala.
    on_leave: list[Callable[[UUID, UUID], None]] = field(
        default_factory=list[Callable[[UUID, UUID], None]]
    )
    _tick: int = 0

    # Seeding (not part of the port).

    def add_shala(
        self,
        owner: UUID,
        name: str = "Ashtanga Almaty",
        city: str = "almaty",
        *,
        moon_city: str | None = None,
        online: bool = False,
        code: str = "J0inC0deJ0inC0de",
        roles: frozenset[ShalaRole] = frozenset({ShalaRole.TEACHER}),
        days_off: frozenset[int] | None = None,
        moon_policy: str = "closed",
    ) -> ShalaRow:
        row = ShalaRow(
            uuid4(),
            name,
            city,
            moon_city,
            online,
            owner,
            code,
            self._next_instant(),
            days_off,
            moon_policy,
        )
        self.shalas[row.id] = row
        self.staff[(row.id, owner)] = MemberRow(roles, JOINED_ON, row.created_at)
        return row

    def add_staff(
        self, shala: UUID, account: UUID, *roles: ShalaRole, at: datetime | None = None
    ) -> None:
        self.students_rows.pop((shala, account), None)
        self.staff[(shala, account)] = MemberRow(
            frozenset(roles), JOINED_ON, at or self._next_instant()
        )

    def add_student(self, shala: UUID, account: UUID, at: datetime | None = None) -> None:
        self.students_rows[(shala, account)] = MemberRow(
            None, JOINED_ON, at or self._next_instant()
        )

    def add_invite(
        self,
        shala: UUID,
        code: str,
        role: ShalaRole = ShalaRole.TEACHER,
        *,
        by: UUID | None = None,
        expires_at: datetime | None = None,
    ) -> None:
        owner = self.shalas[shala].owner_id
        until = expires_at or self.accounts.clock.now() + timedelta(days=7)
        self.invites[code] = InviteRow(shala, role, by or owner, until)

    def membership(self, shala: UUID, account: UUID) -> Membership | None:
        row = self.shalas.get(shala)
        if row is None:
            return None
        if (staff := self.staff.get((shala, account))) is not None:
            return Membership(shala, row.owner_id == account, staff.roles or frozenset(), False)
        if (shala, account) in self.students_rows:
            return Membership(shala, False, frozenset(), True)
        return None

    def staff_of(self, shala: UUID) -> list[UUID]:
        return [a for (s, a), _ in self._by_age(self.staff) if s == shala]

    def students_of(self, shala: UUID) -> list[UUID]:
        return [a for (s, a), _ in self._by_age(self.students_rows) if s == shala]

    def main_of(self, account: UUID) -> ShalaMoon | None:
        """The account load's subquery: `ORDER BY staff DESC, teacher_on_staff DESC,
        created_at, shala_id LIMIT 1`, via the domain's `main_shala`."""
        teacher = self.links.main_of(account) if self.links else None
        options: list[tuple[ShalaMoon, datetime]] = []
        for (shala_id, who), row in self.staff.items():
            if who == account and shala_id in self.shalas:
                options.append((self._moon(shala_id, True, False), row.created_at))
        for (shala_id, who), row in self.students_rows.items():
            if who == account and shala_id in self.shalas:
                on_staff = teacher is not None and (shala_id, teacher.id) in self.staff
                options.append((self._moon(shala_id, False, on_staff), row.created_at))
        return main_shala(options)

    # The port.

    async def create(
        self, me: UUID, new: NewShala, caps: ShalaCaps, joined_on: date
    ) -> ShalaCard | None:
        self._call("create")
        await asyncio.sleep(0)
        owned = [s for s in self.shalas.values() if s.owner_id == me]
        if len(owned) >= caps.owned or len(self._staff_memberships(me)) >= caps.staff_of:
            return None
        row = ShalaRow(
            uuid4(), new.name, new.city, None, new.online, me, new.join_code, self._next_instant()
        )
        self.shalas[row.id] = row
        self.staff[(row.id, me)] = MemberRow(new.roles, joined_on, row.created_at)
        self.writes.append("create")
        return self._card(row.id, me)

    async def mine(self, me: UUID) -> tuple[MyShala, ...]:
        self._call("mine")
        out: list[MyShala] = []
        for shala_id in self._memberships(me):
            row, m = self.shalas[shala_id], self.membership(shala_id, me)
            assert m is not None
            out.append(MyShala(row.id, row.name, row.city, row.online, m))
        return tuple(out)

    async def card(self, shala: UUID, me: UUID) -> ShalaCard | None:
        self._call("card")
        return self._card(shala, me)

    async def update(self, shala: UUID, me: UUID, patch: Any) -> Guarded[ShalaCard]:
        self._call("update")
        m = self.membership(shala, me)
        if m is None or not can_edit_shala(m):
            return Guarded(m, False)
        row = self.shalas[shala]
        for name in ("name", "city", "online", "moon_city", "days_off", "moon_policy"):
            value = getattr(patch, name, "KEEP")  # SC-02's fields exist once it does
            if repr(value) != "KEEP" and value != "KEEP":
                if name == "moon_policy" and value is not None:
                    value = str(value)
                if name == "days_off" and value is not None:
                    value = frozenset(value)
                setattr(row, name, value)
        self.writes.append("update")
        return Guarded(m, True, self._card(shala, me))

    async def delete(self, shala: UUID, me: UUID) -> Guarded[None]:
        self._call("delete")
        m = self.membership(shala, me)
        if m is None or not can_delete_shala(m):
            return Guarded(m, False)
        self._drop(shala)
        self.writes.append("delete")
        return Guarded(m, True)

    async def students(
        self, shala: UUID, me: UUID, offset: int, limit: int
    ) -> Guarded[StudentsPage]:
        self._call("students")
        m = self.membership(shala, me)
        if m is None or not can_view_shala_students(m):
            return Guarded(m, False)
        ids = self.students_of(shala)
        page = tuple(ShalaStudent(a, self._name(a)) for a in ids[offset : offset + limit])
        return Guarded(m, True, StudentsPage(page, len(ids)))

    async def member(self, shala: UUID, me: UUID, target: UUID) -> MemberLookup | None:
        self._call("member")
        card = self._card(shala, me)
        if card is None:
            return None
        t = self.membership(shala, target)
        if t is None:
            return MemberLookup(card, False)
        return MemberLookup(card, True, self._name(target), t.staff)

    async def preview(self, code: str, me: UUID) -> ShalaPreview | None:
        self._call("preview")
        row = self._by_join_code(code)
        if row is None:
            return None
        return ShalaPreview(
            shala_id=row.id,
            name=row.name,
            city=row.city,
            me=self.membership(row.id, me),
            students=len(self.students_of(row.id)),
            my_student_of=len(self._student_memberships(me)),
        )

    async def preview_staff(self, code: str, me: UUID) -> StaffPreview | None:
        self._call("preview_staff")
        invite = self._live_invite(code)
        if invite is None:
            return None
        row = self.shalas[invite.shala_id]
        return StaffPreview(
            shala_id=row.id,
            shala_name=row.name,
            city=row.city,
            role=invite.role,
            inviter_name=self._name(invite.created_by),
            me=self.membership(row.id, me),
        )

    async def join(self, code: str, me: UUID, caps: ShalaCaps, joined_on: date) -> Joined | None:
        self._call("join")
        await asyncio.sleep(0)
        row = self._by_join_code(code)
        if row is None:
            return None
        m = self.membership(row.id, me)
        if m is not None:
            state = JoinState.STAFF if m.staff else JoinState.ALREADY
            return Joined(False, state, self._card(row.id, me))
        if (
            len(self.students_of(row.id)) >= caps.students
            or len(self._student_memberships(me)) >= caps.student_of
        ):
            return Joined(False, JoinState.FULL, None)
        self.students_rows[(row.id, me)] = MemberRow(None, joined_on, self._next_instant())
        self.writes.append("join")
        return Joined(True, JoinState.OPEN, self._card(row.id, me))

    async def invite_staff(
        self,
        shala: UUID,
        me: UUID,
        role: ShalaRole,
        code: str,
        expires_at: datetime,
        caps: ShalaCaps,
    ) -> Guarded[StaffInvite]:
        self._call("invite_staff")
        m = self.membership(shala, me)
        if m is None or not can_invite_staff(m, role):
            return Guarded(m, False)
        live = [i for i in self.invites.values() if i.shala_id == shala and self._live(i)]
        if len(live) >= caps.pending_invites:
            return Guarded(m, True, None)  # allowed, but capped: `CapReached`
        self.invites[code] = InviteRow(shala, role, me, expires_at)
        self.writes.append("invite_staff")
        return Guarded(m, True, StaffInvite(code, expires_at))

    async def accept_staff(
        self, code: str, me: UUID, caps: ShalaCaps, joined_on: date
    ) -> StaffAccepted | None:
        """`DELETE … RETURNING` the unexpired invite: a used or expired code is None."""
        self._call("accept_staff")
        invite = self._live_invite(code)
        await asyncio.sleep(0)  # the round trip: a double tap races here
        if invite is None or self.invites.get(code) is not invite:
            return None
        row = self.shalas[invite.shala_id]
        m = self.membership(row.id, me)
        inviter = self.accounts.accounts.get(invite.created_by)
        base: dict[str, Any] = {
            "role": invite.role,
            "inviter_telegram_id": self._telegram_id(invite.created_by),
            "inviter_locale": inviter.locale if inviter else "en",
        }
        if m is not None and m.staff:
            return StaffAccepted(
                False, JoinState.STAFF, self._card(row.id, me), was_student=False, **base
            )
        if (
            len(self.staff_of(row.id)) >= caps.staff
            or len(self._staff_memberships(me)) >= caps.staff_of
        ):
            return StaffAccepted(False, JoinState.FULL, None, was_student=False, **base)
        del self.invites[code]
        was_student = self.students_rows.pop((row.id, me), None) is not None
        self.staff[(row.id, me)] = MemberRow(
            frozenset({invite.role}), joined_on, self._next_instant()
        )
        self.writes.append("accept_staff")
        return StaffAccepted(
            True, JoinState.OPEN, self._card(row.id, me), was_student=was_student, **base
        )

    async def set_roles(
        self, shala: UUID, me: UUID, target: UUID, roles: frozenset[ShalaRole]
    ) -> Guarded[ShalaCard]:
        self._call("set_roles")
        m, t = self.membership(shala, me), self.membership(shala, target)
        if m is None or t is None or not can_set_roles(m, t, roles):
            return Guarded(m, False)
        self.staff[(shala, target)].roles = roles
        self.writes.append("set_roles")
        return Guarded(m, True, self._card(shala, me))

    async def remove_staff(self, shala: UUID, me: UUID, target: UUID) -> Guarded[None]:
        """Idempotent: someone already gone is done, if the caller could have removed them."""
        self._call("remove_staff")
        await asyncio.sleep(0)
        m, t = self.membership(shala, me), self.membership(shala, target)
        if m is None:
            return Guarded(None, False)
        own = me == target
        if t is None or not t.staff:
            return Guarded(m, own or can_edit_shala(m))
        if not can_remove_staff(m, t, own=own):
            return Guarded(m, False)
        del self.staff[(shala, target)]
        for hook in self.on_leave:
            hook(shala, target)
        self.writes.append("remove_staff")
        return Guarded(m, True)

    async def remove_student(self, shala: UUID, me: UUID, target: UUID) -> Guarded[None]:
        self._call("remove_student")
        await asyncio.sleep(0)
        m = self.membership(shala, me)
        if m is None:
            return Guarded(None, False)
        own = me == target
        if not can_remove_student(m, own=own):
            return Guarded(m, False)
        if self.students_rows.pop((shala, target), None) is not None:
            for hook in self.on_leave:
                hook(shala, target)
            self.writes.append("remove_student")
        return Guarded(m, True)

    async def join_link(self, shala: UUID, me: UUID) -> Guarded[str]:
        self._call("join_link")
        m = self.membership(shala, me)
        if m is None or not can_show_join_link(m):
            return Guarded(m, False)
        return Guarded(m, True, self.shalas[shala].join_code)

    async def rotate_join(self, shala: UUID, me: UUID, code: str) -> Guarded[str]:
        self._call("rotate_join")
        m = self.membership(shala, me)
        if m is None or not can_rotate_join_link(m):
            return Guarded(m, False)
        self.shalas[shala].join_code = code
        self.writes.append("rotate_join")
        return Guarded(m, True, code)

    async def prune_invites(self, now: datetime) -> int:
        self._call("prune_invites")
        dead = [c for c, i in self.invites.items() if i.expires_at <= now]
        for code in dead:
            del self.invites[code]
        return len(dead)

    # Internals.

    def _call(self, name: str) -> None:
        self.accounts._check()  # pyright: ignore[reportPrivateUsage]
        self.reads.append(name)
        if self.fail_with is not None:
            error, self.fail_with = self.fail_with, None
            raise error

    def _moon(self, shala: UUID, staff: bool, teacher_on_staff: bool) -> ShalaMoon:
        row = self.shalas[shala]
        return ShalaMoon(
            row.id, row.name, row.moon_city or row.city, staff, teacher_on_staff, row.city
        )

    def _card(self, shala: UUID, me: UUID) -> ShalaCard | None:
        m = self.membership(shala, me)
        if m is None:
            return None
        row = self.shalas[shala]
        staff = tuple(
            StaffMember(
                a, self._name(a), a == row.owner_id, self.staff[(shala, a)].roles or frozenset()
            )
            for a in self.staff_of(shala)
        )
        sc02: dict[str, Any] = {}
        if "days_off" in {f.name for f in fields(ShalaCard)}:  # SC-02's card fields
            sc02 = {"days_off": row.days_off, "moon_policy": row.moon_policy}
        return ShalaCard(
            id=row.id,
            name=row.name,
            city=row.city,
            moon_city=row.moon_city,
            online=row.online,
            owner_id=row.owner_id,
            staff=staff,
            students_total=len(self.students_of(shala)),
            me=m,
            **sc02,
        )

    def _drop(self, shala: UUID) -> None:
        self.shalas.pop(shala, None)
        for rows in (self.staff, self.students_rows):
            for key in [k for k in rows if k[0] == shala]:
                del rows[key]
        for code in [c for c, i in self.invites.items() if i.shala_id == shala]:
            del self.invites[code]

    def drop_account(self, account: UUID) -> None:
        """ON DELETE CASCADE: their rows, and every shala they own (Q102)."""
        for shala in [s.id for s in self.shalas.values() if s.owner_id == account]:
            self._drop(shala)
        for rows in (self.staff, self.students_rows):
            for key in [k for k in rows if k[1] == account]:
                del rows[key]
        for code in [c for c, i in self.invites.items() if i.created_by == account]:
            del self.invites[code]

    def _memberships(self, me: UUID) -> list[UUID]:
        return [s for s, _ in self._staff_memberships(me)] + [
            s for s, _ in self._student_memberships(me)
        ]

    def _staff_memberships(self, me: UUID) -> list[tuple[UUID, MemberRow]]:
        return [(s, r) for (s, a), r in self._by_age(self.staff) if a == me]

    def _student_memberships(self, me: UUID) -> list[tuple[UUID, MemberRow]]:
        return [(s, r) for (s, a), r in self._by_age(self.students_rows) if a == me]

    @staticmethod
    def _by_age(
        rows: dict[tuple[UUID, UUID], MemberRow],
    ) -> list[tuple[tuple[UUID, UUID], MemberRow]]:
        return sorted(rows.items(), key=lambda kv: (kv[1].created_at, kv[0][1]))

    def _by_join_code(self, code: str) -> ShalaRow | None:
        return next((s for s in self.shalas.values() if s.join_code == code), None)

    def _live(self, invite: InviteRow) -> bool:
        return self.accounts.clock.now() < invite.expires_at

    def _live_invite(self, code: str) -> InviteRow | None:
        """Unexpired, and its inviter may still grant the role (the SQL's `_inviter_may`)."""
        invite = self.invites.get(code)
        if invite is None or not self._live(invite):
            return None
        inviter = self.membership(invite.shala_id, invite.created_by)
        return invite if can_invite_staff(inviter, invite.role) else None

    def _name(self, account: UUID) -> str | None:
        found = self.accounts.accounts.get(account)
        return found.display_name if found else None

    def _telegram_id(self, account_id: UUID) -> str | None:
        for key, owner in self.accounts.identities.items():
            if owner == account_id:
                return key.provider_user_id
        return None

    def _next_instant(self) -> datetime:
        self._tick += 1
        return self.accounts.clock.now() + timedelta(microseconds=self._tick)


@dataclass
class ShalaAccounts(FollowingAccounts):
    """The account load with MD-02's inputs and the main shala (`Account.shala`)."""

    shalas: InMemoryShalas | None = None

    def inputs(self, account: Account) -> Account:
        loaded = super().inputs(account)
        if self.shalas is None:
            return loaded
        return replace(loaded, shala=self.shalas.main_of(account.id))  # type: ignore[call-arg]

    async def delete(self, account_id: UUID) -> bool:
        if self.shalas is not None:
            self.shalas.drop_account(account_id)
        return await super().delete(account_id)


@dataclass
class ShalaLinks(FollowingLinks):
    """ID-04's accept with the teacher's own shala input (for `_keep_offer`)."""

    shalas: InMemoryShalas | None = None

    async def accept(self, code: str, me: UUID, caps: Caps, linked_on: date) -> Accepted | None:
        accepted = await super().accept(code, me, caps, linked_on)
        if accepted is None or self.shalas is None:
            return accepted
        return replace(accepted, teacher_shala=self.shalas.main_of(accepted.teacher_id))  # type: ignore[call-arg]


@dataclass
class ShalaNotifications(FollowingNotifications):
    """Tick candidates carry `shala_location`, `shala_staff`, `shala_teacher_on_staff`."""

    async def candidates(
        self, since: datetime, logged_from: Any, defaults: Any
    ) -> list[ReminderCandidate]:
        out: list[ReminderCandidate] = []
        accounts = self.accounts
        for c in await super().candidates(since, logged_from, defaults):
            shala = (
                accounts.shalas.main_of(c.account_id)
                if isinstance(accounts, ShalaAccounts) and accounts.shalas
                else None
            )
            out.append(
                replace(
                    c,
                    shala_location=shala.moon_city if shala else None,  # type: ignore[call-arg]
                    shala_staff=bool(shala and shala.staff),
                    shala_teacher_on_staff=bool(shala and shala.teacher_on_staff),
                    shala_city=shala.city if shala else None,
                )
            )
        return out


@dataclass
class StaffNotifier(FakeNotifier):
    """Records the silent staff-joined notes: (recipient, name, shala, role)."""

    staff_joined: list[tuple[Recipient, str | None, str, ShalaRole]] = field(
        default_factory=list[tuple[Recipient, str | None, str, ShalaRole]]
    )

    async def tell_staff_joined(
        self, recipient: Recipient, name: str | None, shala: str, role: ShalaRole
    ) -> DeliveryResult:
        self.staff_joined.append((recipient, name, shala, role))
        return DeliveryResult(DeliveryStatus.SENT)


def shala_storage() -> InMemoryStorage:
    """MD-02's following storage with the shala repository wired into the account load."""
    accounts = ShalaAccounts()
    days = InMemoryDays()
    storage = InMemoryStorage(
        repo=accounts,
        day_repo=days,
        notification_repo=ShalaNotifications(accounts, days=days),
        export_repo=FollowingExport(accounts),
    )
    links = ShalaLinks(accounts)
    shalas = InMemoryShalas(accounts, links)
    links.shalas = shalas
    storage.link_repo = links
    storage.shala_repo = shalas
    accounts.links = links
    accounts.shalas = shalas
    return storage
