"""MD-02 use cases on fakes (spec §3, §7; ADR-0032): every reader uses the effective city,
"Follow my teacher" is stored, the link use cases say when the student's own tap moved the
city, the teacher's first-student note offers Keep, and `KeepMoonCity` writes only on NULL.

The calendars are fictional and a day apart, so a wrong city shows as a wrong date:
Mysuru 5 Nov, Almaty 4 Nov, Moscow 6 Nov."""

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta

import pytest

from tests.domain.test_practice import catalog
from tests.fakes import (
    FakeCalculator,
    FakePacker,
    FixedClock,
    InMemoryDays,
    InMemoryMoon,
    cities,
    practice_use_cases,
)
from tests.moon_follow_fakes import (
    FollowingAccounts,
    FollowingExport,
    FollowingLinks,
    FollowingNotifications,
    KeepNotifier,
    person,
)
from tristhana.application.days import GetDays
from tristhana.application.export import SendMyExport
from tristhana.application.labels import PracticeLabels
from tristhana.application.moon import (
    GetMoonView,
    KeepMoonCity,
    SetMoonLocation,
    UnknownLocation,
)
from tristhana.application.policies import Principal
from tristhana.application.ports.notifications import KeepOffer
from tristhana.application.ports.teacher_links import Accepted
from tristhana.application.stats import GetYearStats
from tristhana.application.teacher_links import AcceptInvite, RemoveTeacher, SetPrimaryTeacher
from tristhana.application.tick import RunTick
from tristhana.domain.accounts import Account
from tristhana.domain.days import DayLog, DayStatus
from tristhana.domain.moon import (
    FOLLOW_TEACHER,
    City,
    MoonDay,
    MoonDayKind,
    MoonFollow,
    MoonSource,
    TeacherMoon,
    calendar_years,
)
from tristhana.domain.notifications import moon_key, send_instant
from tristhana.domain.progression import Track
from tristhana.domain.rest_days import AutoDay, AutoKind
from tristhana.infrastructure.i18n.fluent import FluentTranslator

ZONE = "Asia/Almaty"
NOW = datetime(2026, 11, 7, 6, 0, tzinfo=UTC)  # 11:00 in Almaty
CODE = "aB3dE6gH9jK2mN5p"
OTHER_CODE = "Zy8xW7vU6tS5rQ4p"
MYSURU = MoonDay(date(2026, 11, 5), MoonDayKind.PURNIMA)
ALMATY = MoonDay(date(2026, 11, 4), MoonDayKind.PURNIMA)
MOSCOW = MoonDay(date(2026, 11, 6), MoonDayKind.PURNIMA)
BY_CITY = {"mysuru": MYSURU, "almaty": ALMATY, "moscow": MOSCOW}


def _city(slug: str) -> City:
    found = cities().find(slug)
    assert found is not None
    return found


@dataclass
class World:
    clock: FixedClock = field(default_factory=lambda: FixedClock(NOW))
    accounts: FollowingAccounts = field(init=False)
    links: FollowingLinks = field(init=False)
    moon: InMemoryMoon = field(init=False)
    notifier: KeepNotifier = field(default_factory=KeepNotifier)

    def __post_init__(self) -> None:
        self.accounts = FollowingAccounts(clock=self.clock)
        self.links = FollowingLinks(self.accounts)
        self.accounts.links = self.links
        self.moon = InMemoryMoon({slug: [day] for slug, day in BY_CITY.items()})

    def person(self, tg: str, name: str | None = "Person", moon: str | None = None) -> Account:
        return person(self.accounts, tg, name, moon=moon, zone=ZONE)

    def teacher(self, tg: str, name: str, moon: str | None, code: str = CODE) -> Account:
        account = self.person(tg, name, moon)
        self.links.codes[account.id] = code
        return account

    def link(self, student: Account, teacher: Account, primary: bool = False) -> None:
        self.links.add(student.id, teacher.id, primary=primary)

    def me(self, account: Account) -> Principal:
        """The caller as the middleware loads them: with `teaches` and the main teacher."""
        return Principal(self.accounts.inputs(self.accounts.stored(account.id)))

    def stored(self, account: Account) -> str | None:
        return self.accounts.stored(account.id).moon_location

    def tm(self, account: Account) -> TeacherMoon:
        a = self.accounts.stored(account.id)
        return TeacherMoon(a.id, a.display_name, a.moon_location)

    def view(self) -> GetMoonView:
        return GetMoonView(cities(), self.moon, FollowingNotifications(self.accounts), self.clock)


