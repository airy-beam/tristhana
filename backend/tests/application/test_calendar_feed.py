"""SC-06 use cases on fakes (spec §3, §7, §8; ADR-0036; Q145-Q156; expert items 1-4).

`GetCalendarFeed.execute(token) -> Feed | None`: a malformed token reads nothing; the token's
hash finds the account (one call, which stamps `fetched_on` with the UTC date); one
`member_windows` read over [first - 2, end + 2] with `moon_end = today + 365`; the rows of My
schedule, filter All, over today - 14 ... today + 56 (UTC dates); every cancelled occurrence
left out (moon, closure, staff, a kept swap original); the summary names the date's actual
teacher, the description "Dana (for Anna)"; a class's own title wins over its type; 1:1 for
staff only, by type, never its title; my own moon days (MD-02) as all-day events with
`moon-phase-long` and `moon-calc-note` verbatim; text in the account's language; the class's
own time label only when its offset differs from mine; at most 2000 events, the furthest
dropped. `CreateFeedLink` / `GetFeedLink` / `RevokeFeedLink`: create = rotate, revoke is
idempotent; `can_manage_calendar_feed` is owner-only.

Assumed constructors (the spec names the use cases, not their wiring):
`GetCalendarFeed(feeds, schedule, clock, cities, translator)`, `CreateFeedLink(feeds,
tokens)`, `GetFeedLink(feeds)`, `RevokeFeedLink(feeds)`; the port shapes are documented in
`tests/calendar_feed_fakes.py`. Class ids are fixed, so UIDs compare across polls."""

import hashlib
import json
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from tests.calendar_feed_fakes import FixedTokens, InMemoryCalendarFeed
from tests.fakes import FixedClock, InMemoryMoon, cities
from tests.moon_follow_fakes import person
from tests.schedule_fakes import InMemorySchedule
from tests.shala_fakes import InMemoryShalas, ShalaAccounts, ShalaLinks
from tristhana.application.calendar_feed import (
    CreateFeedLink,
    Feed,
    GetCalendarFeed,
    GetFeedLink,
    RevokeFeedLink,
)
from tristhana.application.policies import Principal, can_manage_calendar_feed
from tristhana.application.ports.classes import StoredClass
from tristhana.domain.accounts import Account, moon_follow_of
from tristhana.domain.calendar_feed import MAX_EVENTS, FeedEvent
from tristhana.domain.classes import ClassType, Override, OverrideStatus, Swap
from tristhana.domain.locale import Locale
from tristhana.domain.moon import MoonDay, MoonDayKind
from tristhana.domain.shalas import ShalaRole
from tristhana.infrastructure.i18n.fluent import FluentTranslator

NOW = datetime(2026, 11, 9, 3, 0, tzinfo=UTC)  # Mon 9 Nov, 08:00 in Almaty
TODAY = date(2026, 11, 9)
NOV = {d: date(2026, 11, d) for d in range(1, 31)}
FIRST, LAST = date(2026, 10, 26), date(2027, 1, 4)  # today - 14, today + 56
MON_FRI = frozenset({1, 2, 3, 4, 5})
EVERY_DAY = frozenset(range(1, 8))
ALMATY, BERLIN = "Asia/Almaty", "Europe/Berlin"

TOKEN_1 = "Xy3kP9qR2sT5uV8wZ1aB4cD7eF0gH3iJ6kL9mN2oP5q"
TOKEN_2 = "Qm7nB4vC1xZ8lK5jH2gF9dS6aP3oI0uY7tR4eW1q-_A"
TOKEN_3 = "Lp0oK9iJ8uH7yG6tF5rD4eS3wA2qZ1xC0vB9nM8_-Ab"

MYSORE = UUID("5c000000-0000-4000-8000-000000000001")
LED = UUID("5c000000-0000-4000-8000-000000000002")
PRIVATE = UUID("5c000000-0000-4000-8000-000000000003")
HIDDEN = UUID("5c000000-0000-4000-8000-000000000004")
BERLIN_MYSORE = UUID("5c000000-0000-4000-8000-000000000005")

# What the app stores for Mysuru in 2025: our port of generator.py (owner-verified), not SYC's
# posted list. The two differ on 27/28 Feb and 4 Dec (kshaya days; the generator wins, owner
# 2026-10-18, see tests/fixtures/moon/syc_2025.json).
_MYSURU = json.loads(
    (
        Path(__file__).resolve().parents[1] / "fixtures" / "moon" / "generator" / "mysuru.json"
    ).read_text()
)
MYSURU_2025: list[tuple[date, MoonDayKind]] = [
    (date.fromisoformat(day), MoonDayKind(kind))
    for day, kind in _MYSURU["events"]
    if day.startswith("2025-")
]


