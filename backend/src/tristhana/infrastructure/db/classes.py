"""`ScheduleRepository` on Postgres (SC-02, ADR-0034). Each method is one statement.

The guards reuse SC-01's membership codes, enumerated from `can_manage_schedule`, so the SQL
can't drift from the policy. The window read returns the shala's settings and every row that
shapes [start-7, end+7] as jsonb aggregates; expansion happens in the domain. A teacher who is
not on the shala's staff fails the composite FK: that is an invalid class, not a crash.
"""

from datetime import date, time, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Row,
    and_,
    cast,
    delete,
    exists,
    extract,
    func,
    literal,
    null,
    or_,
    select,
    true,
    update,
)
from sqlalchemy.dialects.postgresql import ARRAY, aggregate_order_by, insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.types import Date, Integer, SmallInteger, Text, Time, Uuid

from tristhana.application.policies import can_manage_schedule
from tristhana.application.ports.classes import (
    ClassCaps,
    ClassDraft,
    MyWindows,
    ScheduleWindow,
    StoredClass,
)
from tristhana.application.ports.shalas import Guarded
from tristhana.domain.attendance import AttendanceState, Counts
from tristhana.domain.classes import (
    ClassType,
    Closure,
    InvalidClass,
    MoonPolicy,
    Override,
    OverrideStatus,
    Swap,
)
from tristhana.domain.moon import MoonDayKind
from tristhana.domain.shalas import Membership
from tristhana.infrastructure.db.accounts import from_mask, to_mask
from tristhana.infrastructure.db.engine import connection
from tristhana.infrastructure.db.shalas import (
    allowed_codes,
    guard,
    member_columns,
    membership_of,
    staff_json,
)
from tristhana.infrastructure.db.tables import (
    class_attendance,
    moon_day,
    shala_class,
    shala_closure,
    shala_staff,
    shala_student,
    shala_swap,
    teacher_link,
)
from tristhana.infrastructure.db.tables import shala as _S
from tristhana.infrastructure.db.tables import shala_class_override as _O

_UUIDS = ARRAY(Uuid())


def _by_date(column: Any) -> Any:
    return aggregate_order_by(column, moon_day.c.date)


_MARGIN = timedelta(days=13)  # a move (±6) then a swap (±6), as the domain
_CHANGES = ("moved_to", "start_time", "minutes", "teacher_id")  # an override's changes
_C = shala_class


def _manage() -> list[int]:
    return allowed_codes(can_manage_schedule)


def _cur(shala: UUID, me: UUID) -> Any:
    return (
        select(_S.c.id, _S.c.owner_id, *member_columns(_S.c.id, me, "me"))
        .where(_S.c.id == shala)
        .cte("cur")
    )


def _allowed(cur: Any) -> Any:
    return guard(cur, cur.c.me_code.in_(_manage()))


def _me(row: Row[Any] | None, shala: UUID, me: UUID) -> Membership | None:
    return None if row is None else membership_of(row, shala, row.owner_id, me)


def _side(cur: Any) -> tuple[Any, ...]:
    """The caller's side and whether the policy allows the write (no `id`: a written row's
    columns come next)."""
    return (
        cur.c.owner_id,
        cur.c.me_roles,
        cur.c.me_student,
        cur.c.me_code.in_(_manage()).label("done"),
    )


def _produces(on: Any, starts_on: date, ends_on: date | None, weekdays: int, every: int) -> Any:
    """SQL: the rule (as literals) produces the date `on` (`domain.classes.rule_dates`)."""
    in_range = on >= starts_on if ends_on is None else and_(on >= starts_on, on <= ends_on)
    if weekdays == 0:
        return on == starts_on
    anchor = starts_on - timedelta(days=starts_on.weekday())
    dow = cast(extract("isodow", on), Integer)
    weeks = cast(on - literal(anchor, Date), Integer) // 7  # integer division
    return and_(
        in_range,
        (literal(weekdays, Integer).op("&")(literal(1, Integer).op("<<")(dow - 1))) != 0,
        weeks % every == 0,
    )


