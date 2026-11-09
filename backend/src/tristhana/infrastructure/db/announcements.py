"""Announcements (NT-03, ADR-0038). One statement per operation; every write carries its own
guard (the SQL mirror of `application/policies.py`). The text is never logged."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
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
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncEngine

from tristhana.application.policies import can_announce_to_shala, can_moderate_announcements
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
from tristhana.domain.announcements import Source, SourceKind
from tristhana.domain.locale import DEFAULT_LOCALE, LOCALES, Locale
from tristhana.domain.notifications import DEFAULTS, QuietHours
from tristhana.domain.shalas import ShalaRole
from tristhana.infrastructure.db.engine import connection
from tristhana.infrastructure.db.notifications import MAX_ATTEMPTS, STALE_CLAIM
from tristhana.infrastructure.db.shalas import allowed_codes, member_columns, membership_of
from tristhana.infrastructure.db.tables import (
    account,
    announcement,
    identity,
    notification_delivery,
    notification_settings,
    shala,
    shala_staff,
    shala_student,
    teacher_link,
)

_A = announcement
_NS = notification_settings


def _same_source(a: Any, author_id: Any, shala_id: Any) -> Any:
    """Rows of `a` from the same source as (author_id, shala_id)."""
    return or_(
        and_(shala_id.is_(None), a.c.shala_id.is_(None), a.c.author_id == author_id),
        and_(shala_id.is_not(None), a.c.shala_id == shala_id),
    )


def _source_match(source: Source) -> Any:
    if source.kind is SourceKind.TEACHER:
        return and_(_A.c.shala_id.is_(None), _A.c.author_id == source.id)
    return _A.c.shala_id == source.id


def _audience_count(source: Source, author: UUID) -> Any:
    if source.kind is SourceKind.TEACHER:
        return (
            select(func.count())
            .select_from(teacher_link)
            .where(teacher_link.c.teacher_id == author)
            .scalar_subquery()
        )
    staff = (
        select(func.count())
        .select_from(shala_staff)
        .where(shala_staff.c.shala_id == source.id, shala_staff.c.account_id != author)
        .scalar_subquery()
    )
    students = (
        select(func.count())
        .select_from(shala_student)
        .where(shala_student.c.shala_id == source.id, shala_student.c.account_id != author)
        .scalar_subquery()
    )
    return staff + students


def _is_staff(shala_id: Any, who: Any) -> Any:
    return exists().where(shala_staff.c.shala_id == shala_id, shala_staff.c.account_id == who)


def _is_member(shala_id: Any, who: Any) -> Any:
    return or_(
        _is_staff(shala_id, who),
        exists().where(shala_student.c.shala_id == shala_id, shala_student.c.account_id == who),
    )


def _manages(shala_id: Any, owner_id: Any, who: Any) -> Any:
    """The SQL mirror of `policies._manages` (owner, or staff with the manager role)."""
    return or_(
        owner_id == who,
        exists().where(
            shala_staff.c.shala_id == shala_id,
            shala_staff.c.account_id == who,
            shala_staff.c.roles.contains([ShalaRole.ADMIN.value]),
        ),
    )


def _can_manage(me: UUID) -> Any:
    """`can_manage_announcement` on a row of `_A` outer-joined to `shala`."""
    return or_(
        _A.c.author_id == me,
        and_(_A.c.shala_id.is_not(None), _manages(_A.c.shala_id, shala.c.owner_id, me)),
    )


def _visible(me: UUID) -> Any:
    """`can_view_announcements`: the author, the teacher's linked students, or a member."""
    return or_(
        _A.c.author_id == me,
        and_(
            _A.c.shala_id.is_(None),
            exists().where(
                teacher_link.c.student_id == me, teacher_link.c.teacher_id == _A.c.author_id
            ),
        ),
        and_(_A.c.shala_id.is_not(None), _is_member(_A.c.shala_id, me)),
    )