def _ov(on: date, status: OverrideStatus | None = None, **kw: Any) -> Override:
    values: dict[str, Any] = {"moved_to": None, "start": None, "minutes": None, "teacher_id": None}
    values.update(kw)
    return Override(on_date=on, status=status, **values)


def _hash(token: str) -> bytes:
    return hashlib.sha256(token.encode()).digest()


@dataclass
class World:
    instant: datetime = NOW
    clock: FixedClock = field(init=False)
    accounts: ShalaAccounts = field(init=False)
    links: ShalaLinks = field(init=False)
    shalas: InMemoryShalas = field(init=False)
    moon: InMemoryMoon = field(init=False)
    schedule: InMemorySchedule = field(init=False)
    feeds: InMemoryCalendarFeed = field(init=False)
    tokens: FixedTokens = field(init=False)

    def __post_init__(self) -> None:
        self.clock = FixedClock(self.instant)
        self.accounts = ShalaAccounts(clock=self.clock)
        self.links = ShalaLinks(self.accounts)
        self.shalas = InMemoryShalas(self.accounts, self.links)
        self.links.shalas = self.shalas
        self.accounts.links = self.links
        self.accounts.shalas = self.shalas
        self.moon = InMemoryMoon()
        self.schedule = InMemorySchedule(self.shalas, self.moon)
        self.feeds = InMemoryCalendarFeed(self.accounts)
        self.tokens = FixedTokens([TOKEN_1, TOKEN_2, TOKEN_3])

    # Seeding

    def person(self, telegram_id: str, name: str, zone: str | None = ALMATY, **kw: Any) -> Account:
        return person(self.accounts, telegram_id, name, zone=zone, **kw)

    def me(self, account: Account) -> Principal:
        return Principal(self.accounts.inputs(self.accounts.accounts[account.id]))

    def shala(self, owner: Account, city: str = "almaty", **kw: Any) -> UUID:
        return self.shalas.add_shala(owner.id, city=city, **kw).id

    def add_class(self, shala: UUID, class_id: UUID, **kw: Any) -> StoredClass:
        """A class with a fixed id (the fake's `add_class` draws a new uuid per call)."""
        values: dict[str, Any] = {
            "type": ClassType.MYSORE,
            "title": None,
            "online": False,
            "city": None,
            "teacher_id": None,
            "start": time(6, 0),
            "minutes": 150,
            "weekdays": MON_FRI,
            "every": 1,
            "starts_on": date(2026, 9, 1),
            "ends_on": None,
        }
        values.update(kw)
        row = StoredClass(id=class_id, **values)
        self.schedule.classes[class_id] = (shala, row)
        return row

    def moon_days(self, city: str, *days: date, kind: MoonDayKind = MoonDayKind.PURNIMA) -> None:
        self.moon.days_by_location[city] = [MoonDay(d, kind) for d in days]

    def link(self, student: Account, teacher: Account) -> None:
        self.links.add(student.id, teacher.id, primary=True)

    # The use cases

    def feed(self) -> GetCalendarFeed:
        return GetCalendarFeed(self.feeds, self.schedule, self.clock, cities(), FluentTranslator())

    async def subscribe(self, who: Account) -> str:
        """A new link each call ("New link": rotate)."""
        link = await CreateFeedLink(self.feeds, self.tokens).execute(self.me(who), rotate=True)
        return link.token

    async def poll(self, token: str) -> Feed | None:
        return await self.feed().execute(token)

    async def feed_of(self, who: Account) -> Feed:
        token = self.feeds.token_of(who.id) or await self.subscribe(who)
        found = await self.poll(token)
        assert found is not None
        return found


@pytest.fixture
def world() -> World:
    return World()


@dataclass
class Cast:
    """Ashtanga Almaty (Anna owns it, Dana on its staff); Sam is a student there."""

    anna: Account
    dana: Account
    sam: Account
    shala: UUID


@pytest.fixture
def cast(world: World) -> Cast:
    anna = world.person("1", "Anna")
    dana = world.person("2", "Dana")
    sam = world.person("4", "Sam")
    shala = world.shala(anna, name="Ashtanga Almaty")
    world.shalas.add_staff(shala, dana.id, ShalaRole.TEACHER)
    world.shalas.add_student(shala, sam.id)
    return Cast(anna, dana, sam, shala)


def _classes(feed: Feed) -> list[FeedEvent]:
    return [e for e in feed.events if not e.all_day]


def _moons(feed: Feed) -> list[FeedEvent]:
    return [e for e in feed.events if e.all_day]


def _of(feed: Feed, class_id: UUID) -> dict[date, FeedEvent]:
    """The events of one class by their UTC date."""
    out: dict[date, FeedEvent] = {}
    for e in _classes(feed):
        if e.uid.startswith(f"{class_id}-"):
            assert isinstance(e.start, datetime)
            out[e.start.astimezone(UTC).date()] = e
    return out