@pytest.fixture
def world() -> World:
    return World()


# Every reader uses the effective city (spec §3's list).

# (student's own, teacher's own, the student teaches, expected city)
CASES = [
    pytest.param(None, "almaty", False, "almaty", id="never-chose-follows-teacher"),
    pytest.param("moscow", "almaty", False, "moscow", id="chosen-wins"),
    pytest.param(FOLLOW_TEACHER, "almaty", False, "almaty", id="follow-chosen"),
    pytest.param(FOLLOW_TEACHER, None, False, "mysuru", id="follow-teacher-without-city"),
    pytest.param(None, FOLLOW_TEACHER, False, "mysuru", id="one-hop"),
    pytest.param(None, "almaty", True, "mysuru", id="has-students-uses-own"),
]


SOURCE: dict[tuple[str | None, str | None, bool], MoonSource] = {
    (None, "almaty", False): MoonSource.TEACHER,
    ("moscow", "almaty", False): MoonSource.CHOSEN,
    (FOLLOW_TEACHER, "almaty", False): MoonSource.TEACHER,
    (FOLLOW_TEACHER, None, False): MoonSource.DEFAULT,
    (None, FOLLOW_TEACHER, False): MoonSource.DEFAULT,
    (None, "almaty", True): MoonSource.DEFAULT,
}


def _setup(world: World, own: str | None, theirs: str | None, teaches: bool) -> Account:
    me = world.person("42", "Ash", own)
    world.link(me, world.teacher("1", "Anna", theirs))
    if teaches:
        world.link(world.person("7", "Student"), me)
    return me


@pytest.mark.parametrize(("own", "theirs", "teaches", "slug"), CASES)
async def test_days_mark_the_effective_citys_moon_day(
    world: World, own: str | None, theirs: str | None, teaches: bool, slug: str
) -> None:
    me = _setup(world, own, theirs, teaches)
    days = InMemoryDays(moon=world.moon)

    view = await GetDays(days, cities(), world.clock).execute(
        world.me(me), date(2026, 11, 1), date(2026, 11, 6)
    )

    assert view.city.slug == slug
    assert view.auto == {BY_CITY[slug].date: AutoDay(AutoKind.MOON)}


@pytest.mark.parametrize(("own", "theirs", "teaches", "slug"), CASES)
async def test_stats_mark_the_effective_citys_moon_days(
    world: World, own: str | None, theirs: str | None, teaches: bool, slug: str
) -> None:
    me = _setup(world, own, theirs, teaches)
    stats = GetYearStats(
        InMemoryDays(), world.moon, cities(), practice_use_cases().catalog, world.clock
    )

    view = await stats.execute(world.me(me))

    assert view.city.slug == slug
    assert [d.date for d in view.moon_days] == [BY_CITY[slug].date]


@pytest.mark.parametrize(("own", "theirs", "teaches", "slug"), CASES)
async def test_the_moon_view_shows_the_effective_city(
    world: World, own: str | None, theirs: str | None, teaches: bool, slug: str
) -> None:
    me = _setup(world, own, theirs, teaches)

    view = await world.view().execute(world.me(me), date(2026, 11, 1), date(2026, 11, 30))

    assert view.city.slug == slug
    assert view.follow is not None
    assert view.follow.city.slug == slug
    assert [d.date for d in view.days] == [BY_CITY[slug].date]


@pytest.mark.parametrize(("own", "theirs", "teaches", "slug"), CASES)
async def test_the_export_names_the_effective_city_and_its_source_only(
    world: World, own: str | None, theirs: str | None, teaches: bool, slug: str
) -> None:
    me = _setup(world, own, theirs, teaches)
    packer = FakePacker()
    t = FluentTranslator()
    export = SendMyExport(
        FollowingExport(world.accounts),
        packer,
        KeepNotifier(),
        t,
        PracticeLabels(t, catalog(), Track(catalog())),
        cities(),
        "cat-v1",
        world.clock,
    )

    await export.execute(world.me(me))

    [(data, _, _)] = packer.packed
    source = SOURCE[(own, theirs, teaches)]
    assert data["account"]["moon_city"] == {  # type: ignore[index]
        "slug": slug,
        "default": source is MoonSource.DEFAULT,
        "source": source.value,
    }