def _class_values(draft: ClassDraft) -> dict[str, Any]:
    return {
        "type": draft.type.value,
        "title": draft.title,
        "online": draft.online,
        "city": draft.city,
        "teacher_id": draft.teacher_id,
        "start_time": draft.start,
        "minutes": draft.minutes,
        "weekdays": to_mask(draft.weekdays) or 0,
        "every": draft.every,
        "starts_on": draft.starts_on,
        "ends_on": draft.ends_on,
    }


_CLASS_COLS = (
    _C.c.id,
    _C.c.type,
    _C.c.title,
    _C.c.online,
    _C.c.city,
    _C.c.teacher_id,
    _C.c.start_time,
    _C.c.minutes,
    _C.c.weekdays,
    _C.c.every,
    _C.c.starts_on,
    _C.c.ends_on,
)


def _stored(r: Any) -> StoredClass:
    """From a row, or from a jsonb object (dates and times as ISO strings)."""

    def get(name: str) -> Any:
        return r[name] if isinstance(r, dict) else getattr(r, name)  # pyright: ignore[reportUnknownVariableType]

    def day(v: Any) -> date | None:
        return date.fromisoformat(v) if isinstance(v, str) else v

    start = get("start_time")
    teacher = get("teacher_id")
    return StoredClass(
        id=UUID(str(get("id"))),
        type=ClassType(get("type")),
        title=get("title"),
        online=get("online"),
        city=get("city"),
        teacher_id=None if teacher is None else UUID(str(teacher)),
        start=time.fromisoformat(start) if isinstance(start, str) else start,
        minutes=get("minutes"),
        weekdays=from_mask(get("weekdays")) or frozenset(),
        every=get("every"),
        starts_on=day(get("starts_on")),  # type: ignore[arg-type]
        ends_on=day(get("ends_on")),
    )


def _agg(*pairs: Any) -> Any:
    """`jsonb_agg` of objects; keys as typed text (asyncpg can't type a bare parameter)."""
    typed = [literal(p, Text) if isinstance(p, str) else p for p in pairs]
    return func.coalesce(func.jsonb_agg(func.jsonb_build_object(*typed)), func.jsonb_build_array())


def _classes_json(shala: Any, lo: date | None = None, hi: date | None = None) -> Any:
    where = [_C.c.shala_id == shala]
    if lo is not None and hi is not None:
        where += [_C.c.starts_on <= hi, or_(_C.c.ends_on.is_(None), _C.c.ends_on >= lo)]
    pairs: list[Any] = []
    for col in _CLASS_COLS:
        pairs += [col.name, col]
    return select(_agg(*pairs)).where(*where).scalar_subquery()


def _invalid(e: IntegrityError) -> InvalidClass:
    return InvalidClass(type(e.orig).__name__ if e.orig is not None else "integrity")


