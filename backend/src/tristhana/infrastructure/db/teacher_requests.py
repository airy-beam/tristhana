"""`TeacherRequestRepository` on Postgres (ID-07, ADR-0046). Each method is one statement.

Three things are joins here, never writes: validity (both membership rows exist, are older
than the request, and the staff row holds the Teacher role), expiry (`created_at` against the
7 days) and "the link wins" (a pair already linked is nobody's waiting request). So leaving,
a removal, a role change and the clock need no cleanup, and a rejoin revives nothing.

`created_at` is the database's clock (the column default), the clock of the membership rows
it is compared with; the `now` arguments only measure the 7 and 30 days from it.

The request row is the lock. Approve, decline, reopen, withdraw and `unlink` each update it,
so two taps at once are serialised by Postgres: the second decides against the first one's
result. The link is inserted from the approval's own `RETURNING`, so a request never makes a
link without becoming approved in the same statement.
"""

from datetime import date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Row, and_, case, delete, exists, func, literal, or_, select, true, update
from sqlalchemy.dialects.postgresql import aggregate_order_by, insert
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

from tristhana.application.policies import can_ask_teacher
from tristhana.application.ports.export import AccountGone
from tristhana.application.ports.shalas import Guarded
from tristhana.application.ports.storage import StorageUnavailable
from tristhana.application.ports.teacher_requests import (
    Answer,
    Answered,
    ApprovedAll,
    Asked,
    AskedTeacher,
    Choices,
    DueClosing,
    MyRequests,
    TeacherChoice,
    WaitingPage,
    WaitingRequest,
    Withdrawn,
)
from tristhana.domain.locale import DEFAULT_LOCALE, LOCALES, Locale
from tristhana.domain.shalas import Membership, ShalaRole
from tristhana.domain.teacher_requests import (
    ANSWER_WITHIN,
    KEEP,
    AskState,
    RequestCaps,
    RequestState,
    ask_state,
    closing_due,
)
from tristhana.infrastructure.db.engine import connection, constraint_name, sqlstate
from tristhana.infrastructure.db.notifications import MAX_ATTEMPTS, STALE_CLAIM
from tristhana.infrastructure.db.shalas import (
    PAIR,
    code_of,
    every_membership,
    member_columns,
    membership_of,
)
from tristhana.infrastructure.db.tables import (
    account,
    identity,
    notification_delivery,
    notification_settings,
    shala_staff,
    shala_student,
    teacher_link,
    teacher_request,
)
from tristhana.infrastructure.db.tables import shala as _S

_R = teacher_request
_OPEN = (RequestState.WAITING.value, RequestState.DECLINED.value)
_WAITING, _DECLINED, _APPROVED, _WITHDRAWN = (
    RequestState.WAITING.value,
    RequestState.DECLINED.value,
    RequestState.APPROVED.value,
    RequestState.WITHDRAWN.value,
)
_LINK_STUDENT_GONE = "teacher_link_student_id_fkey"
_LINK_TEACHER_GONE = "teacher_link_teacher_id_fkey"
_REQUEST_TEACHER_GONE = "teacher_request_teacher_id_fkey"
_REQUEST_SHALA_GONE = "teacher_request_shala_id_fkey"
_ASK_PAIRS = [
    code_of(actor) * PAIR + code_of(target)
    for actor in every_membership()
    for target in every_membership()
    if can_ask_teacher(actor, target)
]


# The joins every read carries


def _linked(r: Any) -> Any:
    link = teacher_link
    return exists().where(link.c.student_id == r.c.student_id, link.c.teacher_id == r.c.teacher_id)


def _student_valid(r: Any) -> Any:
    """Still the membership the request was made under: a rejoin makes a newer row."""
    member = shala_student
    return exists().where(
        member.c.shala_id == r.c.shala_id,
        member.c.account_id == r.c.student_id,
        member.c.created_at <= r.c.created_at,
    )


