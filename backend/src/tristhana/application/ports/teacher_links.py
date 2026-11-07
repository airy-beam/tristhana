"""Teacher links (ID-04, ADR-0030). No exception here carries an invite code: a code must
never reach a log."""

from dataclasses import dataclass
from datetime import date
from typing import Protocol
from uuid import UUID

from tristhana.domain.locale import Locale
from tristhana.domain.moon import MoonFollow, ShalaMoon, TeacherMoon
from tristhana.domain.teacher_links import Linked


class NotLinked(Exception):
    """The caller has no link to that teacher."""


class LinksChanged(Exception):
    """Another tap chose a main teacher at the same moment; the last tap retries."""


@dataclass(frozen=True, slots=True)
class Caps:
    teachers: int
    students: int


@dataclass(frozen=True, slots=True)
class InvitePreview:
    teacher_id: UUID
    teacher_name: str | None
    already: bool
    my_teachers: int
    their_students: int


@dataclass(frozen=True, slots=True)
class Accepted:
    """`created` False: the caller's own code (`teacher_id`), a cap (`full`), else a duplicate,
    so a refused ✅ needs no second read. `already` can be False on a duplicate: the loser of
    a double tap doesn't see the winner's row in its snapshot."""

    created: bool
    already: bool
    full: bool
    my_teachers: int  # after this link
    teacher_id: UUID
    teacher_name: str | None
    teacher_locale: Locale
    teacher_telegram_id: str | None
    # MD-02, from the same statement: the teacher's own stored moon value, their student count
    # before this link and their own main teacher (for the first-student Keep offer).
    teacher_moon: str | None = None
    teacher_students_before: int = 0
    teacher_main: TeacherMoon | None = None
    teacher_shala: ShalaMoon | None = None  # SC-01: the teacher's own main shala
    moon: MoonFollow | None = None  # set by `AcceptInvite`: the caller's new city, if it moved


@dataclass(frozen=True, slots=True)
class Unlinked:
    removed: bool
    main: TeacherMoon | None  # the student's main teacher after the removal


@dataclass(frozen=True, slots=True)
class Links:
    teachers: tuple[Linked, ...]
    students: tuple[Linked, ...]


class CodeSource(Protocol):
    def new(self) -> str: ...


class QrCodes(Protocol):
    def png(self, url: str) -> bytes: ...


class TeacherLinkRepository(Protocol):
    async def preview(self, code: str, me: UUID) -> InvitePreview | None:
        """None: no such code."""
        ...

    async def accept(self, code: str, me: UUID, caps: Caps, linked_on: date) -> Accepted | None:
        """One statement. None: no such code, or the teacher was deleted mid-tap."""
        ...

    async def overview(self, me: UUID) -> Links: ...

    async def invite(self, me: UUID, new_code: str) -> str:
        """The caller's code, created with `new_code` if there is none yet."""
        ...

    async def rotate(self, me: UUID, new_code: str) -> str: ...

    async def set_primary(self, me: UUID, teacher_id: UUID) -> TeacherMoon | None:
        """The new main teacher; None: not linked, nothing changed. Raises `LinksChanged`."""
        ...

    async def unlink(self, student: UUID, teacher: UUID) -> Unlinked: ...