def _calc_note(locale: Locale, slug: str) -> str:
    city = cities().find(slug)
    assert city is not None
    return FluentTranslator().t(locale, "moon-calc-note", city=city.name(locale))


# The read


async def test_a_poll_is_one_lookup_and_one_window_read(world: World, cast: Cast) -> None:
    world.add_class(cast.shala, MYSORE, teacher_id=cast.anna.id)
    token = await world.subscribe(cast.sam)
    world.feeds.calls.clear()
    world.schedule.reads.clear()

    await world.poll(token)

    assert world.feeds.calls == ["account_by_token"]
    assert world.schedule.reads == ["member_windows"]
    slug = moon_follow_of(world.me(cast.sam).account, cities()).city.slug
    [(me, start, end, staff_only, moon_city)] = world.schedule.member_calls
    assert (me, start, end, staff_only, moon_city) == (
        cast.sam.id,
        FIRST - timedelta(days=2),
        LAST + timedelta(days=2),
        False,
        slug,
    )
    assert world.schedule.moon_ends == [TODAY + timedelta(days=365)]


async def test_the_window_uses_the_utc_date() -> None:
    """20:00 UTC on Sun 8 Nov is already Mon 9 Nov in Almaty: the bounds and the poll date
    are the UTC date's."""
    world = World(instant=datetime(2026, 11, 8, 20, 0, tzinfo=UTC))
    sam = world.person("4", "Sam")
    token = await world.subscribe(sam)

    await world.poll(token)

    [(_, start, end, _, _)] = world.schedule.member_calls
    assert (start, end) == (date(2026, 10, 23), date(2027, 1, 5))
    link = await GetFeedLink(world.feeds).execute(world.me(sam))
    assert link is not None
    assert link.fetched_on == NOV[8]


async def test_classes_from_two_weeks_back_to_eight_weeks_ahead(world: World, cast: Cast) -> None:
    world.add_class(cast.shala, MYSORE, teacher_id=cast.anna.id, weekdays=EVERY_DAY)

    feed = await world.feed_of(cast.sam)

    days = sorted(_of(feed, MYSORE))
    assert days[0] == FIRST
    assert days[-1] == LAST
    assert days == [FIRST + timedelta(days=i) for i in range(71)]


async def test_moon_days_from_a_month_back_to_a_year_ahead(world: World) -> None:
    me = world.person("4", "Sam", moon="mysuru")
    world.moon_days(
        "mysuru",
        TODAY - timedelta(days=31),
        TODAY - timedelta(days=10),
        TODAY + timedelta(days=365),
        TODAY + timedelta(days=366),
    )

    feed = await world.feed_of(me)

    assert sorted(e.start for e in _moons(feed)) == [
        TODAY - timedelta(days=10),
        TODAY + timedelta(days=365),
    ]


async def test_the_feed_name_and_stamp(world: World, cast: Cast) -> None:
    """The stamp is the link's creation, so a later poll renders the same DTSTAMP."""
    created = datetime(2026, 11, 1, 9, 15, tzinfo=UTC)
    world.clock.instant = created
    token = await world.subscribe(cast.sam)
    world.clock.instant = NOW

    first = await world.poll(token)
    world.clock.instant = NOW + timedelta(hours=6)
    second = await world.poll(token)

    assert first is not None
    assert second is not None
    assert first.name == "Tristhana: my schedule"
    assert first.stamp == created == second.stamp


# Class events


async def test_a_class_event(world: World, cast: Cast) -> None:
    world.add_class(cast.shala, MYSORE, teacher_id=cast.anna.id)

    feed = await world.feed_of(cast.sam)

    event = _of(feed, MYSORE)[NOV[9]]
    assert event.uid == f"{MYSORE}-20261109@tristhana"
    assert event.summary == "Mysore · Anna"
    assert event.start == datetime(2026, 11, 9, 1, 0, tzinfo=UTC)
    assert event.end == datetime(2026, 11, 9, 3, 30, tzinfo=UTC)
    assert event.all_day is False
    assert "Ashtanga Almaty" in (event.description or "")
    assert "UTC+" not in (event.description or "")  # same offset as mine: no second label


async def test_uids_are_unique_and_stable_across_polls(world: World, cast: Cast) -> None:
    world.add_class(cast.shala, MYSORE, teacher_id=cast.anna.id, weekdays=EVERY_DAY)
    world.add_class(cast.shala, LED, type=ClassType.LED, teacher_id=cast.dana.id,
                    start=time(18, 0), minutes=90)  # fmt: skip
    world.moon_days("almaty", NOV[24])

    first = await world.feed_of(cast.sam)
    second = await world.feed_of(cast.sam)

    uids = [e.uid for e in first.events]
    assert len(uids) == len(set(uids))
    assert uids == [e.uid for e in second.events]
    assert first.events == second.events


