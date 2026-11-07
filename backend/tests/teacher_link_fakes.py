"""In-memory `TeacherLinkRepository` and seeding helpers (ID-04, spec §3).

Its own file because it imports the feature's port, and `tests/fakes.py` is imported by nearly
every test: `InMemoryStorage.teacher_links` loads it on first use."""

import asyncio
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta
from uuid import UUID

from tests.fakes import InMemoryAccounts
from tristhana.application.ports.teacher_links import Accepted, Caps, InvitePreview, Links
from tristhana.application.ports.teacher_links import LinksChanged as LinksChanged
from tristhana.domain.accounts import (
    Account,
    IdentityKey,
    IdentityProvider,
    NewAccount,
)
from tristhana.domain.locale import Locale
from tristhana.domain.teacher_links import MAX_STUDENTS, MAX_TEACHERS, Linked

CAPS = Caps(teachers=MAX_TEACHERS, students=MAX_STUDENTS)
FIRST_LINKED_ON = date(2026, 10, 18)


def add_person(
    accounts: InMemoryAccounts,
    telegram_id: str,
    name: str | None = "Person",
    locale: Locale = "en",
    zone: str | None = None,
) -> Account:
    """Someone already known to the app, for the other side of a link."""
    key = IdentityKey(IdentityProvider.TELEGRAM, telegram_id)
    created = accounts._insert(key, NewAccount(name, locale))  # pyright: ignore[reportPrivateUsage]
    account = replace(created, timezone=zone)
    accounts.accounts[account.id] = account
    return account


@dataclass
class Row:
    student_id: UUID
    teacher_id: UUID
    is_primary: bool
    linked_on: date
    created_at: datetime


class FixedCodes:
    """`CodeSource` with a known sequence."""

    def __init__(self, *codes: str) -> None:
        self._codes = list(codes)

    def new(self) -> str:
        return self._codes.pop(0)


@dataclass
class InMemoryTeacherLinks:
    accounts: InMemoryAccounts
    rows: dict[tuple[UUID, UUID], Row] = field(default_factory=dict[tuple[UUID, UUID], Row])
    codes: dict[UUID, str] = field(default_factory=dict[UUID, str])  # teacher -> code
    # Simulates losing the 23505 race on `teacher_link_one_primary`.
    lose_next_flip: bool = False
    # Raised by the next read or write (a handler error, a storage failure).
    fail_with: Exception | None = None
    # Finished writes, in order: a DB round trip takes time, so each one yields first.
    writes: list[str] = field(default_factory=list[str])
    previews: int = 0
    _tick: int = 0

    # Seeding (not part of the port).

    def add(
        self,
        student: UUID,
        teacher: UUID,
        *,
        primary: bool = False,
        linked_on: date = FIRST_LINKED_ON,
        created_at: datetime | None = None,
    ) -> Row:
        row = Row(student, teacher, primary, linked_on, created_at or self._next_instant())
        self.rows[(student, teacher)] = row
        return row

    def teachers_of(self, student: UUID) -> list[UUID]:
        return [r.teacher_id for r in self._ordered() if r.student_id == student]

    def students_of(self, teacher: UUID) -> list[UUID]:
        return [r.student_id for r in self._ordered() if r.teacher_id == teacher]

    # The port.

    async def preview(self, code: str, me: UUID) -> InvitePreview | None:
        self._check()
        self.previews += 1
        teacher = self._owner(code)
        if teacher is None:
            return None
        return InvitePreview(
            teacher_id=teacher.id,
            teacher_name=teacher.display_name,
            already=(me, teacher.id) in self.rows,
            my_teachers=len(self.teachers_of(me)),
            their_students=len(self.students_of(teacher.id)),
        )

    async def accept(self, code: str, me: UUID, caps: Caps, linked_on: date) -> Accepted | None:
        self._check()
        await asyncio.sleep(0)
        teacher = self._owner(code)
        if teacher is None:
            return None
        already = (me, teacher.id) in self.rows
        created = (
            not already
            and teacher.id != me
            and len(self.teachers_of(me)) < caps.teachers
            and len(self.students_of(teacher.id)) < caps.students
        )
        if created:
            self.add(me, teacher.id, linked_on=linked_on)
            self.writes.append("accept")
        return Accepted(
            created=created,
            already=already,
            full=not created
            and (
                len(self.teachers_of(me)) >= caps.teachers
                or len(self.students_of(teacher.id)) >= caps.students
            ),
            my_teachers=len(self.teachers_of(me)),
            teacher_id=teacher.id,
            teacher_name=teacher.display_name,
            teacher_locale=teacher.locale,
            teacher_telegram_id=self._telegram_id(teacher.id),
        )

    async def overview(self, me: UUID) -> Links:
        self._check()
        return Links(
            teachers=tuple(
                self._linked(r.teacher_id, r, r.is_primary)
                for r in self._ordered()
                if r.student_id == me
            ),
            students=tuple(
                self._linked(r.student_id, r, False)  # a teacher never learns they're main
                for r in self._ordered()
                if r.teacher_id == me
            ),
        )

    async def invite(self, me: UUID, new_code: str) -> str:
        self._check()
        return self.codes.setdefault(me, new_code)

    async def rotate(self, me: UUID, new_code: str) -> str:
        self._check()
        self.codes[me] = new_code
        return new_code

    async def set_primary(self, me: UUID, teacher_id: UUID) -> bool:
        self._check()
        await asyncio.sleep(0)
        if self.lose_next_flip:
            self.lose_next_flip = False
            raise LinksChanged
        target = self.rows.get((me, teacher_id))
        if target is None:
            return False
        for row in self.rows.values():
            if row.student_id == me:
                row.is_primary = False
        target.is_primary = True
        self.writes.append("set_primary")
        return True

    async def unlink(self, student: UUID, teacher: UUID) -> bool:
        self._check()
        await asyncio.sleep(0)
        removed = self.rows.pop((student, teacher), None) is not None
        self.writes.append("unlink")
        return removed

    # Internals.

    def _check(self) -> None:
        self.accounts._check()  # pyright: ignore[reportPrivateUsage]
        if self.fail_with is not None:
            error, self.fail_with = self.fail_with, None
            raise error

    def _owner(self, code: str) -> Account | None:
        for teacher_id, known in self.codes.items():
            if known == code:
                return self.accounts.accounts.get(teacher_id)
        return None

    def _ordered(self) -> list[Row]:
        return sorted(self.rows.values(), key=lambda r: (r.created_at, r.teacher_id))

    def _linked(self, other: UUID, row: Row, chosen: bool) -> Linked:
        account = self.accounts.accounts.get(other)
        name = account.display_name if account else None
        return Linked(other, name, chosen, row.created_at)

    def _telegram_id(self, account_id: UUID) -> str | None:
        for key, owner in self.accounts.identities.items():
            if owner == account_id:
                return key.provider_user_id
        return None

    def _next_instant(self) -> datetime:
        self._tick += 1
        return self.accounts.clock.now() + timedelta(microseconds=self._tick)