@pytest.mark.parametrize(("own", "theirs", "teaches", "slug"), CASES)
async def test_moon_reminders_follow_the_effective_city(
    world: World, own: str | None, theirs: str | None, teaches: bool, slug: str
) -> None:
    me = _setup(world, own, theirs, teaches)
    for city in cities().all:  # calendars already computed
        for year in calendar_years(NOW.date()):
            world.moon.ledger[(city.slug, year)] = FakeCalculator.version
    day = BY_CITY[slug]
    evening = send_instant(day.date - timedelta(days=1), time(19), ZONE)
    notifier = KeepNotifier()
    tick = RunTick(
        FixedClock(evening),
        cities(),
        world.moon,
        FakeCalculator(),
        FollowingNotifications(world.accounts),
        notifier,
    )

    await tick.execute(timedelta(seconds=40))

    mine = [r for recipient, r in notifier.moon if recipient.telegram_id == "42"]
    assert [(r.city.slug, r.moon_day) for r in mine] == [(slug, day)]
    assert world.stored(me) == own  # read, never written


async def test_a_city_that_moved_by_a_day_doesnt_send_a_second_week_before(world: World) -> None:
    """The 7-day reminder went out for Almaty's 4 Nov; the teacher then chose Mysuru (5 Nov)."""
    me = _setup(world, None, "mysuru", False)
    for city in cities().all:
        for year in calendar_years(NOW.date()):
            world.moon.ledger[(city.slug, year)] = FakeCalculator.version
    notifications = FollowingNotifications(world.accounts)
    notifications.deliveries[(me.id, moon_key(ALMATY.date, 7))] = {
        "status": "sent",
        "attempts": 1,
        "local_date": date(2026, 10, 28),
    }
    notifier = KeepNotifier()
    week_before = send_instant(MYSURU.date - timedelta(days=7), time(19), ZONE)
    tick = RunTick(
        FixedClock(week_before), cities(), world.moon, FakeCalculator(), notifications, notifier
    )

    await tick.execute(timedelta(seconds=40))

    assert [r for recipient, r in notifier.moon if recipient.telegram_id == "42"] == []


async def test_a_logged_moon_day_stays_after_the_city_changes(world: World) -> None:
    """Logged 🌙 rows are statements (spec §6): only unlogged days re-derive."""
    me = _setup(world, None, "almaty", False)
    days = InMemoryDays(moon=world.moon)
    days.rows[(me.id, MYSURU.date)] = (DayLog(MYSURU.date, DayStatus.MOON), None)

    view = await GetDays(days, cities(), world.clock).execute(
        world.me(me), date(2026, 11, 1), date(2026, 11, 6)
    )

    assert [(d.local_date, d.status) for d in view.days] == [(MYSURU.date, DayStatus.MOON)]
    assert view.auto == {ALMATY.date: AutoDay(AutoKind.MOON)}


# SetMoonLocation and GetMoonView.


async def test_none_stores_follow_my_teacher(world: World) -> None:
    me = world.person("42", "Ash", "almaty")

    saved = await SetMoonLocation(cities(), world.accounts).execute(world.me(me), None)

    assert saved.moon_location == FOLLOW_TEACHER
    assert world.stored(me) == FOLLOW_TEACHER


async def test_follow_my_teacher_works_with_no_teacher_yet(world: World) -> None:
    me = world.person("42", "Ash", "almaty")
    await SetMoonLocation(cities(), world.accounts).execute(world.me(me), None)

    view = await world.view().execute(world.me(me))

    assert view.follow == MoonFollow(cities().default, MoonSource.DEFAULT, None, True)
    assert view.explicit is True


async def test_the_sentinel_is_no_slug(world: World) -> None:
    me = world.person("42", "Ash", "almaty")

    with pytest.raises(UnknownLocation):
        await SetMoonLocation(cities(), world.accounts).execute(world.me(me), FOLLOW_TEACHER)

    assert world.stored(me) == "almaty"


@pytest.mark.parametrize(
    ("own", "theirs", "explicit"),
    [
        (None, "almaty", False),  # TEACHER by default: not a choice
        (None, None, False),
        (FOLLOW_TEACHER, "almaty", True),
        (FOLLOW_TEACHER, None, True),
        ("moscow", "almaty", True),
        ("mysuru", None, True),
    ],
)
async def test_explicit_is_a_city_or_follow_my_teacher(
    world: World, own: str | None, theirs: str | None, explicit: bool
) -> None:
    me = _setup(world, own, theirs, False)

    view = await world.view().execute(world.me(me))

    assert view.explicit is explicit


