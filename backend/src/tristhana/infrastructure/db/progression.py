"""`ProgressionRepository` on Postgres (PR-08, ADR-0026). Every method is one statement:
a write appends its event and moves the state row together, guarded by the state's
`last_event_id` and position (compare-and-set), so a double tap or a second device can't fork
it. A teacher's mark is the same write with a link guard (PR-08 Phase 3, ADR-0037)."""

from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Row,
    and_,
    case,
    delete,
    distinct,
    exists,
    false,
    func,
    literal,
    literal_column,
    null,
    or_,
    select,
    update,
)
from sqlalchemy.dialects.postgresql import JSON, aggregate_order_by, insert
from sqlalchemy.ext.asyncio import AsyncEngine

from tristhana.application.ports.progression import (
    MarkLink,
    ProgressionView,
    TeacherMarkView,
    TimelineRead,
)
from tristhana.domain.progression import (
    HISTORY_LIMIT,
    TIMELINE_LIMIT,
    Change,
    Earlier,
    EventKind,
    Marker,
    Position,
    Progression,
    ProgressionEvent,
)
from tristhana.infrastructure.db.engine import connection
from tristhana.infrastructure.db.tables import (
    account,
    identity,
    progression,
    progression_event,
    teacher_link,
)

_ITEM_KINDS = (EventKind.ITEM_GIVEN.value, EventKind.ITEM_REMOVED.value)
_POSITION_KINDS = (EventKind.START.value, EventKind.GIVEN.value, EventKind.CHANGED.value)
_NEXT_ID = "nextval(pg_get_serial_sequence('tristhana.progression_event', 'id'))"
_PREFIX = "progression_"
# Labelled, so the state can join other statements (practice save, presets) without clashes.
_STATE = tuple(
    progression.c[name].label(_PREFIX + name)
    for name in (
        "series", "last_key", "items", "last_event_id", "hint_series", "hint_key",
        "hint_event_id",
    )
)  # fmt: skip


def state_columns() -> tuple[Any, ...]:
    return _STATE


def to_progression(row: Row[*tuple[Any, ...]]) -> Progression | None:
    """None when the joined row is absent (`last_event_id` is set on every stored row)."""

    def col(name: str) -> Any:
        return getattr(row, _PREFIX + name)

    if col("last_event_id") is None:
        return None
    hint = Position(col("hint_series"), col("hint_key")) if col("hint_series") else None
    return Progression(
        Position(col("series"), col("last_key")),
        frozenset(col("items")),
        col("last_event_id"),
        hint,
        col("hint_event_id"),
    )


def _to_event(account_id: UUID, e: dict[str, Any]) -> ProgressionEvent:
    kind = EventKind(e["kind"])
    positional = kind not in (EventKind.ITEM_GIVEN, EventKind.ITEM_REMOVED)
    before = Position(e["from_series"], e["from_key"]) if positional else None
    return ProgressionEvent(
        id=e["id"],
        kind=kind,
        occurred_on=date.fromisoformat(e["occurred_on"]),
        before=None if kind is EventKind.START else before,
        after=Position(e["to_series"], e["to_key"]) if positional else None,
        item=e["item"],
        by=Marker(e["by"]),
        by_name=e["by_name"],
    )


class SqlProgressionRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def get(self, account_id: UUID) -> ProgressionView:
        one = select(literal(1).label("one")).subquery("one")
        stmt = select(*_STATE, *_view_columns(account_id)).select_from(
            one.outerjoin(progression, progression.c.account_id == account_id)
        )
        async with connection(self._engine) as conn:
            row = (await conn.execute(stmt)).one()
        return _view(account_id, row)

    async def timeline(self, account_id: UUID) -> TimelineRead:
        """One statement: the newest `TIMELINE_LIMIT` + 1 events (the extra one only says older
        ones exist), oldest first, with who marked them; plus what every event older than the
        kept window reached, so a cut history replays its first entries honestly."""
        e = progression_event
        mine = e.c.account_id == account_id
        newest = (
            select(*e.c)
            .where(mine)
            .order_by(e.c.id.desc())
            .limit(TIMELINE_LIMIT + 1)
            .subquery("newest")
        )
        # The oldest kept id; NULL (nothing older is read) with fewer events than the limit.
        cutoff = (
            select(e.c.id)
            .where(mine)
            .order_by(e.c.id.desc())
            .offset(TIMELINE_LIMIT - 1)
            .limit(1)
            .scalar_subquery()
        )
        targets, given_items = _earlier_columns(account_id, e.c.id < cutoff)
        stmt = select(
            _events_json(account_id, newest, ascending=True).label("events"), targets, given_items
        )
        async with connection(self._engine) as conn:
            row = (await conn.execute(stmt)).one()
        found = _json(row.events)
        truncated = len(found) > TIMELINE_LIMIT
        if truncated:
            found = found[1:]
        events = tuple(_to_event(account_id, x) for x in found)
        return TimelineRead(events, truncated, _earlier(row) if truncated else Earlier())

    async def for_teacher(self, teacher: UUID, student: UUID) -> TeacherMarkView | None:
        """The link (by its primary key), the student's zone, locale and Telegram id, and their
        view, in one statement; no row = not linked this way."""
        link = (
            select(teacher_link.c.student_id)
            .where(teacher_link.c.student_id == student, teacher_link.c.teacher_id == teacher)
            .cte("link")
        )
        stmt = select(
            account.c.timezone,
            account.c.locale,
            identity.c.provider_user_id.label("telegram_id"),
            *_STATE,
            *_view_columns(student),
        ).select_from(
            link.join(account, account.c.id == link.c.student_id)
            .outerjoin(
                identity,
                and_(
                    identity.c.account_id == link.c.student_id,
                    identity.c.provider == "telegram",
                ),
            )
            .outerjoin(progression, progression.c.account_id == link.c.student_id)
        )
        async with connection(self._engine) as conn:
            row = (await conn.execute(stmt.limit(1))).first()
        if row is None:
            return None
        found = MarkLink(teacher, student, row.timezone, row.locale, row.telegram_id)
        return TeacherMarkView(found, _view(student, row))

    async def apply(
        self,
        account_id: UUID,
        change: Change,
        expected_event_id: int | None,
        marked_by: UUID,
        *,
        before: Position | None,
        link_teacher: UUID | None = None,
    ) -> ProgressionEvent | None:
        p, e = progression, progression_event
        state = change.state
        new_id = select(literal_column(_NEXT_ID, BigInteger).label("id")).cte("new_id")
        source = select(
            literal(account_id, p.c.account_id.type),
            literal(state.position.series, p.c.series.type),
            literal(state.position.key, p.c.last_key.type),
            literal(sorted(state.items), p.c["items"].type),
            new_id.c.id,
        ).select_from(new_id)
        if expected_event_id is not None:
            # The row must still be there (an undone START deletes it). An undo committing
            # after this snapshot can still lose to us and leave a row without its START:
            # two devices racing, harmless (the next read shows a set position).
            source = source.where(exists().where(p.c.account_id == account_id))
        if link_teacher is not None:
            # A teacher's mark (ADR-0037): only while linked, checked in the write's own
            # snapshot. KEY SHARE holds the link row, so an unlink racing us waits for our commit
            # (the mark stands, then the link goes) or wins first (we write nothing).
            link = (
                select(teacher_link.c.student_id)
                .where(
                    teacher_link.c.student_id == account_id,
                    teacher_link.c.teacher_id == link_teacher,
                )
                .with_for_update(read=True, key_share=True)
                .cte("link")
            )
            source = source.where(exists(select(link.c.student_id)))
        guard = p.c.last_event_id.is_not_distinct_from(literal(expected_event_id, BigInteger))
        if before is None:
            guard = and_(guard, false())  # "no stored row": an existing one is never replaced
        else:
            # The position too: after a teacher's mark is undone `last_event_id` stays, so the
            # id alone can't catch a client that saw the mark (ADR-0037).
            guard = and_(
                guard,
                p.c.series.is_not_distinct_from(literal(before.series, p.c.series.type)),
                p.c.last_key.is_not_distinct_from(literal(before.key, p.c.last_key.type)),
            )
        upsert = insert(p).from_select(
            ["account_id", "series", "last_key", "items", "last_event_id"], source
        )
        upsert = upsert.on_conflict_do_update(
            index_elements=[p.c.account_id],
            set_={
                "series": upsert.excluded.series,
                "last_key": upsert.excluded.last_key,
                "items": upsert.excluded["items"],
                "last_event_id": upsert.excluded.last_event_id,
                "updated_at": func.now(),
            },
            # Re-checked on the locked row: the loser of a race updates nothing.
            where=guard,
        )
        moved = upsert.returning(p.c.last_event_id).cte("moved")
        start, after = change.before, change.after
        event = insert(e).from_select(
            [
                "id",
                "account_id",
                "kind",
                "from_series",
                "from_key",
                "to_series",
                "to_key",
                "item",
                "occurred_on",
                "marked_by",
            ],
            select(
                moved.c.last_event_id,
                literal(account_id, e.c.account_id.type),
                literal(change.kind.value, e.c.kind.type),
                literal(start.series if start else None, e.c.from_series.type),
                literal(start.key if start else None, e.c.from_key.type),
                literal(after.series if after else None, e.c.to_series.type),
                literal(after.key if after else None, e.c.to_key.type),
                literal(change.item, e.c.item.type),
                literal(change.occurred_on, e.c.occurred_on.type),
                literal(marked_by, e.c.marked_by.type),
            ).select_from(moved),
        )
        stmt = select(event.returning(e.c.id).cte("event").c.id)
        async with connection(self._engine) as conn:
            event_id = (await conn.execute(stmt)).scalar_one_or_none()
        if event_id is None:
            return None
        by = Marker.SELF if marked_by == account_id else Marker.TEACHER
        return ProgressionEvent(
            event_id, change.kind, change.occurred_on, change.before, after, change.item, by
        )

    async def undo(self, account_id: UUID, event_id: int) -> bool:
        """The latest event, or a teacher's `given` that no later position event moved on from
        (ADR-0037): that one goes back to its `from`, keeps the items and `last_event_id`, and
        clears the "Not new" hint (it was tied to an id that no longer moves)."""
        p, e = progression, progression_event
        # Locked first, so a racing write is either seen here or waits; FOR UPDATE reads the
        # newest version of the row, so a move that just committed is caught by the position.
        current = (
            select(p.c.last_event_id, p.c.series, p.c.last_key)
            .where(p.c.account_id == account_id)
            .with_for_update()
            .cte("current")
        )
        current_last = select(current.c.last_event_id).scalar_subquery()
        later = progression_event.alias("later")
        moved_on = exists().where(
            later.c.account_id == account_id,
            later.c.id > event_id,
            later.c.kind.in_(_POSITION_KINDS),
        )
        held = exists().where(
            current.c.series.is_not_distinct_from(e.c.to_series),
            current.c.last_key.is_not_distinct_from(e.c.to_key),
        )
        retractable = and_(
            e.c.kind == EventKind.GIVEN.value,
            e.c.marked_by.is_distinct_from(account_id),
            ~moved_on,
            held,
        )
        removed = (
            delete(e)
            .where(
                e.c.account_id == account_id,
                e.c.id == event_id,
                exists(select(current.c.last_event_id)),
                or_(e.c.id == current_last, retractable),
            )
            .returning(e.c.id, e.c.account_id, e.c.kind, e.c.from_series, e.c.from_key, e.c.item)
            .cte("removed")
        )
        # The snapshot still has the removed row, so "before it" is `id < event_id`.
        previous = (
            select(func.max(e.c.id))
            .where(e.c.account_id == account_id, e.c.id < event_id)
            .scalar_subquery()
        )
        latest = removed.c.id == p.c.last_event_id
        item_kind = removed.c.kind.in_(_ITEM_KINDS)
        restored = (
            update(p)
            .where(p.c.account_id == removed.c.account_id, removed.c.kind != EventKind.START.value)
            .values(
                series=case((item_kind, p.c.series), else_=removed.c.from_series),
                last_key=case((item_kind, p.c.last_key), else_=removed.c.from_key),
                items=case(
                    (
                        removed.c.kind == EventKind.ITEM_GIVEN.value,
                        func.array_remove(p.c["items"], removed.c.item),
                    ),
                    (
                        removed.c.kind == EventKind.ITEM_REMOVED.value,
                        func.array_append(p.c["items"], removed.c.item),
                    ),
                    else_=p.c["items"],
                ),
                last_event_id=case((latest, previous), else_=p.c.last_event_id),
                hint_series=case((latest, p.c.hint_series), else_=null()),
                hint_key=case((latest, p.c.hint_key), else_=null()),
                hint_event_id=case((latest, p.c.hint_event_id), else_=null()),
                updated_at=func.now(),
            )
            .returning(p.c.account_id)
            .cte("restored")
        )
        unset = (
            delete(p)
            .where(
                and_(
                    p.c.account_id == removed.c.account_id, removed.c.kind == EventKind.START.value
                )
            )
            .returning(p.c.account_id)
            .cte("unset")
        )
        stmt = select(
            select(func.count()).select_from(removed).scalar_subquery(),
            select(func.count()).select_from(restored).scalar_subquery(),
            select(func.count()).select_from(unset).scalar_subquery(),
        )
        async with connection(self._engine) as conn:
            found, _, _ = (await conn.execute(stmt)).one()
        return bool(found)

    async def dismiss_hint(self, account_id: UUID, target: Position) -> None:
        stmt = (
            update(progression)
            .where(progression.c.account_id == account_id)
            .values(
                hint_series=target.series,
                hint_key=target.key,
                hint_event_id=progression.c.last_event_id,
            )
        )
        async with connection(self._engine) as conn:
            await conn.execute(stmt)


