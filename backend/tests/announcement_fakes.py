"""An in-memory `AnnouncementRepository` (NT-03) with its own small model of links and shala
members, mirroring the SQL: the guard, the rate limit, the live audience, pins, mutes and the
tick's `due` (minus final ledger rows of `tests.fakes.InMemoryNotifications`)."""

from dataclasses import dataclass, field
from datetime import UTC, datetime, time
from typing import Any
from uuid import UUID, uuid4

from tristhana.application.ports.announcements import (
    DueAnnouncement,
    Feed,
    FeedItem,
    FeedSource,
    Managed,
    NewAnnouncement,
    Posted,
    SentItem,
)
from tristhana.domain.announcements import Source, SourceKind, pinned
from tristhana.domain.locale import Locale
from tristhana.domain.notifications import DEFAULTS, QuietHours
from tristhana.domain.shalas import Membership, ShalaRole

T0 = datetime(2026, 11, 1, tzinfo=UTC)


@dataclass
class Person:
    name: str | None
    telegram_id: str | None = None
    zone: str | None = "Asia/Almaty"
    locale: Locale = "en"
    quiet: QuietHours = DEFAULTS.quiet
    announcements_on: bool | None = None
    unreachable: bool = False


@dataclass
class Member:
    created_at: datetime
    muted: bool = False
    owner: bool = False
    roles: frozenset[ShalaRole] = frozenset()
    student: bool = False


@dataclass
class Row:
    id: UUID
    author_id: UUID
    shala_id: UUID | None
    text: str
    audience: int
    pinned_until: datetime | None
    created_at: datetime


