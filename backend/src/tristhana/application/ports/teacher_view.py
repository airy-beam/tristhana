"""The teacher's read path (ST-06, ADR-0031). `timezone`, `locale`, `linked_on` and
`quiet_note_agreed` stop at the use case and appear in no output type.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import Protocol
from uuid import UUID

from tristhana.domain.locale import Locale
from tristhana.domain.practice import PracticeLength
from tristhana.domain.progression import Position
from tristhana.domain.teacher_view import SharedDay


@dataclass(frozen=True, slots=True)
class StudentLink:
    teacher_id: UUID
    student_id: UUID
    name: str | None
    timezone: str | None
    locale: Locale
    linked_on: date


@dataclass(frozen=True, slots=True)
class SharedLog:
    link: StudentLink
    shown: Mapping[date, SharedDay]


@dataclass(frozen=True, slots=True)
class SharedPage:
    students: tuple[SharedLog, ...]
    total: int


@dataclass(frozen=True, slots=True)
class SharedDetail:
    log: SharedLog
    lengths: Mapping[date, PracticeLength]
    position: Position | None
    quiet_note_agreed: bool


class TeacherViewRepository(Protocol):
    async def page(
        self, teacher: UUID, offset: int, limit: int, since: date, until: date
    ) -> SharedPage: ...
    async def student(
        self, teacher: UUID, student: UUID, since: date, until: date
    ) -> SharedDetail | None: ...