def _view_columns(account_id: UUID) -> tuple[Any, ...]:
    """What the history held, and the newest events with who marked them: `by` from
    `marked_by` (NULL, a deleted account, reads as a teacher), `by_name` only while that teacher
    is still linked. Scalar subqueries over aliases, so they never correlate with the caller's
    own joins (`account`, `teacher_link` in `for_teacher`)."""
    e = progression_event
    mine = e.c.account_id == account_id
    targets, given_items = _earlier_columns(account_id)
    newest = (
        select(*e.c).where(mine).order_by(e.c.id.desc()).limit(HISTORY_LIMIT).subquery("newest")
    )
    events = _events_json(account_id, newest).label("events")
    # Q159: the event that set the position, however old (index `(account_id, id DESC)`).
    latest_position = (
        select(*e.c)
        .where(mine, e.c.kind.in_(_POSITION_KINDS))
        .order_by(e.c.id.desc())
        .limit(1)
        .subquery("latest_position")
    )
    position_event = _events_json(account_id, latest_position).label("position_event")
    return targets, given_items, events, position_event


def _earlier_columns(account_id: UUID, *where: Any) -> tuple[Any, Any]:
    """Every position reached and every item given (`Earlier`), limited by `where`."""
    e = progression_event
    mine = e.c.account_id == account_id
    reached = (
        select(e.c.to_series, e.c.to_key)
        .where(mine, e.c.kind.in_(_POSITION_KINDS), *where)
        .distinct()
        .subquery("reached")
    )
    targets = (
        select(
            func.json_agg(func.json_build_array(reached.c.to_series, reached.c.to_key), type_=JSON)
        )
        .scalar_subquery()
        .label("targets")
    )
    given_items = (
        select(func.array_agg(distinct(e.c.item)))
        .where(mine, e.c.kind == EventKind.ITEM_GIVEN.value, *where)
        .scalar_subquery()
        .label("given_items")
    )
    return targets, given_items


