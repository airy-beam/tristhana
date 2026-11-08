"""In-memory progression for teacher marks (PR-08 Phase 3, spec §4, ADR-0037).

Its own file because it imports the feature's new port and domain types; the bot and API tests
hand it to `InMemoryStorage(progression_repo=…)`. Once the feature lands, it can replace
`tests.fakes.InMemoryProgression` (whose events still carry `marked_by_self`).

`MarkingProgression` follows the SQL over the in-memory rows: `for_teacher` (the link, the
student's zone, locale and Telegram id, and the view, in one "statement"), `apply` with the
position compare-and-set and the link guard, the wider undo (a teacher's `given` until the
position moves on), and `get` with `by` / `by_name` (the name only while linked).

`ScriptedMarks` hands back what a test gives it, including a link the SQL would never return
(another teacher's), because the use case must not trust it."""

import asyncio
from dataclasses import dataclass, field, replace
from typing import Any
from uuid import UUID

from tests.fakes import InMemoryDays, InMemoryProgression
from tristhana.application.ports.progression import MarkLink, ProgressionView, TeacherMarkView
from tristhana.domain.progression import (
    HISTORY_LIMIT,
    Change,
    Earlier,
    EventKind,
    Marker,
    Progression,
    ProgressionEvent,
)

_UNCHECKED: Any = object()  # `before` not passed: an old caller, no position check
_POSITION_KINDS = (EventKind.START, EventKind.GIVEN, EventKind.CHANGED)


@dataclass
class MarkingProgression(InMemoryProgression):
    links: Any = None  # tests.teacher_link_fakes.InMemoryTeacherLinks
    # Who wrote each event; None = the teacher's account was deleted (ON DELETE SET NULL).
    marked_by: dict[int, UUID | None] = field(default_factory=dict[int, UUID | None])

    def _event(self, account_id: UUID, e: ProgressionEvent) -> ProgressionEvent:
        author = self.marked_by.get(e.id, account_id)
        if author == account_id:
            return replace(e, by=Marker.SELF, by_name=None)
        name = None
        if author is not None and (account_id, author) in self.links.rows:
            teacher = self.links.accounts.accounts.get(author)
            name = teacher.display_name if teacher else None
        return replace(e, by=Marker.TEACHER, by_name=name)

    async def get(self, account_id: UUID) -> ProgressionView:
        self.days._check()  # pyright: ignore[reportPrivateUsage]
        self.calls.append("get")
        return self._view(account_id)

    def _view(self, account_id: UUID) -> ProgressionView:
        events = [self._event(account_id, e) for e in self._events(account_id)]
        targets = frozenset(e.after for e in events if e.after is not None)
        items = frozenset(e.item for e in events if e.kind is EventKind.ITEM_GIVEN and e.item)
        newest = tuple(reversed(events))[:HISTORY_LIMIT]
        return ProgressionView(
            self.days.progression_rows.get(account_id), Earlier(targets, items), newest
        )

    async def for_teacher(self, teacher: UUID, student: UUID) -> TeacherMarkView | None:
        self.days._check()  # pyright: ignore[reportPrivateUsage]
        await asyncio.sleep(0)
        self.calls.append("for_teacher")
        if (student, teacher) not in self.links.rows:
            return None
        account = self.links.accounts.accounts[student]
        link = MarkLink(
            teacher_id=teacher,
            student_id=student,
            timezone=account.timezone,
            locale=account.locale,
            telegram_id=self.links._telegram_id(student),  # pyright: ignore[reportPrivateUsage]
        )
        return TeacherMarkView(link, self._view(student))

    async def apply(
        self,
        account_id: UUID,
        change: Change,
        expected_event_id: int | None,
        marked_by: UUID,
        *,
        before: Any = _UNCHECKED,
        link_teacher: UUID | None = None,
    ) -> ProgressionEvent | None:
        self.days._check()  # pyright: ignore[reportPrivateUsage]
        await asyncio.sleep(0)
        self.calls.append("apply")
        if link_teacher is not None and (account_id, link_teacher) not in self.links.rows:
            return None
        current = self.days.progression_rows.get(account_id)
        if (current.last_event_id if current else None) != expected_event_id:
            return None
        if before is not _UNCHECKED and current is not None and current.position != before:
            return None
        event_id = 1 + max((e.id for _, e in self.days.progression_events), default=0)
        by = Marker.SELF if marked_by == account_id else Marker.TEACHER
        event = ProgressionEvent(
            id=event_id,
            kind=change.kind,
            occurred_on=change.occurred_on,
            before=change.before,
            after=change.after,
            item=change.item,
            by=by,
            by_name=None,
        )
        self.days.progression_events.append((account_id, event))
        self.marked_by[event_id] = marked_by
        hint = (current.hint, current.hint_event_id) if current else (None, None)
        self.days.progression_rows[account_id] = Progression(
            change.state.position, change.state.items, event_id, *hint
        )
        return event

    async def undo(self, account_id: UUID, event_id: int) -> bool:
        current = self.days.progression_rows.get(account_id)
        if current is not None and current.last_event_id == event_id:
            return await super().undo(account_id, event_id)
        self.days._check()  # pyright: ignore[reportPrivateUsage]
        self.calls.append("undo")
        events = self._events(account_id)
        event = next((e for e in events if e.id == event_id), None)
        if current is None or event is None or event.kind is not EventKind.GIVEN:
            return False
        if self.marked_by.get(event_id, account_id) == account_id:
            return False  # the student's own marks: latest only
        if any(e.id > event_id and e.kind in _POSITION_KINDS for e in events):
            return False  # the position moved on since the mark
        self.days.progression_events.remove((account_id, event))
        self.days.progression_rows[account_id] = replace(
            current, position=event.before, hint=None, hint_event_id=None
        )
        return True

    # Seeding (not part of the port).

    def delete_teacher(self, teacher: UUID) -> None:
        """The teacher's account goes: `marked_by` becomes NULL, the link cascades."""
        for event_id, author in list(self.marked_by.items()):
            if author == teacher:
                self.marked_by[event_id] = None
        for key in [k for k in self.links.rows if k[1] == teacher]:
            del self.links.rows[key]
        self.links.accounts.accounts.pop(teacher, None)


