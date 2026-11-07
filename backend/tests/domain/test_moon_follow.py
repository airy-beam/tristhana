"""MD-02 (spec §2, §3, §7; ADR-0032): the one rule for the effective moon city.

Own listed choice wins; "Follow my teacher", or never chosen without students, takes the main
teacher's own *explicit* listed city; everything else is the Mysuru default. One hop: a
teacher's NULL, "Follow my teacher" or removed slug gives the student nothing."""

import itertools
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest

from tests.fakes import cities
from tristhana.domain.accounts import Account, moon_follow_of
from tristhana.domain.moon import (
    FOLLOW_TEACHER,
    City,
    MoonFollow,
    MoonSource,
    TeacherMoon,
    moon_follow,
)
from tristhana.infrastructure.seed.cities_yaml import CatalogLoadError, load_cities

ANNA = TeacherMoon(UUID(int=1), "Anna", "almaty")
NO_CITY = TeacherMoon(UUID(int=2), "Boris", None)
FOLLOWS = TeacherMoon(UUID(int=3), "Clara", FOLLOW_TEACHER)
REMOVED = TeacherMoon(UUID(int=4), "Dana", "atlantis")  # a slug since removed from the list


def _city(slug: str) -> City:
    city = cities().find(slug)
    assert city is not None
    return city


CHOSEN, TEACHER, DEFAULT = MoonSource.CHOSEN, MoonSource.TEACHER, MoonSource.DEFAULT


@pytest.mark.parametrize(
    ("own", "teaches", "teacher", "slug", "source", "shown", "follow_chosen"),
    [
        # A listed own choice wins, whatever the teacher has, students or not.
        ("moscow", False, ANNA, "moscow", CHOSEN, None, False),
        ("moscow", True, ANNA, "moscow", CHOSEN, None, False),
        ("mysuru", False, ANNA, "mysuru", CHOSEN, None, False),  # an explicit Mysuru
        ("moscow", False, None, "moscow", CHOSEN, None, False),
        # A removed own slug counts as never chosen.
        ("atlantis", False, ANNA, "almaty", TEACHER, ANNA, False),
        ("atlantis", True, ANNA, "mysuru", DEFAULT, None, False),
        # Never chose: without students, the teacher's city; with students, own (Q76).
        (None, False, ANNA, "almaty", TEACHER, ANNA, False),
        (None, True, ANNA, "mysuru", DEFAULT, None, False),
        # "Follow my teacher", with or without students.
        (FOLLOW_TEACHER, False, ANNA, "almaty", TEACHER, ANNA, True),
        (FOLLOW_TEACHER, True, ANNA, "almaty", TEACHER, ANNA, True),
        # One hop: the teacher's own NULL, "Follow my teacher" or a removed slug is no city.
        (None, False, NO_CITY, "mysuru", DEFAULT, None, False),
        (None, False, FOLLOWS, "mysuru", DEFAULT, None, False),
        (None, False, REMOVED, "mysuru", DEFAULT, None, False),
        # ... and a follow-chosen student keeps the teacher for `moon-source-teacher-none`.
        (FOLLOW_TEACHER, False, NO_CITY, "mysuru", DEFAULT, NO_CITY, True),
        (FOLLOW_TEACHER, False, FOLLOWS, "mysuru", DEFAULT, FOLLOWS, True),
        (FOLLOW_TEACHER, True, REMOVED, "mysuru", DEFAULT, REMOVED, True),
        # No main teacher.
        (None, False, None, "mysuru", DEFAULT, None, False),
        (None, True, None, "mysuru", DEFAULT, None, False),
        (FOLLOW_TEACHER, False, None, "mysuru", DEFAULT, None, True),
    ],
)
def test_the_rule(
    own: str | None,
    teaches: bool,
    teacher: TeacherMoon | None,
    slug: str,
    source: MoonSource,
    shown: TeacherMoon | None,
    follow_chosen: bool,
) -> None:
    got = moon_follow(own, teaches, teacher, None, cities())

    assert got == MoonFollow(_city(slug), source, shown, follow_chosen)


def test_the_default_is_the_listed_default_city() -> None:
    got = moon_follow(None, False, None, None, cities())

    assert got.city is cities().default


def test_a_cycle_of_two_teachers_who_never_chose_is_each_own_city() -> None:
    """A teaches B and B teaches A: both teach, so neither inherits (no loop to walk)."""
    a = TeacherMoon(UUID(int=10), "A", None)
    b = TeacherMoon(UUID(int=11), "B", None)

    of_a = moon_follow(None, True, b, None, cities())
    of_b = moon_follow(None, True, a, None, cities())

    assert (of_a.source, of_a.city.slug) == (DEFAULT, "mysuru")
    assert (of_b.source, of_b.city.slug) == (DEFAULT, "mysuru")