def _earlier(row: Row[*tuple[Any, ...]]) -> Earlier:
    reached_at = frozenset(Position(s, k) for s, k in _json(row.targets))
    return Earlier(reached_at, frozenset(row.given_items or ()))


def _events_json(account_id: UUID, rows: Any, *, ascending: bool = False) -> Any:
    """`rows` (a subquery of `progression_event`) as one JSON array ordered by id, with who
    marked each: `by` from `marked_by` (NULL, a deleted account, reads as a teacher), `by_name`
    only while that teacher is still linked. Over aliases, so it never correlates with the
    caller's own joins (`account`, `teacher_link` in `for_teacher`)."""
    marker_link = teacher_link.alias("marker_link")
    marker = account.alias("marker")
    by = case(
        (rows.c.marked_by == account_id, literal(Marker.SELF.value)),
        else_=literal(Marker.TEACHER.value),
    )
    fields = ("id", "kind", "from_series", "from_key", "to_series", "to_key", "item")
    built = func.json_build_object(
        *(x for f in fields for x in (f, rows.c[f])),
        "occurred_on",
        rows.c.occurred_on,
        "by",
        by,
        "by_name",
        marker.c.display_name,
    )
    order = rows.c.id.asc() if ascending else rows.c.id.desc()
    return (
        select(func.json_agg(aggregate_order_by(built, order), type_=JSON))
        .select_from(
            rows.outerjoin(
                marker_link,
                and_(
                    marker_link.c.student_id == account_id,
                    marker_link.c.teacher_id == rows.c.marked_by,
                ),
            ).outerjoin(marker, marker.c.id == marker_link.c.teacher_id)
        )
        .scalar_subquery()
    )


def _view(account_id: UUID, row: Row[*tuple[Any, ...]]) -> ProgressionView:
    earlier = _earlier(row)
    found = tuple(_to_event(account_id, x) for x in _json(row.events))
    position = [_to_event(account_id, x) for x in _json(row.position_event)]
    return ProgressionView(to_progression(row), earlier, found, position[0] if position else None)


def _json(value: Any) -> list[Any]:
    return [] if value is None else list(value)
