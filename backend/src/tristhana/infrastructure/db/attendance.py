"""`AttendanceRepository` on Postgres (SC-05, ADR-0039). Each method is one statement.

The reads are the SC-02 window of the class's shala (found from the class id) around the rule
date, so the use case expands the occurrence in the domain. The guards reuse SC-01's
membership codes, enumerated from `can_claim_attendance` and `can_take_attendance`, so the SQL
can't drift from the policy. Staff writes are deltas: a concurrent claim is never lost. No
statement here reads or writes a log.
"""

from collections.abc import Sequence
from datetime import date, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Row,
    and_,
    case,
    cast,
    delete,
    exists,
    func,
    literal,
    not_,
    or_,
    select,
    true,
    union,
    update,
)
from sqlalchemy.dialects.postgresql import ARRAY, aggregate_order_by, insert
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.types import Date, Text, Uuid

from tristhana.application.policies import can_claim_attendance, can_take_attendance
from tristhana.application.ports.attendance import (
    AttendanceTarget,
    Marked,
    RosterPerson,
    RosterRead,
)
from tristhana.application.ports.shalas import Guarded
from tristhana.domain.attendance import (
    PRACTISES_HERE_DAYS,
    REGULAR_DAYS,
    AttendanceState,
    Counts,
    Snapshot,
)
from tristhana.domain.shalas import Membership
from tristhana.infrastructure.db.classes import (  # pyright: ignore[reportPrivateUsage]
    _me,  # pyright: ignore[reportPrivateUsage]
    _window,  # pyright: ignore[reportPrivateUsage]
    _window_stmt,  # pyright: ignore[reportPrivateUsage]
    is_member,
)
from tristhana.infrastructure.db.engine import connection
from tristhana.infrastructure.db.shalas import allowed_codes, guard, member_columns
from tristhana.infrastructure.db.tables import account, shala_class, shala_staff, shala_student
from tristhana.infrastructure.db.tables import class_attendance as _A
from tristhana.infrastructure.db.tables import shala as _S

_REACH = timedelta(days=12)  # a move (±6) then a swap (±6) from the rule date
_UUIDS = ARRAY(Uuid())
_CONFIRMED = AttendanceState.CONFIRMED.value
_CLAIMED = AttendanceState.CLAIMED.value


def _shala_of(class_id: UUID) -> Any:
    return select(shala_class.c.shala_id).where(shala_class.c.id == class_id).scalar_subquery()


def _on(class_id: UUID, key: date) -> tuple[Any, ...]:
    return (_A.c.class_id == class_id, _A.c.occurrence_key == key)


def _mine(me: UUID, class_id: UUID, key: date) -> Any:
    return select(_A.c.state).where(*_on(class_id, key), _A.c.account_id == me).scalar_subquery()


def _counted(class_id: UUID, key: date) -> tuple[Any, ...]:
    return (*_on(class_id, key), is_member(_A.c.shala_id, _A.c.account_id))


def _counts(class_id: UUID, key: date) -> tuple[Any, Any]:
    confirmed = select(func.count()).where(*_counted(class_id, key), _A.c.state == _CONFIRMED)
    claimed = select(func.count()).where(*_counted(class_id, key), _A.c.state == _CLAIMED)
    return (
        confirmed.scalar_subquery().label("n_confirmed"),
        claimed.scalar_subquery().label("n_claimed"),
    )


def _target(row: Row[Any], me: UUID) -> AttendanceTarget | None:
    m = _me(row, row.id, me)
    if m is None:
        return None
    state = None if row.my_state is None else AttendanceState(row.my_state)
    return AttendanceTarget(_window(row, m), state)


def _like(q: str) -> str:
    escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _people(me: UUID, class_id: UUID, key: date, q: str | None, offset: int, limit: int) -> Any:
    """`[{id, name, state, staff, regular}]` of one page (limit + 1 rows, for `more`); empty
    unless `me` is on the shala's staff."""
    shala = _shala_of(class_id)
    is_staff = exists().where(shala_staff.c.shala_id == shala, shala_staff.c.account_id == me)
    here = _A.alias("here")
    ids = union(
        select(shala_student.c.account_id.label("id")).where(shala_student.c.shala_id == shala),
        select(shala_staff.c.account_id).where(
            shala_staff.c.shala_id == shala,
            exists().where(
                here.c.shala_id == shala,
                here.c.account_id == shala_staff.c.account_id,
                here.c.on_date >= key - timedelta(days=PRACTISES_HERE_DAYS),
            ),
        ),
        select(_A.c.account_id).where(*_counted(class_id, key)),
    ).subquery("ids")
    reg = _A.alias("reg")
    regular = exists().where(
        reg.c.class_id == class_id,
        reg.c.account_id == ids.c.id,
        reg.c.occurrence_key >= key - timedelta(days=REGULAR_DAYS),
        reg.c.occurrence_key < key,
    )
    staff = exists().where(shala_staff.c.shala_id == shala, shala_staff.c.account_id == ids.c.id)
    state = select(_A.c.state).where(*_on(class_id, key), _A.c.account_id == ids.c.id)
    state = state.scalar_subquery()
    where: list[Any] = [is_staff]
    if q is not None:
        where.append(account.c.display_name.ilike(_like(q), escape="\\"))
    order = (
        func.coalesce(state == _CLAIMED, False).desc(),
        regular.desc(),
        func.lower(account.c.display_name).asc().nulls_last(),
        ids.c.id,
    )
    page = (
        select(
            ids.c.id,
            account.c.display_name.label("name"),
            state.label("state"),
            staff.label("staff"),
            regular.label("regular"),
            func.row_number().over(order_by=order).label("n"),
        )
        .join_from(ids, account, account.c.id == ids.c.id)
        .where(*where)
        .order_by(*order)
        .offset(offset)
        .limit(limit + 1)
        .subquery("page")
    )
    obj = func.jsonb_build_object(
        literal("id", Text), page.c.id,
        literal("name", Text), page.c.name,
        literal("state", Text), page.c.state,
        literal("staff", Text), page.c.staff,
        literal("regular", Text), page.c.regular,
    )  # fmt: skip
    return (
        select(
            func.coalesce(
                func.jsonb_agg(aggregate_order_by(obj, page.c.n)), func.jsonb_build_array()
            )
        )
        .select_from(page)
        .scalar_subquery()
    )


