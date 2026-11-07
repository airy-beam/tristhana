"""The teacher's read path (ST-06, ADR-0031): one statement per list page or card. Only
`practiced` or `rest` leaves SQL, no sealed column is selected and no cipher is held.
"""

from datetime import date, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import Date, and_, case, cast, exists, func, literal, select, true, union_all
from sqlalchemy.dialects.postgresql import INTERVAL
from sqlalchemy.ext.asyncio import AsyncEngine

from tristhana.application.ports.teacher_view import (
    SharedDetail,
    SharedLog,
    SharedPage,
    StudentLink,
)
from tristhana.domain.days import public_status
from tristhana.domain.practice import PracticeLength
from tristhana.domain.progression import Position
from tristhana.domain.rest_periods import MAX_PERIOD_DAYS
from tristhana.domain.teacher_view import SHARED, SharedDay
from tristhana.infrastructure.db.engine import connection
from tristhana.infrastructure.db.tables import (
    account,
    day_log,
    practice,
    progression,
    rest_period,
    teacher_link,
)

_STORED = sorted({public_status(s).value for s, v in SHARED.items() if v is not None})


def _page(teacher: UUID, *, student: UUID | None, offset: int, limit: int, flag: bool) -> Any:
    link = teacher_link
    columns = [
        link.c.student_id,
        link.c.linked_on,
        account.c.display_name,
        account.c.timezone,
        account.c.locale,
        func.count().over().label("total"),
    ]
    if flag:
        columns.append(link.c.quiet_note_agreed)
    stmt = (
        select(*columns)
        .join_from(link, account, account.c.id == link.c.student_id)
        .where(link.c.teacher_id == teacher)
        .order_by(func.lower(account.c.display_name).nulls_last(), link.c.student_id)
    )
    if student is not None:
        stmt = stmt.where(link.c.student_id == student)
    else:
        stmt = stmt.limit(limit).offset(offset)
    return stmt.cte("page")


def _shown(page: Any, since: date, until: date) -> Any:
    d = day_log
    state = case(
        *((d.c.status == s.value, v.value) for s, v in SHARED.items() if v is SharedDay.PRACTICED),
        else_=SharedDay.REST.value,
    )
    logged = select(page.c.student_id, d.c.local_date.label("day"), state.label("state")).join_from(
        page,
        d,
        and_(
            d.c.account_id == page.c.student_id,
            d.c.local_date.between(func.greatest(since, page.c.linked_on), until),
            d.c.status.in_(_STORED),
        ),
    )
    r = rest_period
    covered = (
        func.generate_series(
            func.greatest(r.c.start_date, page.c.linked_on, since),
            func.least(r.c.end_date, until),
            literal("1 day").cast(INTERVAL),
        )
        .table_valued("value")
        .render_derived("covered", with_types=False)
    )
    day = cast(covered.c.value, Date)
    paused = (
        select(page.c.student_id, day.label("day"), literal(SharedDay.REST.value).label("state"))
        .select_from(
            page.join(
                r,
                and_(
                    r.c.account_id == page.c.student_id,
                    r.c.start_date.between(since - timedelta(days=MAX_PERIOD_DAYS - 1), until),
                ),
            ).join(covered, true())
        )
        # Load-bearing: a logged day beats a period, so "No practice" inside one stays blank.
        .where(~exists().where(d.c.account_id == page.c.student_id, d.c.local_date == day))
    )
    return union_all(logged, paused).cte("shown")


def _link(teacher: UUID, r: Any) -> StudentLink:
    return StudentLink(teacher, r.student_id, r.display_name, r.timezone, r.locale, r.linked_on)


class SqlTeacherViewRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def page(
        self, teacher: UUID, offset: int, limit: int, since: date, until: date
    ) -> SharedPage:
        page = _page(teacher, student=None, offset=offset, limit=limit, flag=False)
        shown = _shown(page, since, until)
        stmt = (
            select(page, shown.c.day, shown.c.state)
            .select_from(page.outerjoin(shown, shown.c.student_id == page.c.student_id))
            .order_by(func.lower(page.c.display_name).nulls_last(), page.c.student_id)
        )
        async with connection(self._engine) as conn:
            rows = (await conn.execute(stmt)).all()
        logs: dict[UUID, tuple[StudentLink, dict[date, SharedDay]]] = {}
        total = 0
        for r in rows:
            total = r.total
            entry = logs.setdefault(r.student_id, (_link(teacher, r), {}))
            if r.day is not None:
                entry[1][r.day] = SharedDay(r.state)
        return SharedPage(tuple(SharedLog(link, days) for link, days in logs.values()), total)

    async def student(
        self, teacher: UUID, student: UUID, since: date, until: date
    ) -> SharedDetail | None:
        page = _page(teacher, student=student, offset=0, limit=1, flag=True)
        shown = _shown(page, since, until)
        p, g = practice, progression
        stmt = select(
            page,
            shown.c.day,
            shown.c.state,
            p.c.series.label("length_series"),
            p.c.end_item,
            p.c.first_part,
            g.c.account_id.label("position_set"),
            g.c.series.label("position_series"),
            g.c.last_key,
        ).select_from(
            page.outerjoin(shown, shown.c.student_id == page.c.student_id)
            .outerjoin(
                p,
                and_(
                    p.c.account_id == page.c.student_id,
                    p.c.local_date == shown.c.day,
                    shown.c.state == SharedDay.PRACTICED.value,
                ),
            )
            .outerjoin(g, g.c.account_id == page.c.student_id)
        )
        async with connection(self._engine) as conn:
            rows = (await conn.execute(stmt)).all()
        if not rows:
            return None
        first = rows[0]
        days: dict[date, SharedDay] = {}
        lengths: dict[date, PracticeLength] = {}
        for r in rows:
            if r.day is None:
                continue
            days[r.day] = SharedDay(r.state)
            if r.length_series is not None:
                lengths[r.day] = PracticeLength(tuple(r.length_series), r.end_item, r.first_part)
        position = None
        if first.position_set is not None:
            position = Position(first.position_series, first.last_key)
        return SharedDetail(
            SharedLog(_link(teacher, first), days), lengths, position, first.quiet_note_agreed
        )