async def test_the_view_carries_the_teacher_for_the_source_line(world: World) -> None:
    me = _setup(world, None, "almaty", False)
    [anna] = [a for a in world.accounts.accounts.values() if a.display_name == "Anna"]

    view = await world.view().execute(world.me(me))

    assert view.follow == MoonFollow(_city("almaty"), MoonSource.TEACHER, world.tm(anna), False)


async def test_follow_with_a_teacher_without_a_city_keeps_the_teacher_for_the_none_line(
    world: World,
) -> None:
    me = _setup(world, FOLLOW_TEACHER, None, False)
    [anna] = [a for a in world.accounts.accounts.values() if a.display_name == "Anna"]

    view = await world.view().execute(world.me(me))

    assert view.follow == MoonFollow(cities().default, MoonSource.DEFAULT, world.tm(anna), True)


@pytest.mark.parametrize(
    ("own", "students", "shared"),
    [
        ("almaty", 0, None),  # no students: nothing shared, no line
        (None, 0, None),
        ("almaty", 2, True),
        ("mysuru", 1, True),
        (None, 1, False),  # never chose: shares nothing, the `[no]` variant
    ],
)
async def test_shared_tells_a_teacher_whether_students_follow_their_choice(
    world: World, own: str | None, students: int, shared: bool | None
) -> None:
    me = world.person("42", "Ash", own)
    for i in range(students):
        world.link(world.person(f"{100 + i}", f"S{i}"), me)

    view = await world.view().execute(world.me(me))

    assert view.shared is shared


# The link use cases report a change the student's own tap made (spec §2, §3).


async def _accept(world: World, student: Account, code: str = CODE) -> Accepted | None:
    use_case = AcceptInvite(world.links, world.notifier, world.clock, cities())
    return await use_case.execute(world.me(student), code)


async def test_a_first_link_of_a_never_chose_student_reports_the_teachers_city(
    world: World,
) -> None:
    anna = world.teacher("1", "Anna", "almaty")
    me = world.person("42", "Ash")

    accepted = await _accept(world, me)

    assert accepted is not None
    assert accepted.moon == MoonFollow(_city("almaty"), MoonSource.TEACHER, world.tm(anna), False)


@pytest.mark.parametrize("own", ["mysuru", "moscow", FOLLOW_TEACHER])
async def test_a_first_link_reports_nothing_unless_the_slug_changes(world: World, own: str) -> None:
    """An explicit Mysuru or Moscow stays; follow-chosen on Mysuru moves to Almaty."""
    world.teacher("1", "Anna", "almaty")
    me = world.person("42", "Ash", own)

    accepted = await _accept(world, me)

    assert accepted is not None
    if own == FOLLOW_TEACHER:
        assert accepted.moon is not None
        assert accepted.moon.city.slug == "almaty"
    else:
        assert accepted.moon is None


async def test_a_teacher_without_a_city_changes_nothing_for_a_never_chose_student(
    world: World,
) -> None:
    world.teacher("1", "Anna", None)
    me = world.person("42", "Ash")

    accepted = await _accept(world, me)

    assert accepted is not None
    assert accepted.moon is None  # Mysuru before and after


async def test_a_second_link_reports_nothing(world: World) -> None:
    boris = world.teacher("2", "Boris", "moscow", OTHER_CODE)
    me = world.person("42", "Ash")
    world.link(me, boris)
    world.teacher("1", "Anna", "almaty")

    accepted = await _accept(world, me)

    assert accepted is not None
    assert accepted.created
    assert accepted.moon is None


async def test_a_duplicate_accept_reports_nothing(world: World) -> None:
    world.teacher("1", "Anna", "almaty")
    me = world.person("42", "Ash")
    await _accept(world, me)

    again = await _accept(world, me)

    assert again is not None
    assert not again.created
    assert again.moon is None


async def test_a_student_who_teaches_and_never_chose_gets_no_change(world: World) -> None:
    world.teacher("1", "Anna", "almaty")
    me = world.person("42", "Ash")
    world.link(world.person("7", "Student"), me)

    accepted = await _accept(world, me)

    assert accepted is not None
    assert accepted.moon is None