@pytest.mark.parametrize(
    ("instant", "days"),
    [
        (
            datetime(2026, 11, 1, 12, 0, tzinfo=UTC),
            {
                date(2026, 10, 23): datetime(2026, 10, 23, 4, 30, tzinfo=UTC),  # CEST
                date(2026, 10, 26): datetime(2026, 10, 26, 5, 30, tzinfo=UTC),  # CET
            },
        ),
        (
            datetime(2027, 3, 21, 12, 0, tzinfo=UTC),
            {
                date(2027, 3, 26): datetime(2027, 3, 26, 5, 30, tzinfo=UTC),  # CET
                date(2027, 3, 29): datetime(2027, 3, 29, 4, 30, tzinfo=UTC),  # CEST
            },
        ),
    ],
    ids=["25-oct-2026", "28-mar-2027"],
)
async def test_a_berlin_class_keeps_its_wall_clock_across_dst(
    instant: datetime, days: dict[date, datetime]
) -> None:
    world = World(instant=instant)
    anna = world.person("1", "Anna", zone=BERLIN)
    me = world.person("4", "Sam", zone=BERLIN)
    shala = world.shala(anna, city="berlin", name="Yoga Berlin")
    world.shalas.add_student(shala, me.id)
    world.add_class(shala, BERLIN_MYSORE, teacher_id=anna.id, start=time(6, 30))

    feed = await world.feed_of(me)

    by_day = _of(feed, BERLIN_MYSORE)
    for day, start in days.items():
        assert by_day[day].start == start
        assert by_day[day].end == start + timedelta(minutes=150)


@pytest.mark.parametrize(
    ("viewer", "label"),
    [
        (ALMATY, True),
        ("Europe/Moscow", True),
        ("America/New_York", True),
        (BERLIN, False),
    ],
)
async def test_the_class_time_label_only_when_the_offsets_differ(viewer: str, label: bool) -> None:
    world = World()
    anna = world.person("1", "Anna", zone=BERLIN)
    me = world.person("4", "Sam", zone=viewer)
    shala = world.shala(anna, city="berlin", name="Yoga Berlin")
    world.shalas.add_student(shala, me.id)
    world.add_class(shala, BERLIN_MYSORE, teacher_id=anna.id, start=time(6, 30))

    feed = await world.feed_of(me)

    description = _of(feed, BERLIN_MYSORE)[NOV[10]].description or ""
    assert ("06:30" in description and "(UTC+1)" in description) is label
    if not label:
        assert "UTC" not in description


@pytest.mark.parametrize(("viewer", "label"), [("Asia/Kathmandu", True), ("Asia/Kolkata", False)])
async def test_a_half_hour_zone_against_a_quarter_hour_one(viewer: str, label: bool) -> None:
    """A Mysuru class (+5:30) seen from Kathmandu (+5:45) carries its own label."""
    world = World()
    anna = world.person("1", "Anna", zone="Asia/Kolkata")
    me = world.person("4", "Sam", zone=viewer)
    shala = world.shala(anna, city="mysuru", name="Mysuru Shala")
    world.shalas.add_student(shala, me.id)
    world.add_class(shala, MYSORE, teacher_id=anna.id, start=time(6, 0))

    feed = await world.feed_of(me)

    event = _of(feed, MYSORE)[NOV[10]]
    assert event.start == datetime(2026, 11, 10, 0, 30, tzinfo=UTC)
    description = event.description or ""
    assert ("06:00" in description and "(UTC+5:30)" in description) is label


async def test_russian_titles(world: World) -> None:
    anna = world.person("1", "Анна")
    me = world.person("4", "Саша", locale="ru", moon="mysuru")
    shala = world.shala(anna, name="Аштанга Алматы")
    world.shalas.add_student(shala, me.id)
    world.add_class(shala, MYSORE, teacher_id=anna.id)
    world.moon_days("mysuru", NOV[24])

    feed = await world.feed_of(me)

    assert feed.name == "Tristhana: моё расписание"
    assert _of(feed, MYSORE)[NOV[9]].summary == "Майсор · Анна"
    [moon] = _moons(feed)
    assert moon.summary == "🌕 Полнолуние (Пурнима)"
    assert moon.description == _calc_note("ru", "mysuru")


