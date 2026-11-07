"""`TeacherLinkRepository` on Postgres (ID-04, ADR-0030). `is_primary` holds only an explicit
choice; the partial unique index `teacher_link_one_primary` keeps it to one per student."""

from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import and_, case, delete, exists, func, literal, or_, select, update
from sqlalchemy.dialects.postgresql import JSONB, insert
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

from tristhana.application.ports.teacher_links import (
    Accepted,
    Caps,
    InvitePreview,
    Links,
    LinksChanged,
    Unlinked,
)
from tristhana.domain.moon import TeacherMoon
from tristhana.domain.teacher_links import Linked
from tristhana.infrastructure.db.accounts import MAIN_TEACHER, to_teacher
from tristhana.infrastructure.db.engine import connection, constraint_name, sqlstate
from tristhana.infrastructure.db.tables import account, identity, teacher_invite, teacher_link

_TEACHER_GONE = "teacher_link_teacher_id_fkey"
_ONE_PRIMARY = "teacher_link_one_primary"


def _counts(me: UUID, teacher: Any) -> tuple[Any, Any, Any]:
    """Already linked, my teachers, their students: the facts an invite depends on."""
    link = teacher_link
    already = exists().where(link.c.student_id == me, link.c.teacher_id == teacher)
    mine = select(func.count()).select_from(link).where(link.c.student_id == me)
    theirs = select(func.count()).select_from(link).where(link.c.teacher_id == teacher)
    return already, mine.scalar_subquery(), theirs.scalar_subquery()


def _accept(code: str, me: UUID, caps: Caps, linked_on: date) -> Any:
    teacher = teacher_invite.c.account_id
    already, mine, theirs = _counts(me, teacher)
    found = (
        select(
            teacher.label("teacher_id"),
            already.label("already"),
            mine.label("mine"),
            theirs.label("theirs"),
        )
        .where(teacher_invite.c.code == code)
        .cte("found")
    )
    added = (
        insert(teacher_link)
        .from_select(
            ["student_id", "teacher_id", "linked_on", "quiet_note_agreed"],
            select(literal(me), found.c.teacher_id, literal(linked_on), literal(True)).where(
                found.c.teacher_id != me,
                found.c.mine < caps.teachers,
                found.c.theirs < caps.students,
            ),
        )
        .on_conflict_do_nothing()
        .returning(teacher_link.c.teacher_id)
        .cte("added")
    )
    return (
        select(
            found.c.teacher_id,
            found.c.already,
            found.c.mine,
            found.c.theirs,
            account.c.display_name,
            account.c.locale,
            account.c.moon_location,  # MD-02: the teacher's own value and main teacher
            MAIN_TEACHER,
            identity.c.provider_user_id,
            exists().where(added.c.teacher_id == found.c.teacher_id).label("created"),
        )
        .join_from(found, account, account.c.id == found.c.teacher_id)
        .outerjoin(
            identity,
            and_(identity.c.account_id == found.c.teacher_id, identity.c.provider == "telegram"),
        )
    )


class SqlTeacherLinkRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def preview(self, code: str, me: UUID) -> InvitePreview | None:
        teacher = teacher_invite.c.account_id
        already, mine, theirs = _counts(me, teacher)
        stmt = (
            select(
                teacher,
                account.c.display_name,
                already.label("already"),
                mine.label("mine"),
                theirs.label("theirs"),
            )
            .join_from(teacher_invite, account, account.c.id == teacher)
            .where(teacher_invite.c.code == code)
        )
        async with connection(self._engine) as conn:
            row = (await conn.execute(stmt)).one_or_none()
        if row is None:
            return None
        return InvitePreview(row.account_id, row.display_name, row.already, row.mine, row.theirs)

    async def accept(self, code: str, me: UUID, caps: Caps, linked_on: date) -> Accepted | None:
        try:
            async with connection(self._engine) as conn:
                row = (await conn.execute(_accept(code, me, caps, linked_on))).one_or_none()
        except DBAPIError as e:
            if sqlstate(e) == "23503" and constraint_name(e) == _TEACHER_GONE:
                return None  # the teacher deleted their account mid-tap
            raise
        if row is None:
            return None
        return Accepted(
            created=row.created,
            already=row.already,
            full=row.mine >= caps.teachers or row.theirs >= caps.students,
            my_teachers=row.mine + (1 if row.created else 0),
            teacher_id=row.teacher_id,
            teacher_name=row.display_name,
            teacher_locale=row.locale,
            teacher_telegram_id=row.provider_user_id,
            teacher_moon=row.moon_location,
            teacher_students_before=row.theirs,
            teacher_main=to_teacher(row.main_teacher),
        )

    async def overview(self, me: UUID) -> Links:
        link = teacher_link
        mine = link.c.student_id == me  # a row where I'm the student: the other is my teacher
        other = case((mine, link.c.teacher_id), else_=link.c.student_id).label("other")
        stmt = (
            select(
                mine.label("mine"),
                other,
                account.c.display_name,
                and_(mine, link.c.is_primary).label("chosen"),
                link.c.created_at,
            )
            .join_from(link, account, account.c.id == other)
            .where(or_(mine, link.c.teacher_id == me))
            .order_by(link.c.created_at, other)
        )
        async with connection(self._engine) as conn:
            rows = (await conn.execute(stmt)).all()
        people = [(r.mine, Linked(r.other, r.display_name, r.chosen, r.created_at)) for r in rows]
        return Links(
            teachers=tuple(p for is_mine, p in people if is_mine),
            students=tuple(p for is_mine, p in people if not is_mine),
        )

    async def invite(self, me: UUID, new_code: str) -> str:
        stmt = insert(teacher_invite).values(account_id=me, code=new_code)
        stmt = stmt.on_conflict_do_update(  # a no-op update, so RETURNING gives the stored code
            index_elements=[teacher_invite.c.account_id],
            set_={"code": teacher_invite.c.code},
        ).returning(teacher_invite.c.code)
        async with connection(self._engine) as conn:
            return (await conn.execute(stmt)).scalar_one()

    async def rotate(self, me: UUID, new_code: str) -> str:
        stmt = insert(teacher_invite).values(account_id=me, code=new_code)
        stmt = stmt.on_conflict_do_update(
            index_elements=[teacher_invite.c.account_id],
            set_={"code": stmt.excluded.code, "created_at": func.now()},
        ).returning(teacher_invite.c.code)
        async with connection(self._engine) as conn:
            return (await conn.execute(stmt)).scalar_one()

    async def set_primary(self, me: UUID, teacher_id: UUID) -> TeacherMoon | None:
        """Clear, then set, in one transaction: the index isn't deferrable, so one UPDATE
        flipping both rows can fail on row order. Returns the chosen teacher (MD-02)."""
        link = teacher_link
        mine = link.c.student_id == me
        try:
            async with connection(self._engine) as conn:
                conn = await conn.execution_options(isolation_level="READ COMMITTED")
                async with conn.begin() as transaction:
                    await conn.execute(
                        update(link).where(mine, link.c.is_primary).values(is_primary=False)
                    )
                    chosen = (
                        await conn.execute(
                            update(link)
                            .where(
                                mine,
                                link.c.teacher_id == teacher_id,
                                account.c.id == link.c.teacher_id,
                            )
                            .values(is_primary=True)
                            .returning(account.c.display_name, account.c.moon_location)
                        )
                    ).one_or_none()
                    if chosen is None:
                        await transaction.rollback()  # keep the old choice
                        return None
                    return TeacherMoon(teacher_id, chosen.display_name, chosen.moon_location)
        except DBAPIError as e:
            if sqlstate(e) == "23505" and constraint_name(e) == _ONE_PRIMARY:
                raise LinksChanged from e
            raise

    async def unlink(self, student: UUID, teacher: UUID) -> Unlinked:
        """One statement; the main teacher after it is read past the deleted row (MD-02)."""
        link = teacher_link
        deleted = (
            delete(link)
            .where(link.c.student_id == student, link.c.teacher_id == teacher)
            .returning(link.c.teacher_id)
            .cte("deleted")
        )
        main = (
            select(
                func.jsonb_build_object(
                    "id",
                    account.c.id,
                    "name",
                    account.c.display_name,
                    "moon",
                    account.c.moon_location,
                )
            )
            .join_from(link, account, account.c.id == link.c.teacher_id)
            .where(link.c.student_id == student, link.c.teacher_id != teacher)
            .order_by(link.c.is_primary.desc(), link.c.created_at, link.c.teacher_id)
            .limit(1)
            .scalar_subquery()
            .cast(JSONB)
        )
        stmt = select(exists(select(deleted.c.teacher_id)).label("removed"), main.label("main"))
        async with connection(self._engine) as conn:
            row = (await conn.execute(stmt)).one()
        return Unlinked(row.removed, to_teacher(row.main))