def _two(world: World, own: str | None = None, boris: str | None = "moscow") -> Account:
    """`me` with Anna (Almaty, oldest, main by default) and Boris."""
    me = world.person("42", "Ash", own)
    world.link(me, world.teacher("1", "Anna", "almaty"))
    world.link(me, world.teacher("2", "Boris", boris, OTHER_CODE))
    return me


def _named(world: World, name: str) -> Account:
    return next(a for a in world.accounts.accounts.values() if a.display_name == name)


async def test_make_main_reports_the_new_teachers_city(world: World) -> None:
    me = _two(world)
    boris = _named(world, "Boris")

    moon = await SetPrimaryTeacher(world.links, cities()).execute(world.me(me), boris.id)

    assert moon == MoonFollow(_city("moscow"), MoonSource.TEACHER, world.tm(boris), False)


async def test_make_main_onto_a_teacher_without_a_city_reports_the_default(world: World) -> None:
    me = _two(world, boris=None)
    boris = _named(world, "Boris")

    moon = await SetPrimaryTeacher(world.links, cities()).execute(world.me(me), boris.id)

    assert moon == MoonFollow(cities().default, MoonSource.DEFAULT, None, False)


@pytest.mark.parametrize(
    ("own", "boris"),
    [("moscow", "moscow"), (None, "almaty"), ("mysuru", "moscow")],
    ids=["chose-a-city", "same-slug", "chose-mysuru"],
)
async def test_make_main_reports_nothing_when_the_slug_stays(
    world: World, own: str | None, boris: str
) -> None:
    me = _two(world, own, boris)

    moon = await SetPrimaryTeacher(world.links, cities()).execute(
        world.me(me), _named(world, "Boris").id
    )

    assert moon is None


async def test_making_the_main_teacher_main_again_reports_nothing(world: World) -> None:
    me = _two(world)

    moon = await SetPrimaryTeacher(world.links, cities()).execute(
        world.me(me), _named(world, "Anna").id
    )

    assert moon is None


async def test_removing_the_main_teacher_reports_who_takes_over(world: World) -> None:
    me = _two(world)
    boris = _named(world, "Boris")

    moon = await RemoveTeacher(world.links, cities()).execute(
        world.me(me), _named(world, "Anna").id
    )

    assert moon == MoonFollow(_city("moscow"), MoonSource.TEACHER, world.tm(boris), False)


async def test_removing_the_only_teacher_falls_to_mysuru(world: World) -> None:
    me = world.person("42", "Ash")
    anna = world.teacher("1", "Anna", "almaty")
    world.link(me, anna)

    moon = await RemoveTeacher(world.links, cities()).execute(world.me(me), anna.id)

    assert moon == MoonFollow(cities().default, MoonSource.DEFAULT, None, False)


async def test_removing_a_teacher_who_isnt_main_reports_nothing(world: World) -> None:
    me = _two(world)

    moon = await RemoveTeacher(world.links, cities()).execute(
        world.me(me), _named(world, "Boris").id
    )

    assert moon is None


async def test_removing_reports_nothing_for_a_student_who_chose(world: World) -> None:
    me = _two(world, "moscow")

    moon = await RemoveTeacher(world.links, cities()).execute(
        world.me(me), _named(world, "Anna").id
    )

    assert moon is None


# The teacher's side of the first link: `moon-teacher-own` and [Keep 📍 …] (decision 3).


def _inheriting_teacher(
    world: World, own: str | None = None, theirs: str | None = "almaty"
) -> Account:
    """Lena teaches through CODE and follows her own teacher, Maya, by default."""
    lena = world.teacher("1", "Лена", own)
    world.link(lena, world.person("9", "Maya", theirs))
    return lena


async def test_the_first_student_of_an_inheriting_teacher_offers_keep(world: World) -> None:
    _inheriting_teacher(world)

    await _accept(world, world.person("42", "Ash"))

    assert world.notifier.keeps == [_city("almaty")]


async def test_a_second_student_offers_nothing(world: World) -> None:
    lena = _inheriting_teacher(world)
    world.link(world.person("7", "First"), lena)

    await _accept(world, world.person("42", "Ash"))

    assert world.notifier.keeps == [None]


