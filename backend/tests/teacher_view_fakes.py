"""In-memory `TeacherViewRepository`s (ST-06, spec §3).

Its own file because it imports the feature's port; `InMemoryStorage.teacher_view` loads it on
first use. `InMemoryTeacherView` follows the SQL over the in-memory links, days and periods, so
the bot and API tests log real statuses. `ScriptedTeacherView` returns what a test hands it,
including rows the SQL would never give, because the use case must not trust them."""

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from uuid import UUID

from tests.fakes import InMemoryDays
from tests.teacher_link_fakes import InMemoryTeacherLinks, Row
from tristhana.application.ports.teacher_view import (
    SharedDetail,
    SharedLog,
    SharedPage,
    StudentLink,
)
from tristhana.domain.practice import PracticeLength
from tristhana.domain.teacher_view import SHARED, SharedDay

_DAY = timedelta(days=1)


@dataclass
class InMemoryTeacherView:
    links: InMemoryTeacherLinks
    days: InMemoryDays
    # Finished reads, in order: a DB round trip takes time, so each one yields first.
    reads: list[str] = field(default_factory=list[str])

    async def page(
        self, teacher: UUID, offset: int, limit: int, since: date, until: date
    ) -> SharedPage:
        await asyncio.sleep(0)
        self.reads.append("page")
        rows = sorted(
            (r for r in self.links.rows.values() if r.teacher_id == teacher),
            key=self._order,
        )
        chosen = rows[offset : offset + limit]
        if not chosen:
            return SharedPage((), 0)  # `count(*) OVER ()` has no row to ride on
        return SharedPage(tuple(self._log(r, since, until) for r in chosen), len(rows))

    async def student(
        self, teacher: UUID, student: UUID, since: date, until: date
    ) -> SharedDetail | None:
        await asyncio.sleep(0)
        self.reads.append("student")
        row = self.links.rows.get((student, teacher))
        if row is None:
            return None
        log = self._log(row, since, until)
        lengths: dict[date, PracticeLength] = {}
        for day, shown in log.shown.items():
            kept = self.days.practice_rows.get((student, day))
            if shown is SharedDay.PRACTICED and kept is not None and kept.length is not None:
                lengths[day] = kept.length
        state = self.days.progression_rows.get(student)
        position = state.position if state is not None else None
        return SharedDetail(log, lengths, position, row.quiet_note_agreed)

    def _name(self, student: UUID) -> str | None:
        account = self.links.accounts.accounts.get(student)
        return account.display_name if account else None

    def _order(self, row: Row) -> tuple[bool, str, UUID]:
        name = self._name(row.student_id)
        return (name is None, (name or "").lower(), row.student_id)

    def _log(self, row: Row, since: date, until: date) -> SharedLog:
        account = self.links.accounts.accounts[row.student_id]
        link = StudentLink(
            teacher_id=row.teacher_id,
            student_id=row.student_id,
            name=account.display_name,
            timezone=account.timezone,
            locale=account.locale,
            linked_on=row.linked_on,
        )
        return SharedLog(link, self._shown(row, since, until))

    def _shown(self, row: Row, since: date, until: date) -> dict[date, SharedDay]:
        first = max(since, row.linked_on)
        logged = {
            d: log.status for (a, d), (log, _) in self.days.rows.items() if a == row.student_id
        }
        shown: dict[date, SharedDay] = {}
        for day, status in logged.items():
            value = SHARED[status]
            if value is not None and first <= day <= until:
                shown[day] = value
        for period in self.days.periods.of(row.student_id):
            day, last = max(period.start, first), min(period.end, until)
            while day <= last:
                if day not in logged:  # logged beats period: "No practice" stays blank
                    shown[day] = SharedDay.REST
                day += _DAY
        return shown


@dataclass
class ScriptedTeacherView:
    """Hands back `logs` and `details` as given, trimmed to the range the use case asked for
    the way the SQL's `BETWEEN` does. It doesn't check the teacher, so foreign rows get through."""

    logs: list[SharedLog] = field(default_factory=list[SharedLog])
    details: dict[UUID, SharedDetail] = field(default_factory=dict[UUID, SharedDetail])
    page_calls: list[tuple[UUID, int, int, date, date]] = field(
        default_factory=list[tuple[UUID, int, int, date, date]]
    )
    student_calls: list[tuple[UUID, UUID, date, date]] = field(
        default_factory=list[tuple[UUID, UUID, date, date]]
    )

    async def page(
        self, teacher: UUID, offset: int, limit: int, since: date, until: date
    ) -> SharedPage:
        self.page_calls.append((teacher, offset, limit, since, until))
        chosen = self.logs[offset : offset + limit]
        trimmed = tuple(replace(g, shown=_trim(g.shown, since, until)) for g in chosen)
        return SharedPage(trimmed, len(self.logs) if chosen else 0)

    async def student(
        self, teacher: UUID, student: UUID, since: date, until: date
    ) -> SharedDetail | None:
        self.student_calls.append((teacher, student, since, until))
        found = self.details.get(student)
        if found is None:
            return None
        log = replace(found.log, shown=_trim(found.log.shown, since, until))
        return replace(found, log=log, lengths=_trim(found.lengths, since, until))


def _trim[T](values: Mapping[date, T], since: date, until: date) -> dict[date, T]:
    return {d: v for d, v in values.items() if since <= d <= until}