async def test_the_language_is_the_accounts_at_poll_time(world: World, cast: Cast) -> None:
    world.add_class(cast.shala, MYSORE, teacher_id=cast.anna.id)
    token = await world.subscribe(cast.sam)

    before = await world.poll(token)
    world.accounts.accounts[cast.sam.id] = replace(
        world.accounts.accounts[cast.sam.id], locale="ru"
    )
    after = await world.poll(token)

    assert before is not None
    assert after is not None
    assert _of(before, MYSORE)[NOV[9]].summary == "Mysore · Anna"
    assert _of(after, MYSORE)[NOV[9]].summary == "Майсор · Anna"


async def test_a_class_title_wins_over_its_type(world: World, cast: Cast) -> None:
    world.add_class(cast.shala, LED, type=ClassType.LED, title="Full Primary, counted",
                    teacher_id=cast.anna.id, weekdays=frozenset({5}))  # fmt: skip

    feed = await world.feed_of(cast.sam)

    assert _of(feed, LED)[NOV[13]].summary == "Full Primary, counted · Anna"


async def test_a_substitute_is_named_with_the_planned_teacher(world: World, cast: Cast) -> None:
    world.add_class(cast.shala, MYSORE, teacher_id=cast.anna.id)
    world.schedule.add_override(MYSORE, _ov(NOV[10], teacher_id=cast.dana.id))

    feed = await world.feed_of(cast.sam)

    by_day = _of(feed, MYSORE)
    assert by_day[NOV[10]].summary == "Mysore · Dana"
    assert "Dana (for Anna)" in (by_day[NOV[10]].description or "")
    assert by_day[NOV[9]].summary == "Mysore · Anna"
    assert "(for " not in (by_day[NOV[9]].description or "")


async def test_a_moved_occurrence_keeps_its_uid(world: World, cast: Cast) -> None:
    world.add_class(cast.shala, MYSORE, teacher_id=cast.anna.id)
    world.schedule.add_override(MYSORE, _ov(NOV[19], moved_to=NOV[21], start=time(8, 0)))

    feed = await world.feed_of(cast.sam)

    by_day = _of(feed, MYSORE)
    assert NOV[19] not in by_day
    moved = by_day[NOV[21]]
    assert moved.uid == f"{MYSORE}-20261119@tristhana"
    assert moved.start == datetime(2026, 11, 21, 3, 0, tzinfo=UTC)
    assert "↪" in (moved.description or "")


async def test_a_swapped_occurrence_keeps_its_uid_and_its_original_is_gone(
    world: World, cast: Cast
) -> None:
    """Thu 12 Nov is the shala's moon day (closed); its classes are held on Sat 14 Nov."""
    world.add_class(cast.shala, MYSORE, teacher_id=cast.anna.id)
    world.moon_days("almaty", NOV[12])
    world.schedule.swaps[(cast.shala, NOV[12])] = Swap(NOV[12], NOV[14])

    feed = await world.feed_of(cast.sam)

    by_day = _of(feed, MYSORE)
    assert NOV[12] not in by_day  # the kept original (cancelled) is left out
    swapped = by_day[NOV[14]]
    assert swapped.uid == f"{MYSORE}-20261112@tristhana"
    assert "🔁" in (swapped.description or "")
    assert [e.uid for e in _classes(feed)].count(swapped.uid) == 1


# Cancellations (Q147: every one is left out)


async def test_every_cancelled_occurrence_is_left_out(world: World, cast: Cast) -> None:
    world.add_class(cast.shala, MYSORE, teacher_id=cast.anna.id)
    world.moon_days("almaty", NOV[12])  # closed policy: the moon cancels Thursday
    world.schedule.seed_closure(cast.shala, NOV[16], NOV[17])
    world.schedule.add_override(MYSORE, _ov(NOV[18], OverrideStatus.CANCELLED))

    feed = await world.feed_of(cast.sam)

    days = set(_of(feed, MYSORE))
    assert {NOV[11], NOV[13], NOV[19]} <= days
    assert not {NOV[12], NOV[16], NOV[17], NOV[18]} & days


async def test_a_class_held_on_the_moon_day_is_in_with_its_line(world: World, cast: Cast) -> None:
    world.add_class(cast.shala, MYSORE, teacher_id=cast.anna.id)
    world.moon_days("almaty", NOV[12])
    world.schedule.add_override(MYSORE, _ov(NOV[12], OverrideStatus.HELD))

    feed = await world.feed_of(cast.sam)

    held = _of(feed, MYSORE)[NOV[12]]
    assert "🌙" in (held.description or "")
    assert "🌙" not in (_of(feed, MYSORE)[NOV[11]].description or "")