@pytest.mark.parametrize(
    ("own", "theirs"),
    [
        ("moscow", "almaty"),  # chose a city: nothing flips
        ("mysuru", "almaty"),  # chose Mysuru: nothing flips
        (FOLLOW_TEACHER, "almaty"),  # chose to follow: keeps following
        (None, None),  # own teacher without a city: nothing to keep
        (None, FOLLOW_TEACHER),  # one hop: nothing to keep
    ],
)
async def test_no_keep_without_a_flip(world: World, own: str | None, theirs: str | None) -> None:
    _inheriting_teacher(world, own, theirs)

    await _accept(world, world.person("42", "Ash"))

    assert world.notifier.keeps == [None]


async def test_no_keep_for_a_teacher_with_no_teacher(world: World) -> None:
    world.teacher("1", "Лена", None)

    await _accept(world, world.person("42", "Ash"))

    assert world.notifier.keeps == [None]


# KeepMoonCity (bot only): stores the inherited city only while nothing was chosen.


async def test_keep_on_never_chose_stores_the_city_as_a_choice(world: World) -> None:
    lena = _inheriting_teacher(world)
    world.link(world.person("42", "Ash"), lena)

    result = await KeepMoonCity(cities(), world.accounts).execute(world.me(lena), "almaty")

    assert result.kept is True
    assert result.follow == MoonFollow(_city("almaty"), MoonSource.CHOSEN, None, False)
    assert world.stored(lena) == "almaty"


@pytest.mark.parametrize("chosen", ["moscow", FOLLOW_TEACHER, "mysuru"])
async def test_keep_after_any_choice_writes_nothing(world: World, chosen: str) -> None:
    lena = _inheriting_teacher(world, chosen)
    world.link(world.person("42", "Ash"), lena)
    writes = world.accounts.writes
    me = world.me(lena)

    result = await KeepMoonCity(cities(), world.accounts).execute(me, "almaty")

    assert result.kept is False
    assert result.follow == MoonFollow(
        *(
            (_city("almaty"), MoonSource.TEACHER, world.tm(_named(world, "Maya")), True)
            if chosen == FOLLOW_TEACHER
            else (_city(chosen), MoonSource.CHOSEN, None, False)
        )
    )
    assert world.stored(lena) == chosen
    assert world.accounts.writes == writes


async def test_keep_twice_writes_once(world: World) -> None:
    lena = _inheriting_teacher(world)
    world.link(world.person("42", "Ash"), lena)
    keep = KeepMoonCity(cities(), world.accounts)

    first = await keep.execute(world.me(lena), "almaty")
    second = await keep.execute(world.me(lena), "almaty")

    assert (first.kept, second.kept) == (True, False)
    assert second.follow.city.slug == "almaty"
    assert world.accounts.conditional_writes == 1


async def test_two_keep_taps_at_once_write_once(world: World) -> None:
    lena = _inheriting_teacher(world)
    world.link(world.person("42", "Ash"), lena)
    keep = KeepMoonCity(cities(), world.accounts)
    me = world.me(lena)

    results = await asyncio.gather(keep.execute(me, "almaty"), keep.execute(me, "almaty"))

    assert sorted(r.kept for r in results) == [False, True]
    assert world.accounts.conditional_writes == 1


@pytest.mark.parametrize("slug", ["atlantis", FOLLOW_TEACHER, ""])
async def test_keep_refuses_anything_but_a_listed_city(world: World, slug: str) -> None:
    lena = _inheriting_teacher(world)
    writes = world.accounts.writes

    with pytest.raises(UnknownLocation):
        await KeepMoonCity(cities(), world.accounts).execute(world.me(lena), slug)

    assert world.stored(lena) is None
    assert world.accounts.writes == writes


async def test_the_offer_names_the_teachers_own_teacher_and_the_new_city(world: World) -> None:
    _inheriting_teacher(world)

    await _accept(world, world.person("42", "Ash"))

    assert world.notifier.offers == [KeepOffer(_city("almaty"), cities().default, "Maya")]


async def test_no_keep_when_the_inherited_city_is_the_default_anyway(world: World) -> None:
    """Maya chose Mysuru: Lena's city doesn't move, so a Keep button would change nothing."""
    _inheriting_teacher(world, theirs="mysuru")

    await _accept(world, world.person("42", "Ash"))

    assert world.notifier.keeps == [None]


async def test_no_keep_for_a_removed_own_slug(world: World) -> None:
    """Keep writes only on NULL, so a slug since removed from the list gets no offer."""
    _inheriting_teacher(world, own="atlantis")

    await _accept(world, world.person("42", "Ash"))

    assert world.notifier.keeps == [None]