@dataclass
class InMemoryAnnouncements:
    clock: Any  # has .now(); `created_at` of new rows
    people: dict[UUID, Person] = field(default_factory=dict[UUID, Person])
    links: dict[tuple[UUID, UUID], Member] = field(default_factory=dict[tuple[UUID, UUID], Member])
    members: dict[tuple[UUID, UUID], Member] = field(
        default_factory=dict[tuple[UUID, UUID], Member]
    )
    shala_names: dict[UUID, str] = field(default_factory=dict[UUID, str])
    rows: dict[UUID, Row] = field(default_factory=dict[UUID, Row])
    deliveries: Any = None  # InMemoryNotifications.deliveries, for `due`
    calls: list[str] = field(default_factory=list[str])

    # --- setup ---------------------------------------------------------------------

    def person(self, name: str | None = None, **kw: Any) -> UUID:
        uid = uuid4()
        kw.setdefault("telegram_id", str(len(self.people) + 100))
        self.people[uid] = Person(name, **kw)
        return uid

    def link(self, student: UUID, teacher: UUID, at: datetime = T0) -> None:
        self.links[(student, teacher)] = Member(at)

    def shala(self, name: str, owner: UUID, at: datetime = T0) -> UUID:
        sid = uuid4()
        self.shala_names[sid] = name
        self.members[(sid, owner)] = Member(at, owner=True)
        return sid

    def staff(self, shala: UUID, who: UUID, *roles: ShalaRole, at: datetime = T0) -> None:
        self.members[(shala, who)] = Member(at, roles=frozenset(roles))

    def student(self, shala: UUID, who: UUID, at: datetime = T0) -> None:
        self.members[(shala, who)] = Member(at, student=True)

    def membership(self, shala: UUID, who: UUID) -> Membership | None:
        m = self.members.get((shala, who))
        if m is None:
            return None
        return Membership(shala, m.owner, m.roles, m.student)

    # --- helpers -------------------------------------------------------------------

    def _audience(self, source: Source, author: UUID) -> list[tuple[UUID, Member]]:
        if source.kind is SourceKind.TEACHER:
            return [(s, m) for (s, t), m in self.links.items() if t == source.id]
        return [(a, m) for (sh, a), m in self.members.items() if sh == source.id and a != author]

    def _source(self, row: Row) -> Source:
        if row.shala_id is None:
            return Source(SourceKind.TEACHER, row.author_id)
        return Source(SourceKind.SHALA, row.shala_id)

    def _sent(self, row: Row) -> SentItem:
        name = self.shala_names.get(row.shala_id) if row.shala_id else None
        return SentItem(
            row.id,
            self._source(row),
            name,
            row.text,
            row.created_at,
            row.pinned_until,
            row.audience,
        )

    def _my_sources(self, me: UUID) -> list[tuple[Source, str | None, Member]]:
        out: list[tuple[Source, str | None, Member]] = []
        for (s, t), m in sorted(self.links.items(), key=lambda kv: kv[1].created_at):
            if s == me:
                out.append((Source(SourceKind.TEACHER, t), self.people[t].name, m))
        for (sh, a), m in sorted(self.members.items(), key=lambda kv: kv[1].created_at):
            if a == me:
                out.append((Source(SourceKind.SHALA, sh), self.shala_names[sh], m))
        return out

    def _author_current(self, row: Row) -> bool:
        if row.shala_id is None:
            return any(t == row.author_id for (_, t) in self.links)
        m = self.members.get((row.shala_id, row.author_id))
        return m is not None and not m.student

    def _can_manage(self, me: UUID, row: Row) -> bool:
        if row.author_id == me:
            return True
        if row.shala_id is None:
            return False
        m = self.members.get((row.shala_id, me))
        return m is not None and not m.student and (m.owner or ShalaRole.ADMIN in m.roles)

    def _visible(self, me: UUID, row: Row) -> bool:
        if row.author_id == me:
            return True
        return any(src == self._source(row) for src, _, _ in self._my_sources(me))

    # --- the port ------------------------------------------------------------------

    async def create(self, new: NewAnnouncement) -> Posted:
        self.calls.append("create")
        me: Membership | None = None
        if new.source.kind is SourceKind.SHALA:
            me = self.membership(new.source.id, new.author_id)
            schedule = {ShalaRole.ADMIN, ShalaRole.TEACHER, ShalaRole.OFFICE}
            if me is None or me.student or not (me.owner or me.roles & schedule):
                return Posted(me, False, False, None)
        recent = [
            r
            for r in self.rows.values()
            if self._source(r) == new.source and r.created_at > new.since
        ]
        if len(recent) >= new.limit:
            return Posted(me, True, True, None)
        audience = len(self._audience(new.source, new.author_id))
        if audience == 0:
            return Posted(me, True, False, None)
        if new.pinned_until is not None:
            for r in self.rows.values():
                if self._source(r) == new.source:
                    r.pinned_until = None
        row = Row(
            uuid4(),
            new.author_id,
            new.source.id if new.source.kind is SourceKind.SHALA else None,
            new.text,
            audience,
            new.pinned_until,
            self.clock.now(),
        )
        self.rows[row.id] = row
        return Posted(me, True, False, self._sent(row))

    async def feed(
        self,
        me: UUID,
        source: Source | None,
        since: datetime,
        now: datetime,
        offset: int,
        limit: int,
    ) -> Feed | None:
        self.calls.append("feed")
        mine = self._my_sources(me)
        wanted = {s for s, _, _ in mine}
        if source is not None:
            if source not in wanted:
                return None
            wanted = {source}
        names = {s: n for s, n, _ in mine}
        rows = [
            r
            for r in self.rows.values()
            if self._source(r) in wanted and (r.created_at >= since or pinned(r.pinned_until, now))
        ]
        rows.sort(key=lambda r: (not pinned(r.pinned_until, now), -r.created_at.timestamp()))
        page = rows[offset : offset + limit]
        items = tuple(
            FeedItem(
                r.id,
                self._source(r),
                names[self._source(r)],
                self.people[r.author_id].name if self._author_current(r) else None,
                r.text,
                r.created_at,
                r.pinned_until if pinned(r.pinned_until, now) else None,
                self._can_manage(me, r),
            )
            for r in page
        )
        sources = tuple(FeedSource(s, n, m.muted) for s, n, m in mine if s in wanted)
        return Feed(items, sources, more=len(rows) > offset + limit)

    async def sent(self, me: UUID, since: datetime) -> tuple[SentItem, ...]:
        self.calls.append("sent")
        rows = [r for r in self.rows.values() if r.author_id == me and r.created_at >= since]
        rows.sort(key=lambda r: r.created_at, reverse=True)
        return tuple(self._sent(r) for r in rows)

    def _found(self, me: UUID, row: Row, allowed: bool, item: SentItem | None = None) -> Managed:
        member = self.membership(row.shala_id, me) if row.shala_id else None
        return Managed(True, allowed, item, row.author_id, member, row.shala_id is not None)

    def _can_pin(self, me: UUID, row: Row) -> bool:
        if row.author_id != me:
            return self._can_manage(me, row)
        if row.shala_id is None:
            return True
        m = self.members.get((row.shala_id, me))
        schedule = {ShalaRole.ADMIN, ShalaRole.TEACHER, ShalaRole.OFFICE}
        return m is not None and not m.student and (m.owner or bool(m.roles & schedule))

    async def set_pin(self, me: UUID, id: UUID, pinned_until: datetime | None) -> Managed:
        self.calls.append("set_pin")
        row = self.rows.get(id)
        if row is None or not self._visible(me, row):
            return Managed(False, False)
        if not self._can_pin(me, row):
            return self._found(me, row, False)
        if pinned_until is not None:
            for r in self.rows.values():
                if self._source(r) == self._source(row):
                    r.pinned_until = None
        row.pinned_until = pinned_until
        return self._found(me, row, True, self._sent(row))

    async def delete(self, me: UUID, id: UUID) -> Managed:
        self.calls.append("delete")
        row = self.rows.get(id)
        if row is None or not self._visible(me, row):
            return Managed(False, False)
        if not self._can_manage(me, row):
            return self._found(me, row, False)
        del self.rows[id]
        return self._found(me, row, True)

    async def set_mute(self, me: UUID, source: Source, muted: bool) -> bool:
        self.calls.append("set_mute")
        if source.kind is SourceKind.TEACHER:
            m = self.links.get((me, source.id))
        else:
            m = self.members.get((source.id, me))
        if m is None:
            return False
        m.muted = muted
        return True

    async def due(self, since: datetime, now: datetime, limit: int) -> list[DueAnnouncement]:
        self.calls.append("due")
        out: list[DueAnnouncement] = []
        for row in sorted(self.rows.values(), key=lambda r: r.created_at):
            if row.created_at <= since:
                continue
            source = self._source(row)
            for who, m in sorted(self._audience(source, row.author_id), key=lambda x: str(x[0])):
                p = self.people[who]
                if m.created_at > row.created_at or m.muted or p.announcements_on is False:
                    continue
                if p.telegram_id is None or p.unreachable:
                    continue
                if self.deliveries is not None:
                    d = self.deliveries.get((who, f"ann:{row.id}"))
                    if d is not None and not (d["status"] == "failed" and d["attempts"] < 3):
                        continue
                name = (
                    self.shala_names[row.shala_id]
                    if row.shala_id
                    else self.people[row.author_id].name
                )
                out.append(
                    DueAnnouncement(
                        row.id,
                        source,
                        name,
                        self.people[row.author_id].name,
                        row.text,
                        row.created_at,
                        who,
                        p.telegram_id,
                        p.locale,
                        p.zone,
                        p.quiet,
                    )
                )
        return out[:limit]

    async def prune(self, before: datetime) -> int:
        old = [i for i, r in self.rows.items() if r.created_at < before]
        for i in old:
            del self.rows[i]
        return len(old)


NO_QUIET = QuietHours(time(0), time(0))