def _cur(shala: UUID, me: UUID) -> Any:
    return (
        select(_S.c.id, _S.c.owner_id, *member_columns(_S.c.id, me, "me"))
        .where(_S.c.id == shala)
        .cte("cur")
    )


def _membership(row: Row[Any] | None, shala: UUID, me: UUID) -> Membership | None:
    return None if row is None else _me(row, shala, me)


def _snap_values(snap: Snapshot, who: Any, state: Any) -> list[Any]:
    return [
        literal(snap.shala_id, Uuid),
        literal(snap.class_id, Uuid),
        literal(snap.key, Date),
        who,
        state,
        literal(snap.type.value, Text),
        literal(snap.on, Date),
        literal(snap.starts_at),
        literal(snap.zone, Text),
    ]


_COLS = [
    "shala_id",
    "class_id",
    "occurrence_key",
    "account_id",
    "state",
    "class_type",
    "on_date",
    "starts_at",
    "zone",
]


def _refreshed(stmt: Any) -> dict[str, Any]:
    """A re-mark after staff moved the occurrence refreshes the snapshot (the export's time)."""
    snapshot = ("shala_id", "class_type", "on_date", "starts_at", "zone")
    return {c: getattr(stmt.excluded, c) for c in snapshot} | {"updated_at": func.now()}


def _belongs(snap: Snapshot) -> Any:
    return exists().where(
        shala_class.c.id == snap.class_id, shala_class.c.shala_id == snap.shala_id
    )


class SqlAttendanceRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def _one(self, stmt: Any) -> Row[Any] | None:
        async with connection(self._engine) as conn:
            return (await conn.execute(stmt)).one_or_none()

    async def occurrence(self, me: UUID, class_id: UUID, key: date) -> AttendanceTarget | None:
        stmt = (
            _window_stmt(me, key - _REACH, key + _REACH)
            .add_columns(_mine(me, class_id, key).label("my_state"))
            .where(_S.c.id == _shala_of(class_id))
        )
        row = await self._one(stmt)
        return None if row is None else _target(row, me)

    async def roster(
        self, me: UUID, class_id: UUID, key: date, q: str | None, offset: int, limit: int
    ) -> RosterRead | None:
        stmt = (
            _window_stmt(me, key - _REACH, key + _REACH)
            .add_columns(
                _mine(me, class_id, key).label("my_state"),
                _people(me, class_id, key, q, offset, limit).label("people"),
                *_counts(class_id, key),
            )
            .where(_S.c.id == _shala_of(class_id))
        )
        row = await self._one(stmt)
        target = None if row is None else _target(row, me)
        if row is None or target is None:
            return None
        found = [
            RosterPerson(
                UUID(p["id"]),
                p["name"],
                None if p["state"] is None else AttendanceState(p["state"]),
                bool(p["staff"]),
                bool(p["regular"]),
            )
            for p in row.people
        ]
        return RosterRead(
            target,
            tuple(found[:limit]),
            len(found) > limit,
            Counts(row.n_confirmed, row.n_claimed),
        )

    async def claim(
        self, me: UUID, snap: Snapshot, state: AttendanceState
    ) -> Guarded[AttendanceState]:
        cur = _cur(snap.shala_id, me)
        ok = cur.c.me_code.in_(allowed_codes(can_claim_attendance))
        source = select(*_snap_values(snap, literal(me, Uuid), literal(state.value, Text)))
        stmt_ins = insert(_A).from_select(_COLS, source.where(guard(cur, ok), _belongs(snap)))
        written = (
            stmt_ins.on_conflict_do_update(
                constraint="class_attendance_occurrence_key",
                set_={
                    "state": case(
                        (_A.c.state == _CONFIRMED, _A.c.state),
                        else_=stmt_ins.excluded.state,
                    ),
                    **_refreshed(stmt_ins),
                },
            )
            .returning(_A.c.state)
            .cte("written")
        )
        stmt = select(
            cur.c.id, cur.c.owner_id, cur.c.me_roles, cur.c.me_student,
            ok.label("done"), written.c.state,
        ).outerjoin_from(cur, written, true())  # fmt: skip
        row = await self._one(stmt)
        m = _membership(row, snap.shala_id, me)
        if row is None or m is None:
            return Guarded(None, False)
        if not row.done or row.state is None:
            return Guarded(m, False)
        return Guarded(m, True, AttendanceState(row.state))

    async def remove(self, me: UUID, class_id: UUID, key: date) -> bool:
        stmt = delete(_A).where(*_on(class_id, key), _A.c.account_id == me).returning(_A.c.id)
        async with connection(self._engine) as conn:
            return bool((await conn.execute(stmt)).all())

    async def mark(
        self,
        me: UUID,
        snap: Snapshot,
        present: Sequence[UUID],
        removed: Sequence[UUID],
        confirm_claims: bool,
    ) -> Guarded[Marked]:
        cur = _cur(snap.shala_id, me)
        ok = cur.c.me_code.in_(allowed_codes(can_take_attendance))
        yes, no = list(present), list(removed)
        p = (
            func.unnest(cast(literal(yes, _UUIDS), _UUIDS))
            .table_valued("id")
            .render_derived(name="p")
        )
        stranger = (
            select(p.c.id)
            .where(
                not_(
                    or_(
                        exists().where(
                            shala_student.c.shala_id == snap.shala_id,
                            shala_student.c.account_id == p.c.id,
                        ),
                        exists().where(
                            shala_staff.c.shala_id == snap.shala_id,
                            shala_staff.c.account_id == p.c.id,
                        ),
                    )
                )
            )
            .exists()
        )
        valid = not_(stranger)
        gate = and_(guard(cur, ok), valid, _belongs(snap))
        before = (
            select(
                func.coalesce(
                    func.jsonb_agg(
                        func.jsonb_build_object(
                            literal("id", Text), _A.c.account_id, literal("state", Text), _A.c.state
                        )
                    ),
                    func.jsonb_build_array(),
                )
            )
            .where(*_counted(snap.class_id, snap.key))
            .scalar_subquery()
        )
        columns: list[Any] = [
            cur.c.id,
            cur.c.owner_id,
            cur.c.me_roles,
            cur.c.me_student,
            ok.label("done"),
            valid.label("valid"),
            before.label("before"),
        ]
        empty = cast([], _UUIDS)

        def ids(cte: Any, name: str) -> Any:
            agg = func.coalesce(func.array_agg(cte.c.account_id), empty)
            return select(agg).select_from(cte).scalar_subquery().label(name)

        if no:
            gone = (
                delete(_A)
                .where(*_on(snap.class_id, snap.key), _A.c.account_id.in_(no), gate)
                .returning(_A.c.account_id)
                .cte("gone")
            )
            columns.append(ids(gone, "gone"))
        if yes:
            source = select(*_snap_values(snap, p.c.id, literal(_CONFIRMED, Text))).where(gate)
            ins = insert(_A).from_select(_COLS, source)
            added = (
                ins.on_conflict_do_update(
                    constraint="class_attendance_occurrence_key",
                    set_={"state": _CONFIRMED, **_refreshed(ins)},
                )
                .returning(_A.c.account_id)
                .cte("added")
            )
            columns.append(ids(added, "added"))
        if confirm_claims:
            touched = [*yes, *no]
            where = [*_on(snap.class_id, snap.key), _A.c.state == _CLAIMED, gate]
            if touched:
                where.append(_A.c.account_id.not_in(touched))
            confirmed = (
                update(_A)
                .where(*where)
                .values(state=_CONFIRMED, updated_at=func.now())
                .returning(_A.c.account_id)
                .cte("confirmed")
            )
            columns.append(ids(confirmed, "confirmed"))
        row = await self._one(select(*columns).select_from(cur))
        m = _membership(row, snap.shala_id, me)
        if row is None or m is None:
            return Guarded(None, False)
        if not row.done:
            return Guarded(m, False)
        states = {UUID(b["id"]): AttendanceState(b["state"]) for b in row.before}
        if not row.valid:
            return Guarded(m, True, Marked(False, _tally(states)))
        for a in getattr(row, "gone", None) or ():
            states.pop(a, None)
        added_ids = frozenset(getattr(row, "added", None) or ())
        for a in (*added_ids, *(getattr(row, "confirmed", None) or ())):
            states[a] = AttendanceState.CONFIRMED
        return Guarded(m, True, Marked(True, _tally(states), added_ids))


def _tally(states: dict[UUID, AttendanceState]) -> Counts:
    confirmed = sum(1 for s in states.values() if s is AttendanceState.CONFIRMED)
    return Counts(confirmed, len(states) - confirmed)