def test_a_cycle_where_one_chose_gives_the_other_its_own_city() -> None:
    """A chose Almaty and teaches B; B never chose and teaches A: B uses its own (Mysuru)."""
    a = TeacherMoon(UUID(int=10), "A", "almaty")

    assert moon_follow(None, True, a, None, cities()).source is DEFAULT
    assert moon_follow(FOLLOW_TEACHER, True, a, None, cities()).city.slug == "almaty"


_OWN = (None, "almaty", "mysuru", "atlantis", FOLLOW_TEACHER)
_TEACHERS = (None, ANNA, NO_CITY, FOLLOWS, REMOVED, TeacherMoon(UUID(int=5), None, "moscow"))


@pytest.mark.parametrize(
    ("own", "teaches", "teacher"), list(itertools.product(_OWN, (False, True), _TEACHERS))
)
def test_every_combination_resolves_to_a_listed_city_and_never_further_than_one_hop(
    own: str | None, teaches: bool, teacher: TeacherMoon | None
) -> None:
    got = moon_follow(own, teaches, teacher, None, cities())

    assert cities().find(got.city.slug) is got.city
    assert got.follow_chosen is (own == FOLLOW_TEACHER)
    match got.source:
        case MoonSource.CHOSEN:
            assert got.city.slug == own
            assert got.teacher is None
        case MoonSource.TEACHER:
            assert teacher is not None
            assert got.city.slug == teacher.moon_location
            assert got.teacher == teacher
        case MoonSource.DEFAULT:
            assert got.city is cities().default
            assert got.teacher == (teacher if got.follow_chosen else None)
        case MoonSource.SHALA:  # SC-01: never without a shala
            raise AssertionError(got)


def test_follow_teacher_is_never_a_city() -> None:
    assert FOLLOW_TEACHER == "-teacher"
    assert cities().find(FOLLOW_TEACHER) is None
    assert all(c.slug != FOLLOW_TEACHER for c in cities().all)


def test_the_loader_rejects_the_sentinel_as_a_slug(tmp_path: Path) -> None:
    bad = tmp_path / "cities.yaml"
    bad.write_text(
        "default: mysuru\ncities:\n"
        "  - {slug: mysuru, names: {en: Mysuru, ru: Майсур}, lat: 12.2958, lon: 76.6394,"
        " tz: Asia/Kolkata}\n"
        f"  - {{slug: '{FOLLOW_TEACHER}', names: {{en: T, ru: T}}, lat: 1.0, lon: 1.0,"
        " tz: Asia/Almaty}\n"
    )

    with pytest.raises(CatalogLoadError):
        load_cities(bad)


def test_the_sentinel_fits_the_column_check() -> None:
    """`moon_location ~ '^[a-z-]{1,24}$'` (spec §5): no migration needed."""
    import re

    assert re.fullmatch(r"[a-z-]{1,24}", FOLLOW_TEACHER)


def _account(**kw: object) -> Account:
    base = Account(
        id=UUID(int=99),
        display_name="Ash",
        locale="en",
        timezone="Asia/Almaty",
        last_seen_at=datetime(2026, 11, 7, tzinfo=UTC),
    )
    return replace(base, **kw)  # type: ignore[arg-type]


def test_an_account_starts_with_no_students_and_no_main_teacher() -> None:
    account = _account()

    assert account.teaches is False
    assert account.main_teacher is None


@pytest.mark.parametrize(
    ("own", "teaches", "teacher"),
    [
        (None, False, ANNA),
        (None, True, ANNA),
        ("moscow", False, ANNA),
        (FOLLOW_TEACHER, True, None),
    ],
)
def test_moon_follow_of_reads_the_accounts_inputs(
    own: str | None, teaches: bool, teacher: TeacherMoon | None
) -> None:
    account = _account(moon_location=own, teaches=teaches, main_teacher=teacher)

    assert moon_follow_of(account, cities()) == moon_follow(own, teaches, teacher, None, cities())


def test_home_city_is_never_the_own_city() -> None:
    """Decision 1: "own city" is the explicit choice, else Mysuru, never `home_city`."""
    account = _account(home_city="almaty", teaches=True, main_teacher=ANNA)

    got = moon_follow_of(account, cities())

    assert (got.city.slug, got.source) == ("mysuru", DEFAULT)
