"""The calendar feed (SC-06, ADR-0036): a personal subscription URL for calendar apps.

The token is the authentication: a poll finds the account by the token's hash, then reads My
schedule's windows (filter All) and my own moon days in one more statement. Membership
policies still apply per shala (`my_rows`). Nothing from the log, diary, check-ins, rest or 🌸
is read: the feed is the schedule and the moon calendar only. Cancelled occurrences are left
out (Q147); 1:1 classes show their type only (Q150).
"""

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from urllib.parse import quote, urlsplit
from uuid import UUID
from zoneinfo import ZoneInfo

from tristhana.application.classes import MyRow, Only, my_rows, type_name
from tristhana.application.policies import Principal
from tristhana.application.ports.calendar_feed import (
    CalendarFeedRepository,
    FeedLink,
    TokenSource,
)
from tristhana.application.ports.classes import MyWindows, ScheduleRepository
from tristhana.application.ports.i18n import DateArg, TimeArg, Translator
from tristhana.application.ports.storage import Clock
from tristhana.domain.accounts import moon_follow_of
from tristhana.domain.calendar_feed import (
    MAX_EVENTS,
    TOKEN_RE,
    FeedEvent,
    FeedWindow,
    uid_class,
    uid_moon,
)
from tristhana.domain.classes import ClassType
from tristhana.domain.locale import Locale
from tristhana.domain.moon import Cities, MoonDayKind

_READ = timedelta(days=2)  # offsets span -12..+14: a class on a UTC date is within 2 of its own


@dataclass(frozen=True, slots=True)
class Feed:
    name: str
    stamp: datetime  # the link's creation: a stable DTSTAMP, so a poll renders the same bytes
    events: tuple[FeedEvent, ...]


def token_hash(token: str) -> bytes:
    """The lookup key (256 bits of entropy need no salt)."""
    return hashlib.sha256(token.encode()).digest()


class GetFeedLink:
    def __init__(self, feeds: CalendarFeedRepository) -> None:
        self._feeds = feeds

    async def execute(self, principal: Principal) -> FeedLink | None:
        return await self._feeds.get(principal.account.id)


class CreateFeedLink:
    """Create my link, or keep the one I have: a stale "Create" (an old bot message, a second
    tab) must not silently break a subscribed calendar. `rotate`: always a new token; the old
    one stops working in the same write ("New link", after a confirmation)."""

    def __init__(self, feeds: CalendarFeedRepository, tokens: TokenSource) -> None:
        self._feeds, self._tokens = feeds, tokens

    async def execute(self, principal: Principal, rotate: bool = False) -> FeedLink:
        me = principal.account.id
        if not rotate:
            current = await self._feeds.get(me)
            if current is not None:
                return current
        token = self._tokens.new()
        return await self._feeds.replace(me, token_hash(token), token)


class RevokeFeedLink:
    def __init__(self, feeds: CalendarFeedRepository) -> None:
        self._feeds = feeds

    async def execute(self, principal: Principal) -> None:
        await self._feeds.delete(principal.account.id)