async def test_the_shalas_moon_day_and_mine_differ_by_a_day(world: World) -> None:
    """Expert item 3, pinned as expected behaviour (spec §9): the Almaty shala closes on its
    moon date, Fri 13 Nov; my own city (Mysuru, chosen) has it on Sat 14 Nov. Friday's class
    simply is not there and my all-day 🌕 sits on Saturday; no event marks Friday."""
    anna = world.person("1", "Anna")
    me = world.person("4", "Sam", moon="mysuru")
    shala = world.shala(anna, name="Ashtanga Almaty")
    world.shalas.add_student(shala, me.id)
    world.add_class(shala, MYSORE, teacher_id=anna.id)
    world.moon_days("almaty", NOV[13])
    world.moon_days("mysuru", NOV[14])
    assert moon_follow_of(world.me(me).account, cities()).city.slug == "mysuru"

    feed = await world.feed_of(me)

    assert NOV[13] not in _of(feed, MYSORE)
    assert NOV[12] in _of(feed, MYSORE)
    assert [e.start for e in _moons(feed)] == [NOV[14]]  # nothing all-day on Friday


# 1:1 and privacy


async def test_a_private_class_for_staff_by_type_only(world: World, cast: Cast) -> None:
    world.add_class(cast.shala, PRIVATE, type=ClassType.PRIVATE, title="Ivan, knee rehab",
                    teacher_id=cast.anna.id, start=time(12, 0), minutes=60)  # fmt: skip

    staff = await world.feed_of(cast.dana)
    student = await world.feed_of(cast.sam)

    event = _of(staff, PRIVATE)[NOV[9]]
    assert event.summary == "1:1 · Anna"
    assert "Ivan" not in (event.description or "")
    assert "Ivan" not in (event.location or "")
    assert _of(student, PRIVATE) == {}


async def test_a_followed_teachers_other_shala_never_appears(world: World, cast: Cast) -> None:
    hidden = world.shala(cast.anna, city="berlin", name="Anna's Berlin Room")
    world.add_class(hidden, HIDDEN, title="Secret", teacher_id=cast.anna.id)
    world.add_class(cast.shala, MYSORE, teacher_id=cast.anna.id)
    world.link(cast.sam, cast.anna)

    feed = await world.feed_of(cast.sam)

    assert _of(feed, HIDDEN) == {}
    assert all("Secret" not in e.summary for e in feed.events)
    assert all("Berlin Room" not in (e.description or "") for e in feed.events)
    assert _of(feed, MYSORE)


async def test_without_a_shala_only_my_moon_days(world: World) -> None:
    lone = world.person("50", "Lone", moon="mysuru")
    world.moon_days("mysuru", NOV[24])

    feed = await world.feed_of(lone)

    assert _classes(feed) == []
    assert [e.start for e in _moons(feed)] == [NOV[24]]


async def test_leaving_a_shala_drops_its_classes_on_the_next_poll(world: World, cast: Cast) -> None:
    world.add_class(cast.shala, MYSORE, teacher_id=cast.anna.id)
    token = await world.subscribe(cast.sam)

    before = await world.poll(token)
    del world.shalas.students_rows[(cast.shala, cast.sam.id)]
    after = await world.poll(token)

    assert before is not None
    assert after is not None
    assert _of(before, MYSORE)
    assert _of(after, MYSORE) == {}


async def test_nothing_names_me(world: World, cast: Cast) -> None:
    world.add_class(cast.shala, MYSORE, teacher_id=cast.anna.id)

    feed = await world.feed_of(cast.sam)

    text = " ".join(f"{e.summary} {e.description} {e.location}" for e in feed.events)
    assert "Sam" not in text
    assert "Sam" not in feed.name


# Moon events


async def test_moon_days_follow_my_inherited_city(world: World) -> None:
    """MD-02: Sam never chose; his teacher chose Mysuru; no shala."""
    anna = world.person("1", "Anna", moon="mysuru")
    sam = world.person("4", "Sam")
    world.link(sam, anna)
    world.moon_days("mysuru", NOV[24])
    world.moon_days("almaty", NOV[25])
    assert moon_follow_of(world.me(sam).account, cities()).city.slug == "mysuru"

    feed = await world.feed_of(sam)

    [moon] = _moons(feed)
    assert moon.start == NOV[24]
    assert moon.end == NOV[25]  # the exclusive end: the next day
    assert moon.all_day is True
    assert moon.summary == "🌕 Full moon (Purnima)"
    assert moon.description == _calc_note("en", "mysuru")