def marking(storage: Any) -> MarkingProgression:
    """Installs a `MarkingProgression` on an `InMemoryStorage` (before the app is built)."""
    repo = MarkingProgression(storage.day_repo, links=storage.teacher_links)
    storage.progression_repo = repo
    return repo


@dataclass
class ScriptedMarks:
    """`for_teacher` returns `found`; `apply` returns `result` (None = a lost compare-and-set),
    or a fresh event when `result` is left as the default."""

    days: InMemoryDays = field(default_factory=InMemoryDays)
    found: TeacherMarkView | None = None
    result: Any = "event"
    calls: list[str] = field(default_factory=list[str])
    applied: list[dict[str, Any]] = field(default_factory=list[dict[str, Any]])

    async def for_teacher(self, teacher: UUID, student: UUID) -> TeacherMarkView | None:
        self.calls.append("for_teacher")
        return self.found

    async def get(self, account_id: UUID) -> ProgressionView:
        self.calls.append("get")
        return self.found.view if self.found else ProgressionView(None)

    async def apply(
        self,
        account_id: UUID,
        change: Change,
        expected_event_id: int | None = None,
        marked_by: UUID | None = None,
        **rest: Any,
    ) -> ProgressionEvent | None:
        """Records every argument; `expected` is accepted as a spelling of the expected id."""
        self.calls.append("apply")
        expected = rest.pop("expected", expected_event_id)
        self.applied.append(
            {
                "account_id": account_id,
                "change": change,
                "expected": expected,
                "marked_by": marked_by,
                **rest,
            }
        )
        if self.result != "event":
            return self.result
        return ProgressionEvent(
            id=101,
            kind=change.kind,
            occurred_on=change.occurred_on,
            before=change.before,
            after=change.after,
            item=change.item,
            by=Marker.TEACHER,
            by_name=None,
        )

    async def undo(self, account_id: UUID, event_id: int) -> bool:
        self.calls.append("undo")
        return False

    async def dismiss_hint(self, account_id: UUID, target: Any) -> None:
        self.calls.append("dismiss_hint")