class GetCalendarFeed:
    def __init__(
        self,
        feeds: CalendarFeedRepository,
        schedule: ScheduleRepository,
        clock: Clock,
        cities: Cities,
        translator: Translator,
    ) -> None:
        self._feeds, self._schedule, self._clock = feeds, schedule, clock
        self._cities, self._t = cities, translator

    async def execute(self, token: str) -> Feed | None:
        """None: a malformed, unknown, rotated or revoked token, or a deleted account (the
        route answers all of them with the same 404). Two statements."""
        if TOKEN_RE.fullmatch(token) is None:
            return None
        today = self._clock.now().astimezone(UTC).date()
        owner = await self._feeds.account_by_token(token_hash(token), today)
        if owner is None:
            return None
        account = owner.account
        locale = account.locale
        follow = moon_follow_of(account, self._cities)
        first = today - timedelta(days=FeedWindow.CLASSES_BACK)
        end = today + timedelta(days=FeedWindow.CLASSES_AHEAD)
        found = await self._schedule.member_windows(
            account.id,
            first - _READ,
            end + _READ,
            moon_city=follow.city.slug,
            moon_end=today + timedelta(days=FeedWindow.MOON_AHEAD),
            moon_start=today - timedelta(days=FeedWindow.MOON_BACK),
            attendance=False,  # SC-05 marks and counts are not in the feed
        )
        bound = _expansion_end(found, first, end)
        rows, refs, names = my_rows(found, self._cities, "UTC", first, bound, account.id, Only.ALL)
        live = [r for r in rows if r.occurrence.cancelled is None]  # cancellations: out (Q147)
        if bound < end and len(live) < MAX_EVENTS:  # closures ate the margin: the whole window
            rows, refs, names = my_rows(
                found, self._cities, "UTC", first, end, account.id, Only.ALL
            )
            live = [r for r in rows if r.occurrence.cancelled is None]
        moons = sorted(found.my_moon_kinds.items())
        # Pick the nearest MAX_EVENTS first (Q148), then build only those.
        picked: list[tuple[datetime, MyRow | tuple[date, MoonDayKind]]] = [
            (r.occurrence.starts_at, r) for r in live
        ]
        picked += [(datetime.combine(d, time(0), UTC), (d, k)) for d, k in moons]
        picked.sort(key=lambda p: p[0])
        shalas = {r.id: r.name for r in refs}
        mine = account.timezone or "UTC"
        note = self._t.t(locale, "moon-calc-note", city=follow.city.name(locale))
        texts = _Texts(self._t, locale)
        events: list[FeedEvent] = []
        for _, item in picked[:MAX_EVENTS]:
            if isinstance(item, MyRow):
                staff = names.get(item.shala_id, {})
                events.append(self._class(texts, item, shalas[item.shala_id], staff, mine))
            else:
                events.append(self._moon(texts, *item, note))
        return Feed(
            name=self._t.t(locale, "ics-calendar-name"),
            stamp=owner.created_at,
            events=tuple(events),
        )

    def _name(self, texts: "_Texts", staff: Mapping[UUID, str | None], who: UUID | None) -> str:
        found = None if who is None else staff.get(who)
        return found or texts.get("link-no-name")

    def _class(
        self,
        texts: "_Texts",
        r: MyRow,
        shala: str,
        staff: Mapping[UUID, str | None],
        mine: str,
    ) -> FeedEvent:
        o = r.occurrence
        what = texts.type_name(o.type)
        if o.title and o.type is not ClassType.PRIVATE:  # a 1:1 title may name a client
            what = o.title  # a class's own title wins
        summary = what
        if o.teacher_id is not None:  # whoever teaches that date (a substitute too)
            teacher = self._name(texts, staff, o.teacher_id)
            summary = texts.get("ics-class", what=what, teacher=teacher)
        lines = [shala]
        if o.online:
            lines.append(texts.get("ics-desc-online"))
        start = o.starts_at
        there = start.astimezone(ZoneInfo(r.zone))
        if there.utcoffset() != start.astimezone(ZoneInfo(mine)).utcoffset():
            at = TimeArg(there.date(), there.time(), r.zone, self._cities.find(r.city))
            lines.append(texts.get("ics-desc-time", time=at))
        if o.substitute and o.planned_teacher is not None:
            lines.append(
                texts.get(
                    "schedule-covering-for",
                    name=self._name(texts, staff, o.teacher_id),
                    teacher=self._name(texts, staff, o.planned_teacher),
                )
            )
        if o.moved and o.on != o.key and o.planned is not None:
            planned = TimeArg(o.key, o.planned, r.zone, self._cities.find(r.city))
            moved = texts.get("schedule-moved", day=DateArg(o.key), time=planned)
            lines.append(moved)
        if o.swapped_from is not None:
            lines.append(texts.get("schedule-swapped-from", day=DateArg(o.swapped_from)))
        if o.moon:
            lines.append(texts.get("ics-desc-held-moon"))
        length = (
            timedelta(hours=o.end.hour, minutes=o.end.minute)
            - timedelta(hours=o.start.hour, minutes=o.start.minute)
        ) % timedelta(days=1) or timedelta(days=1)
        return FeedEvent(
            uid=uid_class(o.class_id, o.key),
            summary=summary,
            description="\n".join(lines),
            location=None if o.online else shala,
            start=start,
            end=start + length,
            all_day=False,
        )

    def _moon(self, texts: "_Texts", day: date, kind: MoonDayKind, note: str) -> FeedEvent:
        return FeedEvent(
            uid=uid_moon(day, kind),
            summary=texts.get("moon-phase-long", phase=kind.phase.value),
            description=note,
            location=None,
            start=day,
            end=day + timedelta(days=1),
            all_day=True,
        )