async def test_the_2025_mysuru_moon_days_kshaya_included() -> None:
    world = World(instant=datetime(2025, 1, 1, 3, 0, tzinfo=UTC))
    me = world.person("4", "Sam", moon="mysuru")
    world.moon.days_by_location["mysuru"] = [MoonDay(d, k) for d, k in MYSURU_2025]

    feed = await world.feed_of(me)

    moons = sorted(_moons(feed), key=lambda e: e.start)  # type: ignore[arg-type, return-value]
    assert [e.start for e in moons] == [d for d, _ in MYSURU_2025]
    assert [e.summary for e in moons] == [
        "🌕 Full moon (Purnima)" if k.phase.value == "purnima" else "🌑 New moon (Amavasya)"
        for _, k in MYSURU_2025
    ]  # a kshaya day reads like any other (no label)
    assert len({e.uid for e in moons}) == 24
    kshaya = {d for d, k in MYSURU_2025 if k.value.startswith("kshaya")}
    assert kshaya == {date(2025, 2, 27), date(2025, 12, 4)}
    assert date(2025, 2, 28) not in {e.start for e in moons}  # SYC posted 28 Feb


@pytest.mark.parametrize(
    ("kind", "summary"),
    [
        (MoonDayKind.KSHAYA_PURNIMA, "🌕 Full moon (Purnima)"),
        (MoonDayKind.KSHAYA_AMAVASYA, "🌑 New moon (Amavasya)"),
    ],
)
async def test_a_kshaya_day_reads_like_any_moon_day(
    world: World, kind: MoonDayKind, summary: str
) -> None:
    me = world.person("4", "Sam", moon="mysuru")
    world.moon_days("mysuru", NOV[24], kind=kind)

    feed = await world.feed_of(me)

    [moon] = _moons(feed)
    assert moon.summary == summary
    assert "kshaya" not in f"{moon.summary} {moon.description}".lower()


@pytest.mark.parametrize("locale", ["en", "ru"])
async def test_the_moon_description_is_the_calc_note_verbatim(world: World, locale: Locale) -> None:
    me = world.person("4", "Sam", moon="almaty", locale=locale)
    world.moon_days("almaty", NOV[24])

    feed = await world.feed_of(me)

    [moon] = _moons(feed)
    assert moon.description == _calc_note(locale, "almaty")


# The cap