def _window_stmt(me: UUID, start: date, end: date, attendance: bool = True) -> Any:
    """Every row that shapes [start-13, end+13] for a shala, the caller's side included; the
    caller adds the shala filter. `attendance=False` (the ICS feed) skips the SC-05 reads."""
    lo, hi = start - _MARGIN, end + _MARGIN
    overrides = (
        select(
            _agg(
                "class_id", _O.c.class_id,
                "on_date", _O.c.on_date,
                "status", _O.c.status,
                "moved_to", _O.c.moved_to,
                "start_time", _O.c.start_time,
                "minutes", _O.c.minutes,
                "teacher_id", _O.c.teacher_id,
            )
        )
        .where(_O.c.shala_id == _S.c.id, _O.c.on_date.between(lo, hi))
        .scalar_subquery()
    )  # fmt: skip
    closures = (
        select(
            _agg(
                "id", shala_closure.c.id,
                "start", shala_closure.c.start_date,
                "end", shala_closure.c.end_date,
            )
        )
        .where(
            shala_closure.c.shala_id == _S.c.id,
            shala_closure.c.end_date >= lo,
            shala_closure.c.start_date <= hi,
        )
        .scalar_subquery()
    )  # fmt: skip
    swaps = (
        select(_agg("from", shala_swap.c.from_date, "to", shala_swap.c.to_date))
        .where(
            shala_swap.c.shala_id == _S.c.id,
            or_(shala_swap.c.from_date.between(lo, hi), shala_swap.c.to_date.between(lo, hi)),
        )
        .scalar_subquery()
    )
    moon = (
        select(func.coalesce(func.jsonb_agg(moon_day.c.date), func.jsonb_build_array()))
        .where(
            moon_day.c.location == func.coalesce(_S.c.moon_city, _S.c.city),
            moon_day.c.date.between(lo, hi),
        )
        .scalar_subquery()
    )
    return select(
        *(_attendance_columns(me, lo, hi) if attendance else _no_attendance()),
        _S.c.id,
        _S.c.owner_id,
        _S.c.name,
        _S.c.city,
        _S.c.moon_city,
        _S.c.moon_policy,
        _S.c.days_off,
        *member_columns(_S.c.id, me, "me"),
        _classes_json(_S.c.id, lo, hi).label("classes"),
        overrides.label("overrides"),
        closures.label("closures"),
        swaps.label("swaps"),
        moon.label("moon"),
        staff_json(_S.c.id).label("staff"),
    )


def is_member(shala: Any, who: Any) -> Any:
    """A current student or staff member. Reads count only these: a claim racing a leave can
    insert after the leave's delete (READ COMMITTED), and that stray row stays invisible."""
    return or_(
        exists().where(shala_student.c.shala_id == shala, shala_student.c.account_id == who),
        exists().where(shala_staff.c.shala_id == shala, shala_staff.c.account_id == who),
    )


def _no_attendance() -> tuple[Any, ...]:
    return (
        func.jsonb_build_array().label("att_mine"),
        func.jsonb_build_array().label("att_counts"),
    )


def _attendance_columns(me: UUID, lo: date, hi: date) -> tuple[Any, ...]:
    """SC-05: my marks in the window, and for staff the counts per (class, rule date)."""
    a = class_attendance
    in_window = (
        a.c.shala_id == _S.c.id,
        a.c.class_id.is_not(None),
        a.c.occurrence_key.between(lo, hi),
    )
    mine = (
        select(_agg("class_id", a.c.class_id, "key", a.c.occurrence_key, "state", a.c.state))
        .where(*in_window, a.c.account_id == me)
        .scalar_subquery()
    )
    confirmed = a.c.state == AttendanceState.CONFIRMED.value
    grouped = (
        select(
            a.c.class_id,
            a.c.occurrence_key,
            func.count().filter(confirmed).label("confirmed"),
            func.count().filter(~confirmed).label("claimed"),
        )
        .where(
            *in_window,
            # Correlated by hand: inside this derived table an EXISTS does not see the outer
            # `shala` by itself, it would cross-join it and mean "staff of any shala".
            exists()
            .where(shala_staff.c.shala_id == _S.c.id, shala_staff.c.account_id == me)
            .correlate(_S),
            is_member(a.c.shala_id, a.c.account_id),
        )
        .group_by(a.c.class_id, a.c.occurrence_key)
        .correlate(_S)
        .subquery("g")
    )
    counts = select(
        _agg(
            "class_id", grouped.c.class_id,
            "key", grouped.c.occurrence_key,
            "confirmed", grouped.c.confirmed,
            "claimed", grouped.c.claimed,
        )
    ).scalar_subquery()  # fmt: skip
    return (mine.label("att_mine"), counts.label("att_counts"))