class _Texts:
    """One poll's translations, memoized: a feed repeats the same few titles many times."""

    def __init__(self, translator: Translator, locale: Locale) -> None:
        self._t = translator
        self._locale: Locale = locale
        self._seen: dict[tuple[str, tuple[tuple[str, object], ...]], str] = {}
        self._types: dict[ClassType, str] = {}

    def get(self, key: str, **args: str | int | DateArg | TimeArg) -> str:
        memo = (key, tuple(sorted(args.items())))
        found = self._seen.get(memo)
        if found is None:
            found = self._seen[memo] = self._t.t(self._locale, key, **args)
        return found

    def type_name(self, type: ClassType) -> str:
        found = self._types.get(type)
        if found is None:
            found = self._types[type] = type_name(self._t, self._locale, type)
        return found


def _expansion_end(found: MyWindows, first: date, end: date) -> date:
    """Q148 keeps the nearest MAX_EVENTS: when the classes would clearly overflow it, expand
    only the days that hold them (a quarter to spare) instead of weeks that would be dropped.
    Counted day by day from `first`, each series only between its own start and end; the cap
    still cuts exactly, this only bounds the work for very busy accounts."""
    series = [
        (c.starts_on, c.ends_on, len(c.weekdays) / (7 * c.every))
        for w in found.windows
        for c in w.classes
        if c.weekdays and c.starts_on <= end and (c.ends_on is None or c.ends_on >= first)
    ]
    budget, total, day = MAX_EVENTS * 1.25, 0.0, first
    while day <= end:
        total += sum(
            rate
            for since, until, rate in series
            if since <= day and (until is None or day <= until)
        )
        if total > budget:
            return min(end, day + timedelta(days=1))
        day += timedelta(days=1)
    return end


@dataclass(frozen=True, slots=True)
class FeedUrls:
    feed: str  # https …/ical/v1/{token}.ics: to copy
    google: str  # Google Calendar's add-by-URL page
    subscribe: str  # our https → webcal:// redirect, for Apple and Outlook


def feed_urls(public: str, token: str) -> FeedUrls:
    """`public`: the https base (`PUBLIC_API_URL`). Telegram and `openLink` take only http(s),
    so the webcal:// form is reached through Google's `cid=` or our redirect (Q152)."""
    feed = f"{public}/ical/v1/{token}.ics"
    webcal = webcal_url(public, token)
    return FeedUrls(
        feed=feed,
        google=f"https://calendar.google.com/calendar/r?cid={quote(webcal, safe='')}",
        subscribe=f"{public}/ical/v1/{token}/subscribe",
    )


def webcal_url(public: str, token: str) -> str:
    return f"webcal://{urlsplit(public).netloc}/ical/v1/{token}.ics"


@dataclass(frozen=True, slots=True)
class CalendarFeedUseCases:
    get: GetFeedLink
    create: CreateFeedLink
    revoke: RevokeFeedLink
    feed: GetCalendarFeed
    public_url: str  # empty: the feature is hidden

    @property
    def available(self) -> bool:
        return bool(self.public_url)