async def test_at_most_2000_events_the_furthest_dropped(world: World, cast: Cast) -> None:
    """30 daily classes over 71 days are 2130 events, plus my moon days."""
    for i in range(30):
        world.add_class(
            cast.shala, UUID(int=0x5C00_0000_0000_4000_8000_0000_0000_1000 + i),
            weekdays=EVERY_DAY, start=time(5 + i % 15, 30 * (i // 15)), minutes=30,
            teacher_id=cast.anna.id,
        )  # fmt: skip
    me = cast.sam
    world.accounts.accounts[me.id] = replace(world.accounts.accounts[me.id], moon_location="almaty")
    world.moon_days("almaty", NOV[24], date(2027, 5, 20))

    feed = await world.feed_of(me)

    assert len(feed.events) == MAX_EVENTS
    classes = _classes(feed)
    starts = [e.start for e in classes]
    first_day = [s for s in starts if isinstance(s, datetime) and s.date() == FIRST]
    assert len(first_day) == 30  # the nearest are all kept
    assert all(isinstance(s, datetime) and s.date() < LAST for s in starts)  # the furthest go
    assert [e.start for e in _moons(feed)] == [NOV[24]]  # May 2027 is beyond the kept range


# Tokens


async def test_a_malformed_token_reads_nothing(world: World) -> None:
    for token in ("", "short", TOKEN_1 + "x", TOKEN_1[:-1] + "+", "../" * 15):
        assert await world.poll(token) is None
    assert world.feeds.calls == []
    assert world.schedule.reads == []


async def test_an_unknown_token_is_none(world: World) -> None:
    assert await world.poll(TOKEN_1) is None
    assert world.schedule.reads == []


async def test_a_deleted_account_is_none(world: World, cast: Cast) -> None:
    token = await world.subscribe(cast.sam)

    await world.accounts.delete(cast.sam.id)

    assert await world.poll(token) is None
    assert world.schedule.reads == []


async def test_create_stores_the_hash_and_shows_the_token(world: World, cast: Cast) -> None:
    world.clock.instant = datetime(2026, 11, 1, 9, 15, tzinfo=UTC)

    link = await CreateFeedLink(world.feeds, world.tokens).execute(world.me(cast.sam))

    assert link.token == TOKEN_1
    assert link.created_at == datetime(2026, 11, 1, 9, 15, tzinfo=UTC)
    assert link.fetched_on is None
    assert world.feeds.rows[cast.sam.id].token_hash == _hash(TOKEN_1)
    shown = await GetFeedLink(world.feeds).execute(world.me(cast.sam))
    assert shown == link


async def test_create_again_rotates(world: World, cast: Cast) -> None:
    old = await world.subscribe(cast.sam)

    new = await world.subscribe(cast.sam)

    assert (old, new) == (TOKEN_1, TOKEN_2)
    assert await world.poll(old) is None
    assert await world.poll(new) is not None
    assert len(world.feeds.rows) == 1


async def test_create_keeps_an_existing_link(world: World, cast: Cast) -> None:
    """Review fix: a stale "Create" (an old bot message, a second tab) returns the current
    link; only an explicit rotate makes a new one."""
    create = CreateFeedLink(world.feeds, world.tokens)
    first = await create.execute(world.me(cast.sam))

    again = await create.execute(world.me(cast.sam))

    assert again == first
    assert world.tokens.issued == 1
    assert await world.poll(first.token) is not None


async def test_revoke_turns_it_off_and_is_idempotent(world: World, cast: Cast) -> None:
    token = await world.subscribe(cast.sam)

    await RevokeFeedLink(world.feeds).execute(world.me(cast.sam))
    await RevokeFeedLink(world.feeds).execute(world.me(cast.sam))

    assert await world.poll(token) is None
    assert await GetFeedLink(world.feeds).execute(world.me(cast.sam)) is None


async def test_off_until_created(world: World, cast: Cast) -> None:
    assert await GetFeedLink(world.feeds).execute(world.me(cast.sam)) is None


async def test_a_poll_stamps_the_day_once(world: World, cast: Cast) -> None:
    token = await world.subscribe(cast.sam)

    await world.poll(token)
    await world.poll(token)
    world.clock.instant = NOW + timedelta(days=1)
    await world.poll(token)

    assert world.feeds.fetch_writes == 2
    link = await GetFeedLink(world.feeds).execute(world.me(cast.sam))
    assert link is not None
    assert link.fetched_on == NOV[10]


async def test_each_account_has_its_own_link(world: World, cast: Cast) -> None:
    sams = await world.subscribe(cast.sam)
    danas = await world.subscribe(cast.dana)

    assert sams != danas
    sam_feed, dana_feed = await world.poll(sams), await world.poll(danas)
    assert sam_feed is not None
    assert dana_feed is not None
    await RevokeFeedLink(world.feeds).execute(world.me(cast.dana))
    assert await world.poll(sams) is not None


def test_only_the_owner_manages_the_link(cast: Cast) -> None:
    assert can_manage_calendar_feed(cast.sam, cast.sam) is True
    assert can_manage_calendar_feed(cast.anna, cast.sam) is False


async def test_the_cap_counts_only_classes_that_have_started(world: World, cast: Cast) -> None:
    """Build regression: 80 daily classes (2480 events) that start 40 days after the window's
    first day. The work bound must count each series from its own start, not as if it ran from
    day one (a first version cut the range before any of them began and returned nothing)."""
    for i in range(80):
        world.add_class(
            cast.shala, UUID(int=0x5C00_0000_0000_4000_8000_0000_0000_2000 + i),
            weekdays=EVERY_DAY, start=time(5 + i % 15, 10 * (i // 15)), minutes=10,
            teacher_id=cast.anna.id, starts_on=FIRST + timedelta(days=40),
        )  # fmt: skip

    feed = await world.feed_of(cast.sam)

    classes = _classes(feed)
    assert len(classes) == MAX_EVENTS
    first_day = min(e.start for e in classes if isinstance(e.start, datetime))
    assert first_day.date() == FIRST + timedelta(days=40)


async def test_a_long_closure_does_not_cost_classes_the_cap_has_room_for(
    world: World, cast: Cast
) -> None:
    """Review fix: 40 daily classes would overflow the cap, so the work bound shortens the
    range; a closure over the first 31 days then leaves room. The whole window comes back:
    (71 - 31) days x 40 = 1600 classes, the last day included."""
    for i in range(40):
        world.add_class(
            cast.shala, UUID(int=0x5C00_0000_0000_4000_8000_0000_0000_3000 + i),
            weekdays=EVERY_DAY, start=time(5 + i % 15, 10 * (i // 15)), minutes=10,
            teacher_id=cast.anna.id,
        )  # fmt: skip
    world.schedule.seed_closure(cast.shala, FIRST, FIRST + timedelta(days=30))

    feed = await world.feed_of(cast.sam)

    classes = _classes(feed)
    assert len(classes) == 1600
    last = max(e.start for e in classes if isinstance(e.start, datetime))
    assert last.date() == LAST


async def test_a_moved_class_names_its_old_time_with_a_zone(world: World, cast: Cast) -> None:
    """Review fix: every displayed time carries its zone label."""
    world.add_class(cast.shala, MYSORE, teacher_id=cast.anna.id)
    world.schedule.add_override(MYSORE, _ov(NOV[19], moved_to=NOV[21], start=time(8, 0)))

    feed = await world.feed_of(cast.sam)

    assert "06:00 Almaty (UTC+5)" in (_of(feed, MYSORE)[NOV[21]].description or "")
