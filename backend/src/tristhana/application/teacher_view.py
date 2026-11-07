"""What a teacher sees of their students (ST-06, ADR-0031): both adapters use these. Built with
the teacher view port and a clock only, so no decrypted value or student account is in reach.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from tristhana.application.policies import (
    NotAllowed,
    Principal,
    can_view_activity,
    can_view_last_asana,
)
from tristhana.application.ports.storage import Clock
from tristhana.application.ports.teacher_links import NotLinked
from tristhana.application.ports.teacher_view import StudentLink, TeacherViewRepository
from tristhana.domain.days import local_today, provisional_zone
from tristhana.domain.teacher_view import QUIET_DAYS, StudentCard, StudentToday, card_days, is_quiet


def _today(now: datetime, link: StudentLink) -> date:
    """The student's day, never the teacher's (Q87 and `06 Time Zones`)."""
    return local_today(now, link.timezone or provisional_zone(link.locale))


class GetStudents:
    def __init__(self, view: TeacherViewRepository, clock: Clock) -> None:
        self._view = view
        self._clock = clock

    async def execute(
        self, principal: Principal, offset: int, limit: int
    ) -> tuple[tuple[StudentToday, ...], int]:
        now = self._clock.now()
        utc = now.astimezone(UTC).date()
        page = await self._view.page(
            principal.account.id, offset, limit, utc - timedelta(1), utc + timedelta(1)
        )
        found: list[StudentToday] = []
        for log in page.students:
            if not can_view_activity(principal.account, log.link):
                raise NotAllowed
            found.append(
                StudentToday(
                    log.link.student_id, log.link.name, log.shown.get(_today(now, log.link))
                )
            )
        return tuple(found), page.total


class GetStudent:
    def __init__(self, view: TeacherViewRepository, clock: Clock) -> None:
        self._view = view
        self._clock = clock

    async def execute(self, principal: Principal, student_id: UUID) -> StudentCard:
        now = self._clock.now()
        utc = now.astimezone(UTC).date()
        detail = await self._view.student(
            principal.account.id, student_id, utc - timedelta(QUIET_DAYS), utc + timedelta(1)
        )
        if detail is None:
            raise NotLinked
        link = detail.log.link
        if not can_view_activity(principal.account, link) or not can_view_last_asana(
            principal.account, link
        ):
            raise NotAllowed
        today = _today(now, link)
        return StudentCard(
            link.student_id,
            link.name,
            card_days(detail.log.shown, detail.lengths, today),
            detail.position,
            is_quiet(detail.log.shown.keys(), today, link.linked_on, detail.quiet_note_agreed),
        )


@dataclass(frozen=True, slots=True)
class TeacherViewUseCases:
    students: GetStudents
    student: GetStudent