def _teacher_valid(r: Any) -> Any:
    """The asked side of `can_ask_teacher`: on the staff, with the Teacher role, since
    before the request. An owner counts only with the role, so the owner bit is not read
    (`test_db_teacher_requests.py` pins this to the policy over every membership)."""
    member = shala_staff
    return exists().where(
        member.c.shala_id == r.c.shala_id,
        member.c.account_id == r.c.teacher_id,
        member.c.created_at <= r.c.created_at,
        member.c.roles.contains([ShalaRole.TEACHER.value]),
    )


def _inside(r: Any, now: datetime) -> Any:
    return r.c.created_at > now - ANSWER_WITHIN


def _student_sees(r: Any, now: datetime) -> Any:
    """`waiting_for_student`, while the student is still in the shala: a quiet no and a
    teacher who lost the role both still wait."""
    return and_(r.c.state.in_(_OPEN), _inside(r, now), _student_valid(r), ~_linked(r))


def _teacher_sees(r: Any, now: datetime) -> Any:
    """`waiting_for_teacher`, while valid."""
    return and_(
        r.c.state == _WAITING,
        _inside(r, now),
        _student_valid(r),
        _teacher_valid(r),
        ~_linked(r),
    )


def _open(r: Any, now: datetime) -> Any:
    """`answerable`, while valid: a yes still makes the link, a no can be taken back."""
    return and_(r.c.state.in_(_OPEN), _inside(r, now), _student_valid(r), _teacher_valid(r))


def _count(table: Any, *where: Any) -> Any:
    return select(func.count()).select_from(table).where(*where).scalar_subquery()


def _waiting_for(teacher: UUID, now: datetime) -> Any:
    y = _R.alias("y")
    return _count(y, y.c.teacher_id == teacher, _teacher_sees(y, now))


def _people(build: Any, order: Any, source: Any, *where: Any) -> Any:
    """`[{…}]` in `order`, as one correlated scalar subquery (as `shalas._ordered_staff`)."""
    return (
        select(
            func.coalesce(
                func.jsonb_agg(aggregate_order_by(build, *order)), func.jsonb_build_array()
            )
        )
        .select_from(source)
        .where(*where)
        .scalar_subquery()
    )


def _locale(value: str) -> Locale:
    return value if value in LOCALES else DEFAULT_LOCALE  # type: ignore[return-value]


def _target(row: Row[Any], shala: UUID, teacher: UUID) -> Membership | None:
    if row.t_roles is not None:
        roles = frozenset(ShalaRole(r) for r in row.t_roles)
        return Membership(shala, row.owner_id == teacher, roles, False)
    if row.t_student:
        return Membership(shala, False, frozenset(), True)
    return None


def _left(row: Any) -> int:
    """How many wait for the teacher after a tap: the count as the statement saw it, with
    this row taken off or put back as the tap (or one that got there first) left it."""
    counted = bool(row.open) and not row.linked
    was = counted and row.before == _WAITING
    now = counted and row.after == _WAITING
    return row.waiting - int(was) + int(now)


class SqlTeacherRequestRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def choices(self, shala: UUID, me: UUID, now: datetime) -> Choices | None:
        staff, teacher = shala_staff, account.alias("teacher")
        kept = _R.alias("kept")
        offer = _people(
            func.jsonb_build_object("id", teacher.c.id, "name", teacher.c.display_name),
            (staff.c.created_at, staff.c.account_id),
            staff.join(teacher, teacher.c.id == staff.c.account_id),
            staff.c.shala_id == _S.c.id,
            staff.c.roles.contains([ShalaRole.TEACHER.value]),
            ~exists().where(
                teacher_link.c.student_id == me, teacher_link.c.teacher_id == staff.c.account_id
            ),
            ~exists().where(
                kept.c.student_id == me,
                kept.c.teacher_id == staff.c.account_id,
                kept.c.created_at > now - KEEP,
            ),
        )
        x, asked = _R.alias("x"), account.alias("asked")
        waiting = _people(
            func.jsonb_build_object("id", asked.c.id, "name", asked.c.display_name),
            (x.c.created_at, x.c.teacher_id),
            x.join(asked, asked.c.id == x.c.teacher_id),
            x.c.student_id == me,
            x.c.shala_id == _S.c.id,
            _student_sees(x, now),
        )
        is_student = exists().where(
            shala_student.c.shala_id == _S.c.id, shala_student.c.account_id == me
        )
        stmt = select(_S.c.id, _S.c.name, offer.label("offer"), waiting.label("waiting")).where(
            _S.c.id == shala, is_student
        )
        async with connection(self._engine) as conn:
            row = (await conn.execute(stmt)).one_or_none()
        if row is None:
            return None
        return Choices(
            row.id,
            row.name,
            tuple(TeacherChoice(UUID(t["id"]), t["name"]) for t in row.offer),
            tuple(TeacherChoice(UUID(t["id"]), t["name"]) for t in row.waiting),
        )

    async def ask(
        self,
        shala: UUID,
        me: UUID,
        teacher: UUID,
        asked_on: date,
        agreed: bool,
        caps: RequestCaps,
        now: datetime,
    ) -> Guarded[Asked]:
        earlier, x, asked = _R.alias("earlier"), _R.alias("x"), account.alias("asked")
        link = teacher_link
        cur = (
            select(
                _S.c.id,
                _S.c.owner_id,
                _S.c.name,
                *member_columns(_S.c.id, me, "me"),
                *member_columns(_S.c.id, teacher, "t"),
                exists()
                .where(link.c.student_id == me, link.c.teacher_id == teacher)
                .label("linked"),
                earlier.c.state.label("earlier_state"),
                earlier.c.created_at.label("earlier_at"),
                _student_valid(earlier).label("earlier_valid"),
                _count(x, x.c.student_id == me, _student_sees(x, now)).label("my_waiting"),
                _count(link, link.c.student_id == me).label("my_teachers"),
                _waiting_for(teacher, now).label("their_waiting"),
                _count(link, link.c.teacher_id == teacher).label("their_students"),
                asked.c.display_name,
                asked.c.locale,
                identity.c.provider_user_id,
            )
            .select_from(_S)
            .outerjoin(earlier, and_(earlier.c.student_id == me, earlier.c.teacher_id == teacher))
            .outerjoin(asked, asked.c.id == teacher)
            .outerjoin(
                identity,
                and_(identity.c.account_id == teacher, identity.c.provider == "telegram"),
            )
            .where(_S.c.id == shala)
            .cte("cur")
        )
        # The SQL of `ask_state(...) is CREATED`; the DB tests run both over every cap.
        free = and_(
            (cur.c.me_code * PAIR + cur.c.t_code).in_(_ASK_PAIRS),
            ~cur.c.linked,
            or_(cur.c.earlier_at.is_(None), cur.c.earlier_at <= now - KEEP),
            cur.c.my_waiting < caps.asking,
            cur.c.my_teachers + cur.c.my_waiting < caps.teachers,
            cur.c.their_waiting < caps.waiting,
            cur.c.their_students + cur.c.their_waiting < caps.students,
        )
        new = insert(_R).from_select(
            ["student_id", "teacher_id", "shala_id", "asked_on", "quiet_note_agreed"],
            select(
                literal(me), literal(teacher), cur.c.id, literal(asked_on), literal(agreed)
            ).where(free),
        )
        added = (
            # A row past its 30 days is recycled here, so the rule never waits for the prune.
            # A new `id`: the ledger may still hold the old request's note under the old key.
            new.on_conflict_do_update(
                index_elements=[_R.c.student_id, _R.c.teacher_id],
                set_={
                    "id": func.gen_random_uuid(),
                    "shala_id": new.excluded.shala_id,
                    "state": _WAITING,
                    "asked_on": new.excluded.asked_on,
                    "quiet_note_agreed": new.excluded.quiet_note_agreed,
                    "created_at": func.now(),
                },
                where=_R.c.created_at <= now - KEEP,
            )
            .returning(_R.c.student_id)
            .cte("added")
        )
        stmt = select(*cur.c, exists(select(added.c.student_id)).label("created"))
        student = Membership(shala, False, frozenset(), True)
        try:
            async with connection(self._engine) as conn:
                row = (await conn.execute(stmt)).one_or_none()
        except DBAPIError as e:
            # The asked teacher, or the shala, was deleted mid-tap. The asker's own deletion
            # is `AccountGone` (`is_account_gone` knows the student's key).
            if sqlstate(e) == "23503" and constraint_name(e) == _REQUEST_TEACHER_GONE:
                return Guarded(student, False)
            if sqlstate(e) == "23503" and constraint_name(e) == _REQUEST_SHALA_GONE:
                return Guarded(None, False)
            raise
        if row is None:
            return Guarded(None, False)
        membership = membership_of(row, row.id, row.owner_id, me)
        if membership is None:
            return Guarded(None, False)
        if not can_ask_teacher(membership, _target(row, shala, teacher)):
            return Guarded(membership, False)
        if row.created:
            state = AskState.CREATED
        else:
            had = row.earlier_state is not None
            state = ask_state(
                linked=row.linked,
                earlier=(RequestState(row.earlier_state), row.earlier_at) if had else None,
                now=now,
                my_waiting=row.my_waiting,
                my_teachers=row.my_teachers,
                their_waiting=row.their_waiting,
                their_students=row.their_students,
                caps=caps,
                still_valid=row.earlier_valid,
            )
            if state is AskState.CREATED:  # the other tap of a double tap made the row
                state = AskState.WAITING
        asked_value = Asked(
            state,
            row.display_name,
            _locale(row.locale),
            row.provider_user_id,
            row.name,
            row.their_waiting + (1 if row.created else 0),
        )
        return Guarded(membership, True, asked_value)

    async def withdraw(self, me: UUID, teacher: UUID) -> Withdrawn:
        link = teacher_link
        changed = (
            update(_R)
            .where(_R.c.student_id == me, _R.c.teacher_id == teacher, _R.c.state.in_(_OPEN))
            .values(state=_WITHDRAWN)
            .returning(_R.c.id)
            .cte("changed")
        )
        stmt = select(
            exists(select(changed.c.id)).label("removed"),
            exists().where(link.c.student_id == me, link.c.teacher_id == teacher).label("linked"),
        )
        async with connection(self._engine) as conn:
            row = (await conn.execute(stmt)).one()
        return Withdrawn(row.removed, row.linked)

    async def mine(self, me: UUID, now: datetime) -> MyRequests:
        x, teacher = _R.alias("x"), account.alias("teacher")
        asked = _people(
            func.jsonb_build_object(
                "teacher_id",
                x.c.teacher_id,
                "name",
                teacher.c.display_name,
                "shala_id",
                _S.c.id,
                "shala_name",
                _S.c.name,
            ),
            (x.c.created_at, x.c.teacher_id),
            x.join(teacher, teacher.c.id == x.c.teacher_id).join(_S, _S.c.id == x.c.shala_id),
            x.c.student_id == me,
            _student_sees(x, now),
        )
        stmt = select(asked.label("asked"), _waiting_for(me, now).label("waiting"))
        async with connection(self._engine) as conn:
            row = (await conn.execute(stmt)).one()
        return MyRequests(
            tuple(
                AskedTeacher(UUID(a["teacher_id"]), a["name"], UUID(a["shala_id"]), a["shala_name"])
                for a in row.asked
            ),
            row.waiting,
        )

    async def waiting(
        self, me: UUID, now: datetime, offset: int, limit: int, student: UUID | None = None
    ) -> WaitingPage:
        x, asker = _R.alias("x"), account.alias("asker")
        only = () if student is None else (x.c.student_id == student,)
        page = (
            select(
                x.c.student_id,
                asker.c.display_name.label("name"),
                _S.c.id.label("shala_id"),
                _S.c.name.label("shala_name"),
                x.c.created_at,
            )
            .select_from(
                x.join(asker, asker.c.id == x.c.student_id).join(_S, _S.c.id == x.c.shala_id)
            )
            .where(x.c.teacher_id == me, _teacher_sees(x, now), *only)
            .order_by(x.c.created_at, x.c.student_id)
            .offset(offset)
            .limit(limit)
            .subquery("page")
        )
        listed = _people(
            func.jsonb_build_object(
                "student_id",
                page.c.student_id,
                "name",
                page.c.name,
                "shala_id",
                page.c.shala_id,
                "shala_name",
                page.c.shala_name,
            ),
            (page.c.created_at, page.c.student_id),
            page,
        )
        stmt = select(
            listed.label("page"),
            _waiting_for(me, now).label("total"),
            func.now().label("as_of"),  # the clock `created_at` is on: `approve_all` compares
        )
        async with connection(self._engine) as conn:
            row = (await conn.execute(stmt)).one()
        return WaitingPage(
            tuple(
                WaitingRequest(
                    UUID(p["student_id"]), p["name"], UUID(p["shala_id"]), p["shala_name"]
                )
                for p in row.page
            ),
            row.total,
            row.as_of,
        )

    async def approve(self, me: UUID, student: UUID, caps: RequestCaps, now: datetime) -> Answer:
        link = teacher_link
        fits = and_(
            _count(link, link.c.student_id == student) < caps.teachers,
            _count(link, link.c.teacher_id == me) < caps.students,
        )
        row = await self._tap(
            me, student, now, _APPROVED, and_(_open(_R, now), ~_linked(_R), fits), fits
        )
        if row is None:
            return Answer(Answered.GONE)
        left = _left(row)
        if row.linked:
            return Answer(Answered.ALREADY, row.name, left)
        if row.after == _APPROVED:
            # Not `added`: the other tap of a double tap made the link a moment ago.
            return Answer(Answered.DONE if row.added else Answered.ALREADY, row.name, left)
        if row.after not in _OPEN or not row.open:
            return Answer(Answered.GONE, None, left)
        if not row.fits:
            return Answer(Answered.FULL, row.name, left)
        return Answer(Answered.GONE, None, left)

    async def approve_all(
        self, me: UUID, before: datetime, caps: RequestCaps, now: datetime
    ) -> ApprovedAll:
        link, x = teacher_link, _R.alias("x")
        able = (
            select(
                x.c.student_id,
                func.row_number().over(order_by=(x.c.created_at, x.c.student_id)).label("n"),
            )
            .where(
                x.c.teacher_id == me,
                _teacher_sees(x, now),  # never a declined one
                x.c.created_at < before,  # nobody who asked after the list was drawn
                _count(link, link.c.student_id == x.c.student_id) < caps.teachers,
            )
            .cte("able")
        )
        room = literal(caps.students) - _count(link, link.c.teacher_id == me)
        flipped = (
            update(_R)
            .where(
                _R.c.teacher_id == me,
                _R.c.state == _WAITING,
                _R.c.student_id.in_(select(able.c.student_id).where(able.c.n <= room)),
            )
            .values(state=_APPROVED)
            .returning(_R.c.student_id, _R.c.asked_on, _R.c.quiet_note_agreed)
            .cte("flipped")
        )
        added = (
            insert(link)
            .from_select(
                ["student_id", "teacher_id", "linked_on", "quiet_note_agreed"],
                select(
                    flipped.c.student_id,
                    literal(me),
                    flipped.c.asked_on,
                    flipped.c.quiet_note_agreed,
                ),
            )
            .on_conflict_do_nothing()
            .returning(link.c.student_id)
            .cte("added")
        )
        stmt = select(
            select(func.count()).select_from(flipped).scalar_subquery().label("approved"),
            select(func.count()).select_from(added).scalar_subquery().label("added"),
            _waiting_for(me, now).label("waiting"),  # as it was before this statement
        )
        for _ in range(2):
            async with connection(self._engine) as conn:
                try:
                    row = (await conn.execute(stmt)).one()
                except DBAPIError as e:
                    if sqlstate(e) != "23503":
                        raise
                    if constraint_name(e) == _LINK_TEACHER_GONE:
                        raise AccountGone from e
                    if constraint_name(e) != _LINK_STUDENT_GONE:
                        raise
                    continue  # one student vanished mid-tap: their request went with them
            return ApprovedAll(row.approved, row.waiting - row.approved)
        raise StorageUnavailable("approve_all")

    async def decline(self, me: UUID, student: UUID, now: datetime) -> Answer:
        return await self._set(me, student, now, _WAITING, _DECLINED)

    async def reopen(self, me: UUID, student: UUID, now: datetime) -> Answer:
        return await self._set(me, student, now, _DECLINED, _WAITING)

    async def due(self, now: datetime, limit: int) -> list[DueClosing]:
        student, teacher = account.alias("student"), account.alias("teacher")
        d, settings, link = notification_delivery, notification_settings, teacher_link
        linked = _linked(_R)
        in_ledger = exists().where(
            d.c.account_id == _R.c.student_id,
            d.c.dedupe_key == func.concat("req:", _R.c.id),  # `request_key`
            or_(
                d.c.status.in_(("sent", "blocked")),
                and_(d.c.status == "failed", d.c.attempts >= MAX_ATTEMPTS),
                and_(d.c.status == "claimed", d.c.updated_at >= func.now() - STALE_CLAIM),
            ),
        )
        reachable = or_(
            settings.c.unreachable_at.is_(None), settings.c.unreachable_at < student.c.last_seen_at
        )
        stmt = (
            select(
                _R.c.id,
                _R.c.state,
                _R.c.created_at,
                _R.c.student_id,
                _R.c.teacher_id,
                _R.c.shala_id,
                linked.label("linked"),
                student.c.locale,
                student.c.timezone,
                identity.c.provider_user_id,
                teacher.c.display_name.label("teacher_name"),
                _count(link, link.c.student_id == _R.c.student_id).label("my_teachers"),
            )
            .select_from(
                _R.join(student, student.c.id == _R.c.student_id)
                .join(teacher, teacher.c.id == _R.c.teacher_id)
                .join(
                    identity,
                    and_(
                        identity.c.account_id == _R.c.student_id,
                        identity.c.provider == "telegram",
                    ),
                )
                .outerjoin(settings, settings.c.account_id == _R.c.student_id)
            )
            .where(
                _R.c.created_at > now - KEEP,
                # `closing_due`: confirmed with the link, no answer from day 7 without one.
                or_(
                    and_(_R.c.state == _APPROVED, linked),
                    and_(_R.c.state.in_(_OPEN), ~linked, _R.c.created_at <= now - ANSWER_WITHIN),
                ),
                _student_valid(_R),  # someone who left the shala gets no note
                reachable,
                ~in_ledger,
            )
            .order_by(_R.c.created_at, _R.c.student_id)
            .limit(limit)
        )
        async with connection(self._engine) as conn:
            rows = (await conn.execute(stmt)).all()
        out: list[DueClosing] = []
        for row in rows:
            closing = closing_due(RequestState(row.state), row.created_at, row.linked, now)
            if closing is None:
                continue
            out.append(
                DueClosing(
                    id=row.id,
                    closing=closing,
                    student_id=row.student_id,
                    telegram_id=row.provider_user_id,
                    locale=_locale(row.locale),
                    zone=row.timezone,
                    teacher_id=row.teacher_id,
                    teacher_name=row.teacher_name,
                    shala_id=row.shala_id,
                    my_teachers=row.my_teachers,
                )
            )
        return out

    async def prune(self, before: datetime) -> int:
        stmt = delete(_R).where(_R.c.created_at <= before)
        async with connection(self._engine) as conn:
            return (await conn.execute(stmt)).rowcount

    async def _set(self, me: UUID, student: UUID, now: datetime, was: str, to: str) -> Answer:
        """Decline (`waiting` to `declined`) and its Undo: both only inside the 7 days and
        while valid, both idempotent, and neither ever touches a link."""
        when = and_(_R.c.state == was, _open(_R, now), ~_linked(_R))
        row = await self._tap(me, student, now, to, when)
        if row is None:
            return Answer(Answered.GONE)
        left = _left(row)
        if row.linked or row.after == _APPROVED:
            return Answer(Answered.ALREADY, row.name, left)
        if row.after != to or not row.open:
            return Answer(Answered.GONE, None, left)
        return Answer(Answered.DONE, row.name, left)

    async def _tap(
        self, me: UUID, student: UUID, now: datetime, to: str, when: Any, fits: Any = None
    ) -> Any:
        """A teacher's tap, in one statement: the pair's row moves to `to` if `when` holds,
        and the answer reads what the row was (`before`, `open`), whether the two were
        linked, how many waited, and the state the row is left in (`after`).

        The UPDATE takes the row whatever its state and decides in a CASE, so its
        `RETURNING` is the state after any tap that held the row's lock first: a second
        "Yes" finds `approved`, a "Yes" that lost to a withdrawal finds `withdrawn`. A WHERE
        on the state would return nothing in both cases, and the two could not be told
        apart.

        With `fits` (the approval), the link is inserted from that `RETURNING`: `linked_on`
        is the request's `asked_on`, the consent is copied and never set, `is_primary` keeps
        its default. None: no such request, and no link.

        A 23503 on the link's student key means the student vanished mid-tap: caught inside
        the connection block and answered as None ("gone"), or `connection` would report the
        teacher's own account as deleted. The teacher's key is the caller: `AccountGone`."""
        link, f, asker = teacher_link, _R.alias("f"), account.alias("asker")
        found = (
            select(f.c.state, _open(f, now).label("open"), asker.c.display_name.label("name"))
            .select_from(f.join(asker, asker.c.id == f.c.student_id))
            .where(f.c.teacher_id == me, f.c.student_id == student)
            .cte("found")
        )
        moved = (
            update(_R)
            .where(_R.c.teacher_id == me, _R.c.student_id == student)
            .values(state=case((when, to), else_=_R.c.state))
            .returning(_R.c.state, _R.c.student_id, _R.c.asked_on, _R.c.quiet_note_agreed)
            .cte("moved")
        )
        approval: tuple[Any, ...] = ()
        if fits is not None:
            added = (
                insert(link)
                .from_select(
                    ["student_id", "teacher_id", "linked_on", "quiet_note_agreed"],
                    select(
                        moved.c.student_id,
                        literal(me),
                        moved.c.asked_on,
                        moved.c.quiet_note_agreed,
                    ).where(
                        moved.c.state == _APPROVED,
                        # Only a request that was answerable when this tap began: an old
                        # "Yes" on an approved row never makes a link.
                        exists(select(found.c.state).where(found.c.open)),
                    ),
                )
                .on_conflict_do_nothing()
                .returning(link.c.student_id)
                .cte("added")
            )
            approval = (fits.label("fits"), exists(select(added.c.student_id)).label("added"))
        one = select(literal(1).label("one")).subquery("one")
        stmt = select(
            found.c.state.label("before"),
            found.c.open,
            found.c.name,
            exists().where(link.c.student_id == student, link.c.teacher_id == me).label("linked"),
            _waiting_for(me, now).label("waiting"),
            select(moved.c.state).scalar_subquery().label("after"),
            *approval,
        ).select_from(one.outerjoin(found, true()))
        async with connection(self._engine) as conn:
            try:
                row = (await conn.execute(stmt)).one()
            except DBAPIError as e:
                if sqlstate(e) != "23503":
                    raise
                if constraint_name(e) == _LINK_STUDENT_GONE:
                    return None
                if constraint_name(e) == _LINK_TEACHER_GONE:
                    raise AccountGone from e
                raise
        if row.before is None and not row.linked:
            return None
        return row
