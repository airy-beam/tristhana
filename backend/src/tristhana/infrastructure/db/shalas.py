"""`ShalaRepository` on Postgres (SC-01, ADR-0033). Each method is one statement.

The SQL guards don't restate the policies: a membership is reduced to a small code (four role
bits, the owner bit, the student bit) and each guard allows exactly the codes for which the
policy in `application/policies.py` says yes, enumerated in Python. So the two can't drift.
Joins and staff accepts run after a per-person advisory lock, so a person can't end up both
staff and student of one shala when two taps race (each statement would miss the other's row).
"""

from collections.abc import Callable, Iterable
from dataclasses import replace
from datetime import date, datetime
from functools import cache
from itertools import combinations
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Row,
    and_,
    case,
    delete,
    exists,
    false,
    func,
    literal,
    null,
    or_,
    select,
    true,
    union_all,
    update,
)
from sqlalchemy.dialects.postgresql import ARRAY, insert
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.types import Text

from tristhana.application.policies import (
    can_delete_shala,
    can_edit_shala,
    can_invite_staff,
    can_remove_staff,
    can_remove_student,
    can_rotate_join_link,
    can_set_roles,
    can_show_join_link,
    can_view_shala_students,
)
from tristhana.application.ports.shalas import (
    Guarded,
    Joined,
    MemberLookup,
    MyShala,
    NewShala,
    ShalaCaps,
    ShalaCard,
    ShalaPreview,
    ShalaStudent,
    StaffAccepted,
    StaffInvite,
    StaffMember,
    StaffPreview,
    StudentsPage,
)
from tristhana.domain.classes import MoonPolicy
from tristhana.domain.locale import DEFAULT_LOCALE, LOCALES
from tristhana.domain.shalas import KEEP, JoinState, Membership, ShalaPatch, ShalaRole
from tristhana.infrastructure.db.accounts import from_mask, to_mask
from tristhana.infrastructure.db.engine import connection
from tristhana.infrastructure.db.tables import (
    account,
    identity,
    shala_staff,
    shala_staff_invite,
    shala_student,
)
from tristhana.infrastructure.db.tables import shala as _S

_ROLE_BITS = {
    ShalaRole.ADMIN: 1,
    ShalaRole.TEACHER: 2,
    ShalaRole.ASSISTANT: 4,
    ShalaRole.OFFICE: 8,
}
_OWNER_BIT, _STUDENT_CODE = 16, 32
_PAIR = 64  # actor code * 64 + target code
_LOCK_KEY = 0x5348414C  # "SHAL"
_ROLES_TYPE = ARRAY(Text())


# Membership codes


def _code_of(m: Membership) -> int:
    if m.student:
        return _STUDENT_CODE
    return (_OWNER_BIT if m.owner else 0) + sum(_ROLE_BITS[r] for r in m.roles)


@cache
def _memberships() -> tuple[Membership, ...]:
    """Every membership there can be: staff (owner or not, any roles) and a student."""
    shala_id = UUID(int=0)
    roles = list(ShalaRole)
    staff = [
        Membership(shala_id, owner, frozenset(chosen), False)
        for owner in (False, True)
        for n in range(len(roles) + 1)
        for chosen in combinations(roles, n)
    ]
    return (*staff, Membership(shala_id, False, frozenset(), True))


def _allowed(policy: Callable[[Membership], bool]) -> list[int]:
    return [_code_of(m) for m in _memberships() if policy(m)]


@cache
def _allowed_pairs(name: str, roles: frozenset[ShalaRole] | None, own: bool) -> list[int]:
    out: list[int] = []
    for a in _memberships():
        for t in _memberships():
            if name == "set_roles":
                ok = can_set_roles(a, t, roles or frozenset())
            else:
                ok = can_remove_staff(a, t, own=own)
            if ok:
                out.append(_code_of(a) * _PAIR + _code_of(t))
    return out