def _window(row: Row[Any], m: Membership) -> ScheduleWindow:
    return ScheduleWindow(
        me=m,
        shala_id=row.id,
        name=row.name,
        city=row.city,
        moon_city=row.moon_city,
        moon_policy=MoonPolicy(row.moon_policy),
        days_off=from_mask(row.days_off) or None,
        classes=tuple(_stored(c) for c in row.classes),
        overrides={
            (UUID(o["class_id"]), date.fromisoformat(o["on_date"])): _override(o)
            for o in row.overrides
        },
        closures=tuple(
            Closure(UUID(c["id"]), date.fromisoformat(c["start"]), date.fromisoformat(c["end"]))
            for c in row.closures
        ),
        swaps=tuple(
            Swap(date.fromisoformat(s["from"]), date.fromisoformat(s["to"])) for s in row.swaps
        ),
        moon=frozenset(date.fromisoformat(d) for d in row.moon),
        staff={UUID(s["id"]): s["name"] for s in row.staff},
        mine={
            (UUID(x["class_id"]), date.fromisoformat(x["key"])): AttendanceState(x["state"])
            for x in row.att_mine
        },
        counts={
            (UUID(x["class_id"]), date.fromisoformat(x["key"])): Counts(
                x["confirmed"], x["claimed"]
            )
            for x in row.att_counts
        }
        if m.staff
        else {},
    )


class SqlScheduleRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def _one(self, stmt: Any) -> Row[Any] | None:
        try:
            async with connection(self._engine) as conn:
                return (await conn.execute(stmt)).one_or_none()
        except IntegrityError as e:  # a teacher not on the staff, a taken swap day
            raise _invalid(e) from e

    async def window(self, shala: UUID, me: UUID, start: date, end: date) -> ScheduleWindow | None:
        row = await self._one(_window_stmt(me, start, end).where(_S.c.id == shala))
        m = _me(row, shala, me)
        if row is None or m is None:
            return None
        return _window(row, m)

    async def member_windows(
        self,
        me: UUID,
        start: date,
        end: date,
        staff_only: bool = False,
        moon_city: str | None = None,
        moon_end: date | None = None,
        moon_start: date | None = None,
        attendance: bool = True,
    ) -> MyWindows:
        """One statement: a base row of my teacher ids and my moon dates, the windows of my
        shalas joined to it (none: one row of NULLs)."""
        staff = exists().where(shala_staff.c.shala_id == _S.c.id, shala_staff.c.account_id == me)
        member = staff
        if not staff_only:
            member = or_(
                staff,
                exists().where(
                    shala_student.c.shala_id == _S.c.id, shala_student.c.account_id == me
                ),
            )
        windows = _window_stmt(me, start, end, attendance).where(member).subquery("w")
        teachers = (
            select(func.coalesce(func.array_agg(teacher_link.c.teacher_id), cast([], _UUIDS)))
            .where(teacher_link.c.student_id == me)
            .scalar_subquery()
        )
        in_range = (
            moon_day.c.location == moon_city,
            moon_day.c.date.between(moon_start or start, moon_end or end),
        )
        moon = (
            select(func.coalesce(func.array_agg(_by_date(moon_day.c.date)), cast([], ARRAY(Date))))
            .where(*in_range)
            .scalar_subquery()
        )
        kinds = (
            select(func.coalesce(func.array_agg(_by_date(moon_day.c.kind)), cast([], ARRAY(Text))))
            .where(*in_range)
            .scalar_subquery()
        )  # the same rows, both ordered by date: they zip
        base = select(
            teachers.label("my_teachers"), moon.label("my_moon"), kinds.label("my_moon_kinds")
        ).subquery("base")
        stmt = (
            select(base, windows)
            .select_from(base)
            .outerjoin(windows, true())
            .order_by(windows.c.me_roles.is_(None), windows.c.name, windows.c.id)
        )
        async with connection(self._engine) as conn:
            rows = (await conn.execute(stmt)).all()
        found = ((r, _me(r, r.id, me)) for r in rows if r.id is not None)
        first = rows[0]
        return MyWindows(
            windows=tuple(_window(r, m) for r, m in found if m is not None),
            teachers=frozenset(first.my_teachers or ()),
            my_moon=frozenset(first.my_moon or ()),
            my_moon_kinds={
                d: MoonDayKind(k)
                for d, k in zip(first.my_moon or (), first.my_moon_kinds or (), strict=True)
            },
        )

    async def classes_of(self, shala: UUID, me: UUID) -> Guarded[tuple[StoredClass, ...]]:
        cur = _cur(shala, me)
        stmt = select(*_side(cur), _classes_json(cur.c.id).label("classes"))
        row = await self._one(stmt)
        m = _me(row, shala, me)
        if row is None or m is None or not row.done:
            return Guarded(m, False)
        found = sorted((_stored(c) for c in row.classes), key=lambda c: (c.starts_on, c.start))
        return Guarded(m, True, tuple(found))

    async def _write(
        self, shala: UUID, me: UUID, cur: Any, write: Any, *extra: Any
    ) -> tuple[Membership | None, bool, Row[Any] | None]:
        """`write` is a CTE gated by `_allowed(cur)`, its row (if any) joined in; `wrote` says
        whether it wrote. Returns (me, done, row)."""
        wrote = exists(select(literal(1)).select_from(write)).label("wrote")
        stmt = select(*_side(cur), *write.c, wrote, *extra).outerjoin_from(cur, write, true())
        row = await self._one(stmt)
        m = _me(row, shala, me)
        return m, bool(row is not None and m is not None and row.done), row

    async def create(
        self, shala: UUID, me: UUID, draft: ClassDraft, caps: ClassCaps, today: date
    ) -> Guarded[StoredClass]:
        cur = _cur(shala, me)
        live = (
            select(func.count())
            .select_from(_C)
            .where(_C.c.shala_id == shala, or_(_C.c.ends_on.is_(None), _C.c.ends_on >= today))
            .scalar_subquery()
        )
        values = _class_values(draft)
        added = (
            insert(_C)
            .from_select(
                ["shala_id", *values],
                select(
                    literal(shala), *(literal(v, _C.c[k].type) for k, v in values.items())
                ).where(_allowed(cur), live < caps.classes),
            )
            .returning(*_CLASS_COLS)
            .cte("added")
        )
        m, done, row = await self._write(shala, me, cur, added)
        if not done or row is None:
            return Guarded(m, False)
        return Guarded(m, True, _stored(row) if row.wrote else None)

    async def update(
        self, shala: UUID, me: UUID, class_id: UUID, draft: ClassDraft, from_date: date | None
    ) -> Guarded[StoredClass]:
        if from_date is not None:
            split = await self._split(shala, me, class_id, draft, from_date)
            if split.value is not None or not split.done:
                return split
            # The series starts on or after `from` (or is one date): all dates change.
        cur = _cur(shala, me)
        values = _class_values(draft)
        changed = (
            update(_C)
            .where(_C.c.id == class_id, _C.c.shala_id == shala, _allowed(cur))
            .values(**values, updated_at=func.now())
            .returning(*_CLASS_COLS)
            .cte("changed")
        )
        stale = (
            delete(_O)
            .where(
                _O.c.class_id == class_id,
                _O.c.shala_id == shala,
                _allowed(cur),
                ~_produces(
                    _O.c.on_date, draft.starts_on, draft.ends_on, values["weekdays"], draft.every
                ),
            )
            .returning(_O.c.class_id)
            .cte("stale")
        )
        dropped = select(func.count()).select_from(stale).scalar_subquery().label("dropped")
        m, done, row = await self._write(shala, me, cur, changed, dropped)
        if not done or row is None:
            return Guarded(m, False)
        return Guarded(m, True, _stored(row) if row.wrote else None)

    async def _split(
        self, shala: UUID, me: UUID, class_id: UUID, draft: ClassDraft, from_date: date
    ) -> Guarded[StoredClass]:
        """The old series ends the day before `from`; a new one starts on it and takes the
        overrides on or after it that its rule produces (the rest are deleted)."""
        cur = _cur(shala, me)
        values = _class_values(draft) | {"starts_on": from_date}
        ended = (
            update(_C)
            .where(
                _C.c.id == class_id,
                _C.c.shala_id == shala,
                _C.c.starts_on < from_date,
                _C.c.weekdays > 0,
                _allowed(cur),
            )
            .values(
                ends_on=func.least(
                    func.coalesce(_C.c.ends_on, from_date - timedelta(days=1)),
                    from_date - timedelta(days=1),
                ),
                updated_at=func.now(),
            )
            .returning(_C.c.id)
            .cte("ended")
        )
        added = (
            insert(_C)
            .from_select(
                ["shala_id", *values],
                select(
                    literal(shala), *(literal(v, _C.c[k].type) for k, v in values.items())
                ).where(exists(select(ended.c.id))),
            )
            .returning(*_CLASS_COLS)
            .cte("added")
        )
        produced = _produces(
            _O.c.on_date, from_date, draft.ends_on, to_mask(draft.weekdays) or 0, draft.every
        )
        later = and_(_O.c.class_id == class_id, _O.c.on_date >= from_date)
        moved = (
            update(_O)
            .where(later, produced, exists(select(ended.c.id)))
            .values(class_id=select(added.c.id).scalar_subquery(), updated_at=func.now())
            .returning(_O.c.on_date)
            .cte("moved")
        )
        dropped = (
            delete(_O)
            .where(later, ~produced, exists(select(ended.c.id)))
            .returning(_O.c.on_date)
            .cte("dropped")
        )
        m, done, row = await self._write(
            shala,
            me,
            cur,
            added,
            select(func.count()).select_from(moved).scalar_subquery().label("moved"),
            select(func.count()).select_from(dropped).scalar_subquery().label("dropped"),
        )
        if not done or row is None:
            return Guarded(m, False)
        return Guarded(m, True, _stored(row) if row.wrote else None)

    async def delete(self, shala: UUID, me: UUID, class_id: UUID) -> Guarded[None]:
        cur = _cur(shala, me)
        gone = (
            delete(_C)
            .where(_C.c.id == class_id, _C.c.shala_id == shala, _allowed(cur))
            .returning(_C.c.id)
            .cte("gone")
        )
        m, done, _ = await self._write(shala, me, cur, gone)
        return Guarded(m, done)

    async def set_override(
        self, shala: UUID, me: UUID, class_id: UUID, override: Override, keep: bool = False
    ) -> Guarded[bool]:
        cur = _cur(shala, me)
        o = override
        values = {
            "class_id": class_id,
            "on_date": o.on_date,
            "shala_id": shala,
            "status": None if o.status is None else o.status.value,
            "moved_to": o.moved_to,
            "start_time": o.start,
            "minutes": o.minutes,
            "teacher_id": o.teacher_id,
        }
        types = {"moved_to": Date, "start_time": Time, "minutes": SmallInteger, "on_date": Date}
        source = select(
            *(
                (null() if v is None else literal(v, types.get(k))).label(k)
                if k not in ("class_id", "shala_id")
                else literal(v).label(k)
                for k, v in values.items()
            )
        ).where(exists().where(_C.c.id == class_id, _C.c.shala_id == shala), _allowed(cur))
        stmt_insert = insert(_O).from_select(list(values), source)
        upsert = (
            stmt_insert.on_conflict_do_update(
                index_elements=[_O.c.class_id, _O.c.on_date],
                set_={
                    "status": stmt_insert.excluded.status,
                    # `keep` (the bot's quick hold) leaves a move, a time and a substitute.
                    **({} if keep else {k: stmt_insert.excluded[k] for k in _CHANGES}),
                    "updated_at": func.now(),
                },
            )
            .returning(_O.c.class_id)
            .cte("upserted")
        )
        m, done, row = await self._write(shala, me, cur, upsert)
        if not done or row is None:
            return Guarded(m, False)
        return Guarded(m, True, bool(row.wrote))

    async def clear_override(
        self, shala: UUID, me: UUID, class_id: UUID, on_date: date
    ) -> Guarded[None]:
        cur = _cur(shala, me)
        gone = (
            delete(_O)
            .where(
                _O.c.class_id == class_id,
                _O.c.on_date == on_date,
                _O.c.shala_id == shala,
                _allowed(cur),
            )
            .returning(_O.c.class_id)
            .cte("gone")
        )
        m, done, _ = await self._write(shala, me, cur, gone)
        return Guarded(m, done)

    async def add_closure(
        self, shala: UUID, me: UUID, start: date, end: date, caps: ClassCaps, today: date
    ) -> Guarded[Closure]:
        cur = _cur(shala, me)
        future = (
            select(func.count())
            .select_from(shala_closure)
            .where(shala_closure.c.shala_id == shala, shala_closure.c.end_date >= today)
            .scalar_subquery()
        )
        added = (
            insert(shala_closure)
            .from_select(
                ["shala_id", "start_date", "end_date"],
                select(literal(shala), literal(start, Date), literal(end, Date)).where(
                    _allowed(cur), future < caps.closures
                ),
            )
            .returning(shala_closure.c.id.label("closure_id"), shala_closure.c.start_date,
                       shala_closure.c.end_date)
            .cte("added")
        )  # fmt: skip
        m, done, row = await self._write(shala, me, cur, added)
        if not done or row is None:
            return Guarded(m, False)
        if not row.wrote:
            return Guarded(m, True, None)
        return Guarded(m, True, Closure(row.closure_id, row.start_date, row.end_date))

    async def remove_closure(self, shala: UUID, me: UUID, closure: UUID) -> Guarded[None]:
        cur = _cur(shala, me)
        gone = (
            delete(shala_closure)
            .where(shala_closure.c.id == closure, shala_closure.c.shala_id == shala, _allowed(cur))
            .returning(shala_closure.c.id)
            .cte("gone")
        )
        m, done, _ = await self._write(shala, me, cur, gone)
        return Guarded(m, done)

    async def add_swap(
        self, shala: UUID, me: UUID, swap: Swap, caps: ClassCaps, today: date
    ) -> Guarded[Swap]:
        cur = _cur(shala, me)
        future = (
            select(func.count())
            .select_from(shala_swap)
            .where(shala_swap.c.shala_id == shala, shala_swap.c.from_date >= today)
            .scalar_subquery()
        )
        stmt_insert = insert(shala_swap).from_select(
            ["shala_id", "from_date", "to_date"],
            select(
                literal(shala), literal(swap.from_date, Date), literal(swap.to_date, Date)
            ).where(_allowed(cur), future < caps.swaps),
        )
        added = (
            stmt_insert.on_conflict_do_update(
                index_elements=[shala_swap.c.shala_id, shala_swap.c.from_date],
                set_={"to_date": stmt_insert.excluded.to_date},
            )
            .returning(shala_swap.c.from_date, shala_swap.c.to_date)
            .cte("added")
        )
        m, done, row = await self._write(shala, me, cur, added)
        if not done or row is None:
            return Guarded(m, False)
        if not row.wrote:
            return Guarded(m, True, None)
        return Guarded(m, True, Swap(row.from_date, row.to_date))

    async def remove_swap(self, shala: UUID, me: UUID, from_date: date) -> Guarded[None]:
        cur = _cur(shala, me)
        gone = (
            delete(shala_swap)
            .where(
                shala_swap.c.shala_id == shala,
                shala_swap.c.from_date == from_date,
                _allowed(cur),
            )
            .returning(shala_swap.c.from_date)
            .cte("gone")
        )
        m, done, _ = await self._write(shala, me, cur, gone)
        return Guarded(m, done)


def _override(o: dict[str, Any]) -> Override:
    start, moved, teacher = o["start_time"], o["moved_to"], o["teacher_id"]
    return Override(
        on_date=date.fromisoformat(o["on_date"]),
        status=None if o["status"] is None else OverrideStatus(o["status"]),
        moved_to=None if moved is None else date.fromisoformat(moved),
        start=None if start is None else time.fromisoformat(start),
        minutes=o["minutes"],
        teacher_id=None if teacher is None else UUID(teacher),
    )
