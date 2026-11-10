"""In-memory `TeacherLinkRepository` and seeding helpers (ID-04, spec §3).

Its own file because it imports the feature's port, and `tests/fakes.py` is imported by nearly
every test: `InMemoryStorage.teacher_links` loads it on first use."""

import asyncio
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta
from typing import Any
from uuid import UUID

from tests.fakes import InMemoryAccounts
from tristhana.application.ports.teacher_links import (
    Accepted,
    Caps,
    InvitePreview,
    Links,
    Unlinked,
)
from tristhana.application.ports.teacher_links import LinksChanged as LinksChanged
from tristhana.domain.accounts import (
    Account,
    IdentityKey,
    IdentityProvider,
    NewAccount,
)
from tristhana.domain.directory_listing import ListingMark, mark_of
from tristhana.domain.locale import Locale
from tristhana.domain.moon import TeacherMoon
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
    quiet_note_agreed: bool = False  # ST-06: the column's default; only `accept` sets it


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
    # ID-05: an `InMemoryListings`; a listed teacher's mark rides on `preview` and `overview`.
    listings: Any = None

    def _mark(self, teacher: UUID) -> ListingMark | None:
        if self.listings is None:
            return None
        return mark_of(self.listings.rows.get(teacher))

    # Seeding (not part of the port).

    def add(
        self,
        student: UUID,
        teacher: UUID,
        *,
        primary: bool = False,
        linked_on: date = FIRST_LINKED_ON,
        created_at: datetime | None = None,
        quiet_note_agreed: bool = False,
    ) -> Row:
        at = created_at or self._next_instant()
        row = Row(student, teacher, primary, linked_on, at, quiet_note_agreed)
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
            listing=self._mark(teacher.id),
        )

    async def accept(self, code: str, me: UUID, caps: Caps, linked_on: date) -> Accepted | None:
        self._check()
        await asyncio.sleep(0)
        teacher = self._owner(code)
        if teacher is None:
            return None
        students_before = len(self.students_of(teacher.id))
        their_main = self.main_of(teacher.id)
        already = (me, teacher.id) in self.rows
        created = (
            not already
            and teacher.id != me
            and len(self.teachers_of(me)) < caps.teachers
            and len(self.students_of(teacher.id)) < caps.students
        )
        if created:
            self.add(me, teacher.id, linked_on=linked_on, quiet_note_agreed=True)  # as `_accept`
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
            teacher_moon=teacher.moon_location,
            teacher_students_before=students_before,
            teacher_main=their_main,
        )

    async def overview(self, me: UUID) -> Links:
        self._check()
        return Links(
            teachers=tuple(
                self._linked(r.teacher_id, r, r.is_primary)
                for r in self._ordered()
                if r.student_id == me
            ),
            listings={
                r.teacher_id: mark
                for r in self._ordered()
                if r.student_id == me and (mark := self._mark(r.teacher_id)) is not None
            },
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

    def main_of(self, student: UUID) -> TeacherMoon | None:
        """`ORDER BY is_primary DESC, created_at, teacher_id LIMIT 1` with the teacher's row."""
        mine = [r for r in self.rows.values() if r.student_id == student]
        if not mine:
            return None
        row = min(mine, key=lambda r: (not r.is_primary, r.created_at, r.teacher_id))
        teacher = self.accounts.accounts[row.teacher_id]
        return TeacherMoon(teacher.id, teacher.display_name, teacher.moon_location)

    async def set_primary(self, me: UUID, teacher_id: UUID) -> TeacherMoon | None:
        self._check()
        await asyncio.sleep(0)
        if self.lose_next_flip:
            self.lose_next_flip = False
            raise LinksChanged
        target = self.rows.get((me, teacher_id))
        if target is None:
            return None
        for row in self.rows.values():
            if row.student_id == me:
                row.is_primary = False
        target.is_primary = True
        self.writes.append("set_primary")
        return self.main_of(me)

    async def unlink(self, student: UUID, teacher: UUID) -> Unlinked:
        self._check()
        await asyncio.sleep(0)
        removed = self.rows.pop((student, teacher), None) is not None
        self.writes.append("unlink")
        return Unlinked(removed, self.main_of(student))

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
