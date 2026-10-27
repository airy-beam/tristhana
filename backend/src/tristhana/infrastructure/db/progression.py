"""`ProgressionRepository` on Postgres (PR-08, ADR-0026). Every method is one statement:
a write appends its event and moves the state row together, guarded by the state's
`last_event_id` (compare-and-set), so a double tap or a second device can't fork it."""

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
    func,
    literal,
    literal_column,
    select,
    update,
)
from sqlalchemy.dialects.postgresql import JSON, aggregate_order_by, insert
from sqlalchemy.ext.asyncio import AsyncEngine

from tristhana.application.ports.progression import ProgressionView
from tristhana.domain.progression import (
    HISTORY_LIMIT,
    Change,
    Earlier,
    EventKind,
    Position,
    Progression,
    ProgressionEvent,
)
from tristhana.infrastructure.db.engine import connection
from tristhana.infrastructure.db.tables import progression, progression_event

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
        marked_by_self=e["marked_by"] == str(account_id),
    )


class SqlProgressionRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def get(self, account_id: UUID) -> ProgressionView:
        e = progression_event
        mine = e.c.account_id == account_id
        reached = (
            select(e.c.to_series, e.c.to_key)
            .where(mine, e.c.kind.in_(_POSITION_KINDS))
            .distinct()
            .subquery("reached")
        )
        targets = (
            select(
                func.json_agg(
                    func.json_build_array(reached.c.to_series, reached.c.to_key), type_=JSON
                )
            )
            .scalar_subquery()
            .label("targets")
        )
        given_items = (
            select(func.array_agg(distinct(e.c.item)))
            .where(mine, e.c.kind == EventKind.ITEM_GIVEN.value)
            .scalar_subquery()
            .label("given_items")
        )
        newest = (
            select(*e.c).where(mine).order_by(e.c.id.desc()).limit(HISTORY_LIMIT).subquery("newest")
        )
        fields = ("id", "kind", "from_series", "from_key", "to_series", "to_key", "item")
        built = func.json_build_object(
            *(x for f in fields for x in (f, newest.c[f])),
            "occurred_on",
            newest.c.occurred_on,
            "marked_by",
            newest.c.marked_by,
        )
        events = (
            select(func.json_agg(aggregate_order_by(built, newest.c.id.desc()), type_=JSON))
            .scalar_subquery()
            .label("events")
        )
        one = select(literal(1).label("one")).subquery("one")
        stmt = select(*_STATE, targets, given_items, events).select_from(
            one.outerjoin(progression, progression.c.account_id == account_id)
        )
        async with connection(self._engine) as conn:
            row = (await conn.execute(stmt)).one()
        reached_at = frozenset(Position(s, k) for s, k in _json(row.targets))
        earlier = Earlier(reached_at, frozenset(row.given_items or ()))
        found = tuple(_to_event(account_id, x) for x in _json(row.events))
        return ProgressionView(to_progression(row), earlier, found)

    async def apply(
        self, account_id: UUID, change: Change, expected_event_id: int | None, marked_by: UUID
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
            where=p.c.last_event_id.is_not_distinct_from(literal(expected_event_id, BigInteger)),
        )
        moved = upsert.returning(p.c.last_event_id).cte("moved")
        before, after = change.before, change.after
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
                literal(before.series if before else None, e.c.from_series.type),
                literal(before.key if before else None, e.c.from_key.type),
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
        return ProgressionEvent(
            event_id, change.kind, change.occurred_on, before, after, change.item, True
        )

    async def undo(self, account_id: UUID, event_id: int) -> bool:
        p, e = progression, progression_event
        current = (
            select(p.c.last_event_id)
            .where(p.c.account_id == account_id)
            .with_for_update()
            .cte("current")
        )
        removed = (
            delete(e)
            .where(
                e.c.account_id == account_id,
                e.c.id == event_id,
                e.c.id == select(current.c.last_event_id).scalar_subquery(),
            )
            .returning(e.c.account_id, e.c.kind, e.c.from_series, e.c.from_key, e.c.item)
            .cte("removed")
        )
        # The snapshot still has the removed row, so "before it" is `id < event_id`.
        previous = (
            select(func.max(e.c.id))
            .where(e.c.account_id == account_id, e.c.id < event_id)
            .scalar_subquery()
        )
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
                last_event_id=previous,
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


def _json(value: Any) -> list[Any]:
    return [] if value is None else list(value)