def _author_current() -> Any:
    """The author is still the teacher (a link exists) or still on the shala's staff."""
    return case(
        (
            _A.c.shala_id.is_(None),
            exists().where(teacher_link.c.teacher_id == _A.c.author_id),
        ),
        else_=_is_staff(_A.c.shala_id, _A.c.author_id),
    )


def _source_of(author_id: UUID, shala_id: UUID | None) -> Source:
    if shala_id is None:
        return Source(SourceKind.TEACHER, author_id)
    return Source(SourceKind.SHALA, shala_id)


def _parse_ts(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value is not None else None


class SqlAnnouncementRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def _one(self, stmt: Any) -> Any:
        async with connection(self._engine) as conn:
            return (await conn.execute(stmt)).one_or_none()

    async def create(self, new: NewAnnouncement) -> Posted:
        source, me = new.source, new.author_id
        recent = (
            select(func.count())
            .select_from(_A)
            .where(_source_match(source), _A.c.created_at > new.since)
            .scalar_subquery()
        )
        audience = _audience_count(source, me)
        guards: list[Any] = [recent < new.limit, audience > 0]
        cur = None
        if source.kind is SourceKind.SHALA:
            cur = (
                select(shala.c.id, shala.c.owner_id, *member_columns(shala.c.id, me, "me"))
                .where(shala.c.id == source.id)
                .cte("cur")
            )
            allowed = allowed_codes(can_announce_to_shala)
            guards.append(exists(select(cur.c.id).where(cur.c.me_code.in_(allowed))))
        shala_id = source.id if source.kind is SourceKind.SHALA else None
        unpinned = (
            update(_A)
            .where(
                _source_match(source),
                _A.c.pinned_until.is_not(None),
                true() if new.pinned_until is not None else false(),
                *guards,
            )
            .values(pinned_until=None)
            .returning(_A.c.id)
            .cte("unpinned")
        )
        added = (
            insert(_A)
            .from_select(
                ["author_id", "shala_id", "text", "audience", "pinned_until"],
                select(
                    literal(me),
                    literal(shala_id, type_=_A.c.shala_id.type),
                    literal(new.text),
                    audience,
                    literal(new.pinned_until, type_=_A.c.pinned_until.type),
                ).where(*guards),
            )
            .returning(_A.c.id, _A.c.created_at, _A.c.audience, _A.c.pinned_until)
            .cte("added")
        )
        columns: list[Any] = [
            recent.label("recent"),
            select(added.c.id).scalar_subquery().label("new_id"),
            select(added.c.created_at).scalar_subquery().label("new_at"),
            select(added.c.audience).scalar_subquery().label("new_audience"),
            select(added.c.pinned_until).scalar_subquery().label("new_pin"),
            select(func.count()).select_from(unpinned).scalar_subquery().label("unpinned"),
        ]
        if cur is not None:
            stmt = select(
                cur.c.id,
                cur.c.owner_id,
                cur.c.me_roles,
                cur.c.me_student,
                shala.c.name,
                *columns,
            ).select_from(cur.join(shala, shala.c.id == cur.c.id))
        else:
            stmt = select(*columns)
        row = await self._one(stmt)
        if row is None:  # no such shala
            return Posted(None, False, False, None)
        membership = None
        name = None
        if cur is not None:
            membership = membership_of(row, row.id, row.owner_id, me)
            name = row.name
            if membership is None or not can_announce_to_shala(membership):
                return Posted(membership, False, False, None)
        if row.new_id is None:
            return Posted(membership, True, row.recent >= new.limit, None)
        item = SentItem(
            row.new_id,
            source,
            name,
            new.text,
            row.new_at,
            row.new_pin,
            row.new_audience,
        )
        return Posted(membership, True, False, item)

    def _sources(self, me: UUID) -> Any:
        teachers = (
            select(
                literal("t").label("kind"),
                teacher_link.c.teacher_id.label("sid"),
                account.c.display_name.label("name"),
                teacher_link.c.announcements_muted.label("muted"),
                teacher_link.c.created_at.label("since"),
            )
            .select_from(teacher_link.join(account, account.c.id == teacher_link.c.teacher_id))
            .where(teacher_link.c.student_id == me)
        )
        staff = (
            select(
                literal("h"),
                shala.c.id,
                shala.c.name,
                shala_staff.c.announcements_muted,
                shala_staff.c.created_at,
            )
            .select_from(shala_staff.join(shala, shala.c.id == shala_staff.c.shala_id))
            .where(shala_staff.c.account_id == me)
        )
        students = (
            select(
                literal("h"),
                shala.c.id,
                shala.c.name,
                shala_student.c.announcements_muted,
                shala_student.c.created_at,
            )
            .select_from(shala_student.join(shala, shala.c.id == shala_student.c.shala_id))
            .where(shala_student.c.account_id == me)
        )
        return union_all(teachers, staff, students)

    async def feed(
        self,
        me: UUID,
        source: Source | None,
        since: datetime,
        now: datetime,
        offset: int,
        limit: int,
    ) -> Feed | None:
        everything = self._sources(me).subquery("everything")
        src_q = select(everything)
        if source is not None:
            src_q = src_q.where(
                everything.c.kind == source.kind.value, everything.c.sid == source.id
            )
        src = src_q.cte("src")
        live_pin = and_(_A.c.pinned_until.is_not(None), _A.c.pinned_until > now)
        author = account.alias("author")
        items = (
            select(
                _A.c.id,
                _A.c.author_id,
                _A.c.shala_id,
                src.c.name.label("source_name"),
                case((_author_current(), author.c.display_name), else_=null()).label("author_name"),
                _A.c.text,
                _A.c.created_at,
                case((live_pin, _A.c.pinned_until), else_=null()).label("pinned_until"),
                _can_manage(me).label("can_manage"),
            )
            .select_from(
                _A.join(
                    src,
                    or_(
                        and_(
                            src.c.kind == "t",
                            _A.c.shala_id.is_(None),
                            _A.c.author_id == src.c.sid,
                        ),
                        and_(src.c.kind == "h", _A.c.shala_id == src.c.sid),
                    ),
                )
                .join(author, author.c.id == _A.c.author_id)
                .outerjoin(shala, shala.c.id == _A.c.shala_id)
            )
            .where(or_(_A.c.created_at >= since, live_pin))
            .order_by(live_pin.desc(), _A.c.created_at.desc(), _A.c.id)
            .offset(offset)
            .limit(limit + 1)
            .subquery("items")
        )
        item_json = func.jsonb_build_object(
            "id",
            items.c.id,
            "author_id",
            items.c.author_id,
            "shala_id",
            items.c.shala_id,
            "source_name",
            items.c.source_name,
            "author_name",
            items.c.author_name,
            "text",
            items.c.text,
            "created_at",
            items.c.created_at,
            "pinned_until",
            items.c.pinned_until,
            "can_manage",
            items.c.can_manage,
        )
        items_agg = (
            select(func.coalesce(func.jsonb_agg(item_json), func.jsonb_build_array()))
            .select_from(items)
            .scalar_subquery()
        )
        ordered_src = select(src).order_by(src.c.since, src.c.sid).subquery("ordered_src")
        src_agg = (
            select(
                func.coalesce(
                    func.jsonb_agg(
                        func.jsonb_build_object(
                            "kind",
                            ordered_src.c.kind,
                            "sid",
                            ordered_src.c.sid,
                            "name",
                            ordered_src.c.name,
                            "muted",
                            ordered_src.c.muted,
                        )
                    ),
                    func.jsonb_build_array(),
                )
            )
            .select_from(ordered_src)
            .scalar_subquery()
        )
        row = await self._one(select(items_agg.label("items"), src_agg.label("sources")))
        sources = tuple(
            FeedSource(Source(SourceKind(s["kind"]), UUID(s["sid"])), s["name"], s["muted"])
            for s in row.sources
        )
        if source is not None and not sources:
            return None
        found = [
            FeedItem(
                UUID(i["id"]),
                _source_of(UUID(i["author_id"]), UUID(i["shala_id"]) if i["shala_id"] else None),
                i["source_name"],
                i["author_name"],
                i["text"],
                _parse_ts(i["created_at"]) or now,
                _parse_ts(i["pinned_until"]),
                bool(i["can_manage"]),
            )
            for i in row.items
        ]
        # jsonb_agg keeps the subquery's order in practice, but sort to be sure.
        found.sort(key=lambda i: (i.pinned_until is None, -i.created_at.timestamp(), str(i.id)))
        return Feed(tuple(found[:limit]), sources, more=len(found) > limit)

    async def sent(self, me: UUID, since: datetime) -> tuple[SentItem, ...]:
        stmt = (
            select(
                _A.c.id,
                _A.c.author_id,
                _A.c.shala_id,
                shala.c.name,
                _A.c.text,
                _A.c.created_at,
                _A.c.pinned_until,
                _A.c.audience,
            )
            .select_from(_A.outerjoin(shala, shala.c.id == _A.c.shala_id))
            .where(_A.c.author_id == me, _A.c.created_at >= since)
            .order_by(_A.c.created_at.desc(), _A.c.id)
        )
        async with connection(self._engine) as conn:
            rows = (await conn.execute(stmt)).all()
        return tuple(self._sent(r) for r in rows)

    @staticmethod
    def _sent(r: Any) -> SentItem:
        return SentItem(
            r.id,
            _source_of(r.author_id, r.shala_id),
            r.name,
            r.text,
            r.created_at,
            r.pinned_until,
            r.audience,
        )

    def _cur(self, me: UUID, id: UUID, *, pin: bool) -> Any:
        """The item, whether the caller sees it, their membership of its shala, and the guard
        built from the policies' own codes (as `allowed_codes` does for send)."""
        member = member_columns(shala.c.id, me, "me")
        code = member[2]
        moderate = code.in_(allowed_codes(can_moderate_announcements))
        if pin:  # the author only while still speaking for the source
            speaks = or_(_A.c.shala_id.is_(None), code.in_(allowed_codes(can_announce_to_shala)))
            allowed = or_(and_(_A.c.author_id == me, speaks), moderate)
        else:
            allowed = or_(_A.c.author_id == me, moderate)
        return (
            select(
                _A.c.id,
                _A.c.author_id,
                _A.c.shala_id,
                shala.c.owner_id,
                *member,
                _visible(me).label("visible"),
                func.coalesce(allowed, false()).label("can_manage"),
            )
            .select_from(_A.outerjoin(shala, shala.c.id == _A.c.shala_id))
            .where(_A.c.id == id)
            .cte("cur")
        )

    @staticmethod
    def _managed(row: Any, me: UUID, item: SentItem | None = None) -> Managed:
        if row is None or not row.visible:
            return Managed(False, False)
        membership = membership_of(row, row.shala_id, row.owner_id, me) if row.shala_id else None
        return Managed(
            True,
            bool(row.can_manage),
            item,
            row.author_id,
            membership,
            row.shala_id is not None,
        )

    async def set_pin(self, me: UUID, id: UUID, pinned_until: datetime | None) -> Managed:
        cur = self._cur(me, id, pin=True)
        allowed = exists(select(cur.c.id).where(cur.c.visible, cur.c.can_manage))
        others = (
            update(_A)
            .where(
                _A.c.id != id,
                _A.c.pinned_until.is_not(None),
                true() if pinned_until is not None else false(),
                exists(
                    select(cur.c.id).where(
                        cur.c.visible,
                        cur.c.can_manage,
                        _same_source(_A, cur.c.author_id, cur.c.shala_id),
                    )
                ),
            )
            .values(pinned_until=None)
            .returning(_A.c.id)
            .cte("others")
        )
        changed = (
            update(_A)
            .where(_A.c.id == id, allowed)
            .values(pinned_until=literal(pinned_until, type_=_A.c.pinned_until.type))
            .returning(*_A.c)
            .cte("changed")
        )
        stmt = select(
            cur.c.visible,
            cur.c.can_manage,
            cur.c.author_id,
            cur.c.shala_id,
            cur.c.owner_id,
            cur.c.me_roles,
            cur.c.me_student,
            changed.c.id.label("changed_id"),
            changed.c.text,
            changed.c.created_at,
            changed.c.pinned_until,
            changed.c.audience,
            shala.c.name,
            select(func.count()).select_from(others).scalar_subquery().label("others"),
        ).select_from(
            cur.outerjoin(changed, changed.c.id == cur.c.id).outerjoin(
                shala, shala.c.id == cur.c.shala_id
            )
        )
        row = await self._one(stmt)
        item = None
        if row is not None and row.changed_id is not None:
            item = SentItem(
                row.changed_id,
                _source_of(row.author_id, row.shala_id),
                row.name,
                row.text,
                row.created_at,
                row.pinned_until,
                row.audience,
            )
        return self._managed(row, me, item)

    async def delete(self, me: UUID, id: UUID) -> Managed:
        cur = self._cur(me, id, pin=False)
        gone = (
            delete(_A)
            .where(
                _A.c.id == id,
                exists(select(cur.c.id).where(cur.c.visible, cur.c.can_manage)),
            )
            .returning(_A.c.id)
            .cte("gone")
        )
        stmt = select(
            cur.c.visible,
            cur.c.can_manage,
            cur.c.author_id,
            cur.c.shala_id,
            cur.c.owner_id,
            cur.c.me_roles,
            cur.c.me_student,
            select(func.count()).select_from(gone).scalar_subquery().label("gone"),
        )
        return self._managed(await self._one(stmt), me)

    async def set_mute(self, me: UUID, source: Source, muted: bool) -> bool:
        if source.kind is SourceKind.TEACHER:
            stmt: Any = (
                update(teacher_link)
                .where(teacher_link.c.student_id == me, teacher_link.c.teacher_id == source.id)
                .values(announcements_muted=muted)
                .returning(literal(1))
            )
            async with connection(self._engine) as conn:
                return (await conn.execute(stmt)).first() is not None
        staff = (
            update(shala_staff)
            .where(shala_staff.c.shala_id == source.id, shala_staff.c.account_id == me)
            .values(announcements_muted=muted)
            .returning(literal(1).label("one"))
            .cte("staff")
        )
        student = (
            update(shala_student)
            .where(shala_student.c.shala_id == source.id, shala_student.c.account_id == me)
            .values(announcements_muted=muted)
            .returning(literal(1).label("one"))
            .cte("student")
        )
        stmt = select(
            select(func.count()).select_from(staff).scalar_subquery()
            + select(func.count()).select_from(student).scalar_subquery()
        )
        async with connection(self._engine) as conn:
            return bool((await conn.execute(stmt)).scalar_one())

    async def due(self, since: datetime, now: datetime, limit: int) -> list[DueAnnouncement]:
        r = (
            select(_A.c.id, _A.c.author_id, _A.c.shala_id, _A.c.created_at)
            .where(_A.c.created_at > since)
            .cte("recent")
        )
        audience = union_all(
            select(
                r.c.id.label("aid"),
                teacher_link.c.student_id.label("account_id"),
                teacher_link.c.created_at.label("joined"),
                teacher_link.c.announcements_muted.label("muted"),
            ).select_from(
                r.join(
                    teacher_link,
                    and_(r.c.shala_id.is_(None), teacher_link.c.teacher_id == r.c.author_id),
                )
            ),
            select(
                r.c.id,
                shala_staff.c.account_id,
                shala_staff.c.created_at,
                shala_staff.c.announcements_muted,
            ).select_from(
                r.join(
                    shala_staff,
                    and_(
                        shala_staff.c.shala_id == r.c.shala_id,
                        shala_staff.c.account_id != r.c.author_id,
                    ),
                )
            ),
            select(
                r.c.id,
                shala_student.c.account_id,
                shala_student.c.created_at,
                shala_student.c.announcements_muted,
            ).select_from(
                r.join(
                    shala_student,
                    and_(
                        shala_student.c.shala_id == r.c.shala_id,
                        shala_student.c.account_id != r.c.author_id,
                    ),
                )
            ),
        ).subquery("audience")
        recipient = account.alias("recipient")
        author = account.alias("author")
        d = notification_delivery
        delivered = exists().where(
            d.c.account_id == recipient.c.id,
            d.c.dedupe_key == func.concat("ann:", _A.c.id),
            or_(
                d.c.status.in_(("sent", "blocked")),
                and_(d.c.status == "failed", d.c.attempts >= MAX_ATTEMPTS),
                and_(d.c.status == "claimed", d.c.updated_at >= func.now() - STALE_CLAIM),
            ),
        )
        reachable = or_(
            _NS.c.unreachable_at.is_(None), _NS.c.unreachable_at < recipient.c.last_seen_at
        )
        stmt = (
            select(
                _A.c.id,
                _A.c.author_id,
                _A.c.shala_id,
                _A.c.text,
                _A.c.created_at,
                shala.c.name.label("shala_name"),
                author.c.display_name.label("author_name"),
                _author_current().label("author_current"),
                recipient.c.id.label("account_id"),
                recipient.c.locale,
                recipient.c.timezone,
                identity.c.provider_user_id,
                _NS.c.quiet_start,
                _NS.c.quiet_end,
            )
            .select_from(
                audience.join(_A, _A.c.id == audience.c.aid)
                .join(author, author.c.id == _A.c.author_id)
                .join(recipient, recipient.c.id == audience.c.account_id)
                .join(
                    identity,
                    and_(
                        identity.c.account_id == recipient.c.id,
                        identity.c.provider == "telegram",
                    ),
                )
                .outerjoin(_NS, _NS.c.account_id == recipient.c.id)
                .outerjoin(shala, shala.c.id == _A.c.shala_id)
            )
            .where(
                audience.c.joined <= _A.c.created_at,
                audience.c.muted.is_(False),
                func.coalesce(_NS.c.announcements_on, True),
                reachable,
                ~delivered,
            )
            .order_by(_A.c.created_at, recipient.c.id)
            .limit(limit)
        )
        async with connection(self._engine) as conn:
            rows = (await conn.execute(stmt)).all()
        out: list[DueAnnouncement] = []
        for row in rows:
            locale: Locale = row.locale if row.locale in LOCALES else DEFAULT_LOCALE
            quiet = (
                QuietHours(row.quiet_start, row.quiet_end)
                if row.quiet_start is not None and row.quiet_end is not None
                else DEFAULTS.quiet
            )
            source_name = row.shala_name if row.shala_id is not None else row.author_name
            out.append(
                DueAnnouncement(
                    row.id,
                    _source_of(row.author_id, row.shala_id),
                    source_name,
                    row.author_name if row.author_current else None,
                    row.text,
                    row.created_at,
                    row.account_id,
                    row.provider_user_id,
                    locale,
                    row.timezone,
                    quiet,
                )
            )
        return out

    async def prune(self, before: datetime) -> int:
        stmt = delete(_A).where(_A.c.created_at < before)
        async with connection(self._engine) as conn:
            return (await conn.execute(stmt)).rowcount