def _code_expr(owner: Any, roles: Any, student: Any) -> Any:
    """The same code in SQL: NULL = not a member."""
    bits = sum(
        (case((roles.contains([role.value]), bit), else_=0) for role, bit in _ROLE_BITS.items()),
        start=case((owner, _OWNER_BIT), else_=0),
    )
    return case((roles.is_not(None), bits), (student, _STUDENT_CODE), else_=null())


def _member(shala_id: Any, who: Any, name: str) -> Any:
    """One person's side of the shala in `shala_id`: roles (NULL if not staff), student."""
    roles = (
        select(shala_staff.c.roles)
        .where(shala_staff.c.shala_id == shala_id, shala_staff.c.account_id == who)
        .scalar_subquery()
    )
    student = exists().where(
        shala_student.c.shala_id == shala_id, shala_student.c.account_id == who
    )
    owner = _S.c.owner_id == who
    return (
        roles.label(f"{name}_roles"),
        student.label(f"{name}_student"),
        _code_expr(owner, roles, student).label(f"{name}_code"),
    )


def _membership(row: Row[Any], shala_id: UUID, owner_id: UUID, me: UUID) -> Membership | None:
    if row.me_roles is not None:
        roles = frozenset(ShalaRole(r) for r in row.me_roles)
        return Membership(shala_id, owner_id == me, roles, False)
    if row.me_student:
        return Membership(shala_id, False, frozenset(), True)
    return None


# The card


def _student_count(shala_id: Any) -> Any:
    return (
        select(func.count())
        .select_from(shala_student)
        .where(shala_student.c.shala_id == shala_id)
        .scalar_subquery()
    )


def _card_columns() -> tuple[Any, ...]:
    return (
        _S.c.id,
        _S.c.name,
        _S.c.city,
        _S.c.moon_city,
        _S.c.online,
        _S.c.owner_id,
        _S.c.days_off,
        _S.c.moon_policy,
        _ordered_staff(_S.c.id).label("staff"),
        _student_count(_S.c.id).label("students_total"),
    )


def _ordered_staff(shala_id: Any) -> Any:
    """`[{id, name, roles}]`, oldest first."""
    inner = (
        select(
            account.c.id,
            account.c.display_name.label("name"),
            shala_staff.c.roles,
            shala_staff.c.created_at,
        )
        .select_from(shala_staff.join(account, account.c.id == shala_staff.c.account_id))
        .where(shala_staff.c.shala_id == shala_id)
        .order_by(shala_staff.c.created_at, shala_staff.c.account_id)
        .subquery()
    )
    return (
        select(
            func.coalesce(
                func.jsonb_agg(
                    func.jsonb_build_object(
                        "id", inner.c.id, "name", inner.c.name, "roles", inner.c.roles
                    )
                ),
                func.jsonb_build_array(),
            )
        )
        .select_from(inner)
        .scalar_subquery()
    )


def _staff_members(found: Iterable[dict[str, Any]], owner_id: UUID) -> tuple[StaffMember, ...]:
    out: list[StaffMember] = []
    for s in found:
        member = UUID(s["id"])
        roles = frozenset(ShalaRole(r) for r in s["roles"])
        out.append(StaffMember(member, s["name"], member == owner_id, roles))
    return tuple(out)


def _card(row: Row[Any], me: Membership, staff: tuple[StaffMember, ...] | None = None) -> ShalaCard:
    return ShalaCard(
        id=row.id,
        name=row.name,
        city=row.city,
        moon_city=row.moon_city,
        online=row.online,
        owner_id=row.owner_id,
        staff=_staff_members(row.staff, row.owner_id) if staff is None else staff,
        students_total=row.students_total,
        me=me,
        days_off=from_mask(row.days_off) or None,
        moon_policy=MoonPolicy(row.moon_policy),
    )


def _roles(roles: Iterable[ShalaRole]) -> list[str]:
    return sorted(r.value for r in roles)


def _inviter_may(role: Any, inviter_code: Any) -> Any:
    """A staff link works only while its inviter may still grant its role (review fix): a
    removed or demoted manager's pending links die with their rights."""
    return or_(
        *(
            and_(role == r.value, inviter_code.in_(_allowed(lambda m, r=r: can_invite_staff(m, r))))
            for r in ShalaRole
        )
    )


def _if(cur: Any, condition: Any) -> Any:
    """A guard on the one-row `cur` CTE, as EXISTS so the write doesn't join it."""
    return exists(select(cur.c.id).where(condition))


def _lock_id(account_id: UUID) -> int:
    return int.from_bytes(account_id.bytes[:4], "big", signed=True)


class SqlShalaRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def _one(self, stmt: Any) -> Row[Any] | None:
        async with connection(self._engine) as conn:
            return (await conn.execute(stmt)).one_or_none()

    async def _locked(self, account_id: UUID, stmt: Any) -> Row[Any] | None:
        """The lock and the write in one transaction: the write's snapshot is taken after the
        lock, so it sees a racing join or accept of the same person."""
        lock = select(func.pg_advisory_xact_lock(_LOCK_KEY, _lock_id(account_id)))
        async with connection(self._engine) as conn:
            conn = await conn.execution_options(isolation_level="READ COMMITTED")
            async with conn.begin():
                await conn.execute(lock)
                return (await conn.execute(stmt)).one_or_none()

    async def create(
        self, me: UUID, new: NewShala, caps: ShalaCaps, joined_on: date
    ) -> ShalaCard | None:
        owned = select(func.count()).select_from(_S).where(_S.c.owner_id == me)
        staff_of = (
            select(func.count()).select_from(shala_staff).where(shala_staff.c.account_id == me)
        )
        added = (
            insert(_S)
            .from_select(
                ["name", "city", "online", "owner_id", "join_code"],
                select(
                    literal(new.name),
                    literal(new.city),
                    literal(new.online),
                    literal(me),
                    literal(new.join_code),
                ).where(
                    owned.scalar_subquery() < caps.owned,
                    staff_of.scalar_subquery() < caps.staff_of,
                ),
            )
            .returning(_S.c.id, _S.c.name, _S.c.city, _S.c.moon_city, _S.c.online, _S.c.owner_id)
            .cte("added")
        )
        row_roles = literal(_roles(new.roles), _ROLES_TYPE)
        staff = (
            insert(shala_staff)
            .from_select(
                ["shala_id", "account_id", "roles", "joined_on"],
                select(added.c.id, literal(me), row_roles, literal(joined_on)),
            )
            .returning(shala_staff.c.shala_id)
            .cte("staff")
        )
        name = select(account.c.display_name).where(account.c.id == me).scalar_subquery()
        stmt = select(*added.c, name.label("me_name")).where(
            exists().where(staff.c.shala_id == added.c.id)
        )
        row = await self._one(stmt)
        if row is None:
            return None
        membership = Membership(row.id, True, frozenset(new.roles), False)
        return ShalaCard(
            id=row.id,
            name=row.name,
            city=row.city,
            moon_city=row.moon_city,
            online=row.online,
            owner_id=me,
            staff=(StaffMember(me, row.me_name, True, frozenset(new.roles)),),
            students_total=0,
            me=membership,
        )

    async def mine(self, me: UUID) -> tuple[MyShala, ...]:
        staff = select(
            shala_staff.c.shala_id,
            shala_staff.c.roles,
            false().label("student"),
            literal(0).label("side"),
            shala_staff.c.created_at,
        ).where(shala_staff.c.account_id == me)
        students = select(
            shala_student.c.shala_id,
            null().cast(_ROLES_TYPE).label("roles"),
            true().label("student"),
            literal(1).label("side"),
            shala_student.c.created_at,
        ).where(shala_student.c.account_id == me)
        m = union_all(staff, students).subquery("m")
        stmt = (
            select(
                _S.c.id,
                _S.c.name,
                _S.c.city,
                _S.c.online,
                _S.c.owner_id,
                m.c.roles,
                m.c.student,
            )
            .join_from(m, _S, _S.c.id == m.c.shala_id)
            .order_by(m.c.side, m.c.created_at, _S.c.id)
        )
        async with connection(self._engine) as conn:
            rows = (await conn.execute(stmt)).all()
        out: list[MyShala] = []
        for r in rows:
            if r.student:
                membership = Membership(r.id, False, frozenset(), True)
            else:
                roles = frozenset(ShalaRole(x) for x in r.roles)
                membership = Membership(r.id, r.owner_id == me, roles, False)
            out.append(MyShala(r.id, r.name, r.city, r.online, membership))
        return tuple(out)

    async def card(self, shala: UUID, me: UUID) -> ShalaCard | None:
        stmt = select(*_card_columns(), *_member(_S.c.id, me, "me")).where(_S.c.id == shala)
        row = await self._one(stmt)
        if row is None:
            return None
        membership = _membership(row, row.id, row.owner_id, me)
        return None if membership is None else _card(row, membership)

    async def update(self, shala: UUID, me: UUID, patch: ShalaPatch) -> Guarded[ShalaCard]:
        cur = (
            select(*_card_columns(), *_member(_S.c.id, me, "me")).where(_S.c.id == shala).cte("cur")
        )
        values: dict[str, Any] = {
            name: value
            for name in ("name", "city", "online", "moon_city", "moon_policy")
            if (value := getattr(patch, name)) is not KEEP
        }
        if patch.days_off is None or isinstance(patch.days_off, frozenset):
            values["days_off"] = to_mask(patch.days_off or None)
        changed = (
            update(_S)
            .where(_S.c.id == shala, _if(cur, cur.c.me_code.in_(_allowed(can_edit_shala))))
            .values(**values, updated_at=func.now())
            .returning(
                _S.c.name, _S.c.city, _S.c.moon_city, _S.c.online, _S.c.days_off, _S.c.moon_policy
            )
            .cte("changed")
        )
        stmt = select(
            *cur.c,
            changed.c.name.label("new_name"),
            changed.c.city.label("new_city"),
            changed.c.moon_city.label("new_moon_city"),
            changed.c.online.label("new_online"),
            changed.c.days_off.label("new_days_off"),
            changed.c.moon_policy.label("new_moon_policy"),
            exists(select(changed.c.name)).label("done"),
        ).outerjoin_from(cur, changed, true())
        row = await self._one(stmt)
        if row is None:
            return Guarded(None, False)
        membership = _membership(row, row.id, row.owner_id, me)
        if membership is None or not row.done:
            return Guarded(membership, False)
        new = replace(
            _card(row, membership),
            name=row.new_name,
            city=row.new_city,
            moon_city=row.new_moon_city,
            online=row.new_online,
            days_off=from_mask(row.new_days_off) or None,
            moon_policy=MoonPolicy(row.new_moon_policy),
        )
        return Guarded(membership, True, new)

    async def delete(self, shala: UUID, me: UUID) -> Guarded[None]:
        cur = (
            select(_S.c.id, _S.c.owner_id, *_member(_S.c.id, me, "me"))
            .where(_S.c.id == shala)
            .cte("cur")
        )
        gone = (
            delete(_S)
            .where(_S.c.id == shala, _if(cur, cur.c.me_code.in_(_allowed(can_delete_shala))))
            .returning(_S.c.id)
            .cte("gone")
        )
        stmt = select(*cur.c, exists(select(gone.c.id)).label("done"))
        row = await self._one(stmt)
        if row is None:
            return Guarded(None, False)
        return Guarded(_membership(row, row.id, row.owner_id, me), row.done)

    async def students(
        self, shala: UUID, me: UUID, offset: int, limit: int
    ) -> Guarded[StudentsPage]:
        page = (
            select(account.c.id, account.c.display_name.label("name"))
            .select_from(shala_student.join(account, account.c.id == shala_student.c.account_id))
            .where(shala_student.c.shala_id == _S.c.id)
            .order_by(shala_student.c.created_at, shala_student.c.account_id)
            .offset(offset)
            .limit(limit)
            .correlate(_S)
            .subquery("page")
        )
        listed = select(
            func.coalesce(
                func.jsonb_agg(func.jsonb_build_object("id", page.c.id, "name", page.c.name)),
                func.jsonb_build_array(),
            )
        ).scalar_subquery()
        allowed = _code_expr(
            _S.c.owner_id == me,
            select(shala_staff.c.roles)
            .where(shala_staff.c.shala_id == _S.c.id, shala_staff.c.account_id == me)
            .scalar_subquery(),
            false(),
        ).in_(_allowed(can_view_shala_students))
        stmt = select(
            _S.c.id,
            _S.c.owner_id,
            *_member(_S.c.id, me, "me"),
            case((allowed, listed), else_=null()).label("page"),
            _student_count(_S.c.id).label("total"),
        ).where(_S.c.id == shala)
        row = await self._one(stmt)
        if row is None:
            return Guarded(None, False)
        membership = _membership(row, row.id, row.owner_id, me)
        if membership is None or row.page is None:
            return Guarded(membership, False)
        students = tuple(ShalaStudent(UUID(s["id"]), s["name"]) for s in row.page)
        return Guarded(membership, True, StudentsPage(students, row.total))

    async def member(self, shala: UUID, me: UUID, target: UUID) -> MemberLookup | None:
        name = select(account.c.display_name).where(account.c.id == target).scalar_subquery()
        stmt = select(
            *_card_columns(),
            *_member(_S.c.id, me, "me"),
            *_member(_S.c.id, target, "t"),
            name.label("t_name"),
        ).where(_S.c.id == shala)
        row = await self._one(stmt)
        if row is None:
            return None
        membership = _membership(row, row.id, row.owner_id, me)
        if membership is None:
            return None
        card = _card(row, membership)
        if row.t_code is None:
            return MemberLookup(card, False)
        return MemberLookup(card, True, row.t_name, row.t_roles is not None)

    async def preview(self, code: str, me: UUID) -> ShalaPreview | None:
        mine = (
            select(func.count())
            .select_from(shala_student)
            .where(shala_student.c.account_id == me)
            .scalar_subquery()
        )
        stmt = select(
            _S.c.id,
            _S.c.name,
            _S.c.city,
            _S.c.owner_id,
            *_member(_S.c.id, me, "me"),
            _student_count(_S.c.id).label("students"),
            mine.label("mine"),
        ).where(_S.c.join_code == code)
        row = await self._one(stmt)
        if row is None:
            return None
        return ShalaPreview(
            shala_id=row.id,
            name=row.name,
            city=row.city,
            me=_membership(row, row.id, row.owner_id, me),
            students=row.students,
            my_student_of=row.mine,
        )

    async def preview_staff(self, code: str, me: UUID) -> StaffPreview | None:
        invite = shala_staff_invite
        stmt = (
            select(
                _S.c.id,
                _S.c.name,
                _S.c.city,
                _S.c.owner_id,
                invite.c.role,
                account.c.display_name.label("inviter_name"),
                *_member(_S.c.id, me, "me"),
            )
            .select_from(invite.join(_S, _S.c.id == invite.c.shala_id))
            .outerjoin(account, account.c.id == invite.c.created_by)
            .where(
                invite.c.code == code,
                invite.c.expires_at > func.now(),
                _inviter_may(invite.c.role, _member(_S.c.id, invite.c.created_by, "inviter")[2]),
            )
        )
        row = await self._one(stmt)
        if row is None:
            return None
        return StaffPreview(
            shala_id=row.id,
            shala_name=row.name,
            city=row.city,
            role=ShalaRole(row.role),
            inviter_name=row.inviter_name,
            me=_membership(row, row.id, row.owner_id, me),
        )

    async def join(self, code: str, me: UUID, caps: ShalaCaps, joined_on: date) -> Joined | None:
        mine = (
            select(func.count())
            .select_from(shala_student)
            .where(shala_student.c.account_id == me)
            .scalar_subquery()
        )
        found = (
            select(*_card_columns(), *_member(_S.c.id, me, "me"), mine.label("mine"))
            .where(_S.c.join_code == code)
            .cte("found")
        )
        added = (
            insert(shala_student)
            .from_select(
                ["shala_id", "account_id", "joined_on"],
                select(found.c.id, literal(me), literal(joined_on)).where(
                    found.c.me_code.is_(None),
                    found.c.students_total < caps.students,
                    found.c.mine < caps.student_of,
                ),
            )
            .on_conflict_do_nothing()
            .returning(shala_student.c.shala_id)
            .cte("added")
        )
        stmt = select(*found.c, exists(select(added.c.shala_id)).label("created"))
        row = await self._locked(me, stmt)
        if row is None:
            return None
        membership = _membership(row, row.id, row.owner_id, me)
        if row.created:
            student = Membership(row.id, False, frozenset(), True)
            card = _card(row, student)
            total = (row.students_total or 0) + 1
            return Joined(True, JoinState.OPEN, replace(card, students_total=total))
        if membership is not None:
            state = JoinState.STAFF if membership.staff else JoinState.ALREADY
            return Joined(False, state, _card(row, membership))
        return Joined(False, JoinState.FULL, None)

    async def invite_staff(
        self,
        shala: UUID,
        me: UUID,
        role: ShalaRole,
        code: str,
        expires_at: datetime,
        caps: ShalaCaps,
    ) -> Guarded[StaffInvite]:
        live = (
            select(func.count())
            .select_from(shala_staff_invite)
            .where(
                shala_staff_invite.c.shala_id == shala,
                shala_staff_invite.c.expires_at > func.now(),
            )
            .scalar_subquery()
        )
        allowed = _allowed(lambda m: can_invite_staff(m, role))
        cur = (
            select(_S.c.id, _S.c.owner_id, *_member(_S.c.id, me, "me"), live.label("live"))
            .where(_S.c.id == shala)
            .cte("cur")
        )
        added = (
            insert(shala_staff_invite)
            .from_select(
                ["code", "shala_id", "role", "created_by", "expires_at"],
                select(
                    literal(code), cur.c.id, literal(role.value), literal(me), literal(expires_at)
                ).where(cur.c.me_code.in_(allowed), cur.c.live < caps.pending_invites),
            )
            .returning(shala_staff_invite.c.code)
            .cte("added")
        )
        stmt = select(
            *cur.c,
            cur.c.me_code.in_(allowed).label("done"),
            exists(select(added.c.code)).label("created"),
        )
        row = await self._one(stmt)
        if row is None:
            return Guarded(None, False)
        membership = _membership(row, row.id, row.owner_id, me)
        if membership is None or not row.done:
            return Guarded(membership, False)
        return Guarded(membership, True, StaffInvite(code, expires_at) if row.created else None)

    async def accept_staff(
        self, code: str, me: UUID, caps: ShalaCaps, joined_on: date
    ) -> StaffAccepted | None:
        invite = shala_staff_invite
        inviter = account.alias("inviter")
        staff_of = (
            select(func.count())
            .select_from(shala_staff)
            .where(shala_staff.c.account_id == me)
            .scalar_subquery()
        )
        staff_count = (
            select(func.count())
            .select_from(shala_staff)
            .where(shala_staff.c.shala_id == _S.c.id)
            .scalar_subquery()
        )
        found = (
            select(
                *_card_columns(),
                *_member(_S.c.id, me, "me"),
                invite.c.role,
                inviter.c.locale.label("inviter_locale"),
                identity.c.provider_user_id.label("inviter_telegram_id"),
                staff_count.label("staff_count"),
                staff_of.label("staff_of"),
                _member(_S.c.id, invite.c.created_by, "inviter")[2],
                select(account.c.display_name)
                .where(account.c.id == me)
                .scalar_subquery()
                .label("me_name"),
            )
            .select_from(invite.join(_S, _S.c.id == invite.c.shala_id))
            .outerjoin(inviter, inviter.c.id == invite.c.created_by)
            .outerjoin(
                identity,
                and_(
                    identity.c.account_id == invite.c.created_by, identity.c.provider == "telegram"
                ),
            )
            .where(invite.c.code == code, invite.c.expires_at > func.now())
            .cte("found")
        )
        open_ = and_(
            _inviter_may(found.c.role, found.c.inviter_code),
            found.c.me_roles.is_(None),
            found.c.staff_count < caps.staff,
            found.c.staff_of < caps.staff_of,
        )
        spent = (
            delete(invite)
            .where(
                invite.c.code == code,
                invite.c.expires_at > func.now(),
                exists(select(found.c.id).where(open_)),
            )
            .returning(invite.c.shala_id, invite.c.role)
            .cte("spent")
        )
        added = (
            insert(shala_staff)
            .from_select(
                ["shala_id", "account_id", "roles", "joined_on"],
                select(
                    spent.c.shala_id,
                    literal(me),
                    func.array_append(literal([], _ROLES_TYPE), spent.c.role),
                    literal(joined_on),
                ),
            )
            .on_conflict_do_nothing()
            .returning(shala_staff.c.shala_id)
            .cte("added")
        )
        dropped = (
            delete(shala_student)
            .where(
                shala_student.c.account_id == me,
                shala_student.c.shala_id.in_(select(added.c.shala_id)),
            )
            .returning(shala_student.c.shala_id)
            .cte("dropped")
        )
        stmt = select(
            *found.c,
            exists(select(added.c.shala_id)).label("created"),
            exists(select(dropped.c.shala_id)).label("was_student"),
        )
        row = await self._locked(me, stmt)
        if row is None:
            return None
        role = ShalaRole(row.role)
        if row.inviter_code not in _allowed(lambda m: can_invite_staff(m, role)):
            return None  # the inviter can't grant this role any more: a dead link
        locale = row.inviter_locale if row.inviter_locale in LOCALES else DEFAULT_LOCALE
        base: dict[str, Any] = {
            "role": role,
            "inviter_telegram_id": row.inviter_telegram_id,
            "inviter_locale": locale,
        }
        membership = _membership(row, row.id, row.owner_id, me)
        if membership is not None and membership.staff:
            return StaffAccepted(
                False, JoinState.STAFF, _card(row, membership), was_student=False, **base
            )
        if row.staff_count >= caps.staff or row.staff_of >= caps.staff_of:
            return StaffAccepted(False, JoinState.FULL, None, was_student=False, **base)
        if not row.created:
            return None  # spent by a racing tap in the meantime
        mine = Membership(row.id, False, frozenset({role}), False)
        staff = (
            *_staff_members(row.staff, row.owner_id),
            StaffMember(me, row.me_name, False, frozenset({role})),
        )
        card = _card(row, mine, staff)
        total = (row.students_total or 0) - (1 if row.was_student else 0)
        return StaffAccepted(
            True,
            JoinState.OPEN,
            replace(card, students_total=total),
            was_student=row.was_student,
            **base,
        )

    async def set_roles(
        self, shala: UUID, me: UUID, target: UUID, roles: frozenset[ShalaRole]
    ) -> Guarded[ShalaCard]:
        cur = (
            select(*_card_columns(), *_member(_S.c.id, me, "me"), *_member(_S.c.id, target, "t"))
            .where(_S.c.id == shala)
            .cte("cur")
        )
        pair = cur.c.me_code * _PAIR + cur.c.t_code
        changed = (
            update(shala_staff)
            .where(
                shala_staff.c.shala_id == shala,
                shala_staff.c.account_id == target,
                _if(cur, pair.in_(_allowed_pairs("set_roles", roles, False))),
            )
            .values(roles=_roles(roles))
            .returning(shala_staff.c.account_id)
            .cte("changed")
        )
        stmt = select(*cur.c, exists(select(changed.c.account_id)).label("done"))
        row = await self._one(stmt)
        if row is None:
            return Guarded(None, False)
        membership = _membership(row, row.id, row.owner_id, me)
        if membership is None or not row.done:
            return Guarded(membership, False)
        staff = tuple(
            StaffMember(s.id, s.name, s.owner, roles) if s.id == target else s
            for s in _staff_members(row.staff, row.owner_id)
        )
        if target == me:
            membership = Membership(row.id, membership.owner, roles, False)
        return Guarded(membership, True, _card(row, membership, staff))

    async def remove_staff(self, shala: UUID, me: UUID, target: UUID) -> Guarded[None]:
        own = me == target
        cur = (
            select(
                _S.c.id,
                _S.c.owner_id,
                *_member(_S.c.id, me, "me"),
                *_member(_S.c.id, target, "t"),
            )
            .where(_S.c.id == shala)
            .cte("cur")
        )
        pair = cur.c.me_code * _PAIR + cur.c.t_code
        gone = (
            delete(shala_staff)
            .where(
                shala_staff.c.shala_id == shala,
                shala_staff.c.account_id == target,
                _if(cur, pair.in_(_allowed_pairs("remove_staff", None, own))),
            )
            .returning(shala_staff.c.account_id)
            .cte("gone")
        )
        stmt = select(*cur.c, exists(select(gone.c.account_id)).label("done"))
        row = await self._one(stmt)
        if row is None:
            return Guarded(None, False)
        membership = _membership(row, row.id, row.owner_id, me)
        if membership is None:
            return Guarded(None, False)
        if row.t_roles is None:  # already gone: done, if the caller could have done it
            return Guarded(membership, own or can_edit_shala(membership))
        return Guarded(membership, row.done)

    async def remove_student(self, shala: UUID, me: UUID, target: UUID) -> Guarded[None]:
        allowed = _allowed(lambda m: can_remove_student(m, own=me == target))
        cur = (
            select(_S.c.id, _S.c.owner_id, *_member(_S.c.id, me, "me"))
            .where(_S.c.id == shala)
            .cte("cur")
        )
        gone = (
            delete(shala_student)
            .where(
                shala_student.c.shala_id == shala,
                shala_student.c.account_id == target,
                _if(cur, cur.c.me_code.in_(allowed)),
            )
            .returning(shala_student.c.account_id)
            .cte("gone")
        )
        stmt = select(*cur.c, exists(select(gone.c.account_id)).label("removed"))
        row = await self._one(stmt)
        if row is None:
            return Guarded(None, False)
        membership = _membership(row, row.id, row.owner_id, me)
        if membership is None:
            return Guarded(None, False)
        return Guarded(membership, can_remove_student(membership, own=me == target))

    async def join_link(self, shala: UUID, me: UUID) -> Guarded[str]:
        stmt = select(_S.c.id, _S.c.owner_id, _S.c.join_code, *_member(_S.c.id, me, "me")).where(
            _S.c.id == shala
        )
        row = await self._one(stmt)
        if row is None:
            return Guarded(None, False)
        membership = _membership(row, row.id, row.owner_id, me)
        if membership is None or not can_show_join_link(membership):
            return Guarded(membership, False)
        return Guarded(membership, True, row.join_code)

    async def rotate_join(self, shala: UUID, me: UUID, code: str) -> Guarded[str]:
        cur = (
            select(_S.c.id, _S.c.owner_id, *_member(_S.c.id, me, "me"))
            .where(_S.c.id == shala)
            .cte("cur")
        )
        changed = (
            update(_S)
            .where(_S.c.id == shala, _if(cur, cur.c.me_code.in_(_allowed(can_rotate_join_link))))
            .values(join_code=code, updated_at=func.now())
            .returning(_S.c.join_code)
            .cte("changed")
        )
        stmt = select(*cur.c, exists(select(changed.c.join_code)).label("done"))
        row = await self._one(stmt)
        if row is None:
            return Guarded(None, False)
        membership = _membership(row, row.id, row.owner_id, me)
        if membership is None or not row.done:
            return Guarded(membership, False)
        return Guarded(membership, True, code)

    async def prune_invites(self, now: datetime) -> int:
        """Expired staff links (the tick's pruning step)."""
        stmt = (
            delete(shala_staff_invite)
            .where(shala_staff_invite.c.expires_at <= now)
            .returning(shala_staff_invite.c.code)
        )
        async with connection(self._engine) as conn:
            return len((await conn.execute(stmt)).all())


# For the SC-02 schedule and NT-03 announcement repositories: the same membership code
# and guards.
member_columns = _member
membership_of = _membership
allowed_codes = _allowed
guard = _if
staff_json = _ordered_staff
