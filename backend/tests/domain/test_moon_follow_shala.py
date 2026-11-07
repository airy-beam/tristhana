"""SC-01 + MD-02 (spec §3, Q99, Q108; ADR-0033): the shala step in the one moon rule.

1. own listed city → CHOSEN; 2. "-shala" → the shala's city, else DEFAULT; 3. "-teacher" → as
MD-02; 4. never chose: staff → SHALA; student where the main teacher is staff → SHALA (Q108);
no students and the teacher has an explicit city → TEACHER; student → SHALA; else DEFAULT.
Still one hop: a teacher's SHALA never passes to students who aren't members.

`moon_follow(own, teaches, teacher, shala, cities)`. `MoonFollow.shala` is the shala for
source SHALA, else None. `follow_chosen` stays "Follow my teacher" only; `explicit` also holds
for "-shala"."""

import itertools
import re
from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

import pytest

from tests.fakes import cities
from tristhana.domain.accounts import Account, moon_follow_of
from tristhana.domain.moon import (
    FOLLOW_SHALA,
    FOLLOW_TEACHER,
    MoonFollow,
    MoonSource,
    ShalaMoon,
    TeacherMoon,
    moon_follow,
)

ANNA = TeacherMoon(UUID(int=1), "Anna", "almaty")
NO_CITY = TeacherMoon(UUID(int=2), "Boris", None)
FOLLOWS = TeacherMoon(UUID(int=3), "Clara", FOLLOW_TEACHER)
REMOVED = TeacherMoon(UUID(int=4), "Dana", "atlantis")
ON_SHALA = TeacherMoon(UUID(int=5), "Eva", FOLLOW_SHALA)  # a teacher following their shala

# The shala's moon city is `coalesce(moon_city, city)`: always a slug, maybe since removed.
STAFF_AT = ShalaMoon(UUID(int=20), "Ashtanga Kyiv", "kyiv", True, False)
STUDENT_OF = ShalaMoon(UUID(int=21), "Moscow Shala", "moscow", False, False)
WITH_TEACHER = ShalaMoon(UUID(int=22), "Moscow Shala", "moscow", False, True)
GONE = ShalaMoon(UUID(int=23), "Atlantis Shala", "atlantis", False, False)
GONE_STAFF = ShalaMoon(UUID(int=24), "Atlantis Shala", "atlantis", True, False)

CHOSEN, TEACHER, DEFAULT, SHALA = (
    MoonSource.CHOSEN,
    MoonSource.TEACHER,
    MoonSource.DEFAULT,
    MoonSource.SHALA,
)


def _view(got: MoonFollow) -> tuple[str, MoonSource, TeacherMoon | None, ShalaMoon | None]:
    return got.city.slug, got.source, got.teacher, got.shala


@pytest.mark.parametrize("staff", [False, True])
def test_a_removed_moon_city_falls_back_to_the_shalas_own_city(staff: bool) -> None:
    """Q111 (owner, 2026-11-07): nearer to what the shala observes than Mysuru."""
    shala = ShalaMoon(UUID(int=25), "Almaty Shala", "atlantis", staff, False, "almaty")

    got = moon_follow(None, False, None, shala, cities())

    assert _view(got) == ("almaty", SHALA, None, shala)


def test_the_sentinel_and_the_source() -> None:
    assert FOLLOW_SHALA == "-shala"
    assert MoonSource.SHALA.value == "shala"
    assert cities().find(FOLLOW_SHALA) is None
    assert re.fullmatch(r"[a-z-]{1,24}", FOLLOW_SHALA)  # the `moon_location` CHECK
    assert FOLLOW_SHALA != FOLLOW_TEACHER


@pytest.mark.parametrize(
    ("own", "teaches", "teacher", "shala", "slug", "source", "shown", "shala_shown"),
    [
        # 1. A listed own choice wins over any shala.
        ("minsk", False, ANNA, STAFF_AT, "minsk", CHOSEN, None, None),
        ("minsk", True, ANNA, WITH_TEACHER, "minsk", CHOSEN, None, None),
        ("mysuru", False, None, STUDENT_OF, "mysuru", CHOSEN, None, None),
        # 2. "Follow my shala", with and without a shala.
        (FOLLOW_SHALA, False, ANNA, STUDENT_OF, "moscow", SHALA, None, STUDENT_OF),
        (FOLLOW_SHALA, True, None, STAFF_AT, "kyiv", SHALA, None, STAFF_AT),
        (FOLLOW_SHALA, False, ANNA, None, "mysuru", DEFAULT, None, None),  # never the teacher
        (FOLLOW_SHALA, False, None, None, "mysuru", DEFAULT, None, None),
        (FOLLOW_SHALA, False, ANNA, GONE, "mysuru", DEFAULT, None, None),  # a removed slug
        # 3. "Follow my teacher" beats the shala, even Q108's.
        (FOLLOW_TEACHER, False, ANNA, WITH_TEACHER, "almaty", TEACHER, ANNA, None),
        (FOLLOW_TEACHER, True, ANNA, STAFF_AT, "almaty", TEACHER, ANNA, None),
        (FOLLOW_TEACHER, False, NO_CITY, STUDENT_OF, "mysuru", DEFAULT, NO_CITY, None),
        # 4. Never chose. Staff follow their shala first (Q99), students or not.
        (None, False, ANNA, STAFF_AT, "kyiv", SHALA, None, STAFF_AT),
        (None, True, ANNA, STAFF_AT, "kyiv", SHALA, None, STAFF_AT),
        (None, True, None, STAFF_AT, "kyiv", SHALA, None, STAFF_AT),
        # Q108: the main teacher (with a chosen city) staffs the student's shala.
        (None, False, ANNA, WITH_TEACHER, "moscow", SHALA, None, WITH_TEACHER),
        # ... the same teacher not on that shala's staff (or on another shala's): TEACHER.
        (None, False, ANNA, STUDENT_OF, "almaty", TEACHER, ANNA, None),
        # ... a teacher with no city on staff: SHALA.
        (None, False, NO_CITY, WITH_TEACHER, "moscow", SHALA, None, WITH_TEACHER),
        # ... a student with students (Q76) in that shala: SHALA.
        (None, True, ANNA, WITH_TEACHER, "moscow", SHALA, None, WITH_TEACHER),
        # A student whose teacher gives no city, or who teaches, follows the shala.
        (None, False, NO_CITY, STUDENT_OF, "moscow", SHALA, None, STUDENT_OF),
        (None, False, FOLLOWS, STUDENT_OF, "moscow", SHALA, None, STUDENT_OF),
        (None, False, REMOVED, STUDENT_OF, "moscow", SHALA, None, STUDENT_OF),
        (None, True, ANNA, STUDENT_OF, "moscow", SHALA, None, STUDENT_OF),
        (None, False, None, STUDENT_OF, "moscow", SHALA, None, STUDENT_OF),
        # A removed own slug counts as never chose.
        ("atlantis", False, ANNA, WITH_TEACHER, "moscow", SHALA, None, WITH_TEACHER),
        ("atlantis", True, None, STAFF_AT, "kyiv", SHALA, None, STAFF_AT),
        # A shala whose moon slug was removed gives nothing: the rule goes on without it.
        (None, False, ANNA, GONE, "almaty", TEACHER, ANNA, None),
        (None, False, None, GONE_STAFF, "mysuru", DEFAULT, None, None),
        (None, True, ANNA, GONE_STAFF, "mysuru", DEFAULT, None, None),
    ],
)
def test_the_rule_with_a_shala(
    own: str | None,
    teaches: bool,
    teacher: TeacherMoon | None,
    shala: ShalaMoon | None,
    slug: str,
    source: MoonSource,
    shown: TeacherMoon | None,
    shala_shown: ShalaMoon | None,
) -> None:
    got = moon_follow(own, teaches, teacher, shala, cities())

    assert _view(got) == (slug, source, shown, shala_shown)


@pytest.mark.parametrize("own", [FOLLOW_SHALA])
@pytest.mark.parametrize("shala", [None, STUDENT_OF, STAFF_AT, GONE])
def test_follow_shala_is_explicit_and_not_a_teacher_follow(
    own: str, shala: ShalaMoon | None
) -> None:
    got = moon_follow(own, False, ANNA, shala, cities())

    assert got.explicit is True
    assert got.follow_chosen is False


@pytest.mark.parametrize("shala", [STUDENT_OF, STAFF_AT, WITH_TEACHER])
def test_never_chose_with_a_shala_is_not_explicit(shala: ShalaMoon) -> None:
    assert moon_follow(None, False, ANNA, shala, cities()).explicit is False


# One hop (Q98): the teacher's shala city never reaches a student who isn't a member.


@pytest.mark.parametrize("teacher", [NO_CITY, ON_SHALA])
def test_a_teacher_on_their_shala_gives_their_student_nothing(teacher: TeacherMoon) -> None:
    """The teacher resolves to SHALA (never chose, or "-shala"), but the student only sees
    the teacher's stored value: NULL or the sentinel, neither a city."""
    got = moon_follow(None, False, teacher, None, cities())

    assert _view(got) == ("mysuru", DEFAULT, None, None)


def test_following_a_teacher_who_follows_their_shala_is_the_none_line() -> None:
    got = moon_follow(FOLLOW_TEACHER, False, ON_SHALA, None, cities())

    assert (got.city.slug, got.source, got.teacher, got.follow_chosen) == (
        "mysuru",
        DEFAULT,
        ON_SHALA,
        True,
    )


# Every MD-02 row by no shala / staff / student: the shala only changes never-chose rows.

_MD02_ROWS: list[tuple[str | None, bool, TeacherMoon | None]] = [
    ("moscow", False, ANNA),
    ("moscow", True, ANNA),
    ("mysuru", False, ANNA),
    ("moscow", False, None),
    ("atlantis", False, ANNA),
    ("atlantis", True, ANNA),
    (None, False, ANNA),
    (None, True, ANNA),
    (FOLLOW_TEACHER, False, ANNA),
    (FOLLOW_TEACHER, True, ANNA),
    (None, False, NO_CITY),
    (None, False, FOLLOWS),
    (None, False, REMOVED),
    (FOLLOW_TEACHER, False, NO_CITY),
    (FOLLOW_TEACHER, False, FOLLOWS),
    (FOLLOW_TEACHER, True, REMOVED),
    (None, False, None),
    (None, True, None),
    (FOLLOW_TEACHER, False, None),
]


def _never_chose(own: str | None) -> bool:
    return own is None or (own != FOLLOW_TEACHER and cities().find(own) is None)


@pytest.mark.parametrize(("own", "teaches", "teacher"), _MD02_ROWS)
def test_without_a_shala_md02_is_unchanged(
    own: str | None, teaches: bool, teacher: TeacherMoon | None
) -> None:
    got = moon_follow(own, teaches, teacher, None, cities())

    assert got.source is not SHALA
    assert got.shala is None


@pytest.mark.parametrize(("own", "teaches", "teacher"), _MD02_ROWS)
def test_as_staff_every_never_chose_row_becomes_the_shala(
    own: str | None, teaches: bool, teacher: TeacherMoon | None
) -> None:
    before = moon_follow(own, teaches, teacher, None, cities())
    got = moon_follow(own, teaches, teacher, STAFF_AT, cities())

    if _never_chose(own):
        assert _view(got) == ("kyiv", SHALA, None, STAFF_AT)
    else:
        assert _view(got) == _view(before)


@pytest.mark.parametrize(("own", "teaches", "teacher"), _MD02_ROWS)
def test_as_a_student_the_teachers_city_still_comes_first(
    own: str | None, teaches: bool, teacher: TeacherMoon | None
) -> None:
    before = moon_follow(own, teaches, teacher, None, cities())
    got = moon_follow(own, teaches, teacher, STUDENT_OF, cities())

    if _never_chose(own) and before.source is not TEACHER:
        assert _view(got) == ("moscow", SHALA, None, STUDENT_OF)
    else:
        assert _view(got) == _view(before)


@pytest.mark.parametrize(("own", "teaches", "teacher"), _MD02_ROWS)
def test_as_a_student_with_the_teacher_on_staff_the_shala_beats_the_teacher(
    own: str | None, teaches: bool, teacher: TeacherMoon | None
) -> None:
    before = moon_follow(own, teaches, teacher, None, cities())
    got = moon_follow(own, teaches, teacher, WITH_TEACHER, cities())

    if _never_chose(own):
        assert _view(got) == ("moscow", SHALA, None, WITH_TEACHER)
    else:
        assert _view(got) == _view(before)


_OWN = (None, "almaty", "mysuru", "atlantis", FOLLOW_TEACHER, FOLLOW_SHALA)
_TEACHERS = (None, ANNA, NO_CITY, FOLLOWS, REMOVED, ON_SHALA)
_SHALAS = (None, STAFF_AT, STUDENT_OF, WITH_TEACHER, GONE, GONE_STAFF)


@pytest.mark.parametrize(
    ("own", "teaches", "teacher", "shala"),
    list(itertools.product(_OWN, (False, True), _TEACHERS, _SHALAS)),
)
def test_every_combination_is_a_listed_city_from_a_named_source(
    own: str | None, teaches: bool, teacher: TeacherMoon | None, shala: ShalaMoon | None
) -> None:
    got = moon_follow(own, teaches, teacher, shala, cities())

    assert cities().find(got.city.slug) is got.city
    match got.source:
        case MoonSource.CHOSEN:
            assert got.city.slug == own
            assert (got.teacher, got.shala) == (None, None)
        case MoonSource.SHALA:
            assert shala is not None
            assert got.city.slug in (shala.moon_city, shala.city)
            assert own != FOLLOW_TEACHER
            assert cities().find(own) is None
            assert (got.teacher, got.shala) == (None, shala)
        case MoonSource.TEACHER:
            assert teacher is not None
            assert got.city.slug == teacher.moon_location
            assert got.shala is None
            assert own != FOLLOW_SHALA
        case MoonSource.DEFAULT:
            assert got.city is cities().default
            assert got.shala is None


# The account carries the main shala (`Account.shala`), and every reader picks it up.


def _account(**kw: object) -> Account:
    base = Account(
        id=UUID(int=99),
        display_name="Ash",
        locale="en",
        timezone="Asia/Almaty",
        last_seen_at=datetime(2026, 11, 7, tzinfo=UTC),
    )
    return replace(base, **kw)  # type: ignore[arg-type]


def test_an_account_starts_with_no_shala() -> None:
    assert _account().shala is None


@pytest.mark.parametrize(
    ("own", "teaches", "teacher", "shala"),
    [
        (None, False, ANNA, WITH_TEACHER),
        (None, True, None, STAFF_AT),
        (FOLLOW_SHALA, False, None, STUDENT_OF),
        ("moscow", False, ANNA, STAFF_AT),
        (None, False, ANNA, None),
    ],
)
def test_moon_follow_of_passes_the_shala(
    own: str | None, teaches: bool, teacher: TeacherMoon | None, shala: ShalaMoon | None
) -> None:
    account = _account(moon_location=own, teaches=teaches, main_teacher=teacher, shala=shala)

    assert moon_follow_of(account, cities()) == moon_follow(own, teaches, teacher, shala, cities())


def test_home_city_is_still_never_the_own_city_with_a_shala() -> None:
    account = _account(home_city="almaty", shala=STUDENT_OF)

    assert moon_follow_of(account, cities()).city.slug == "moscow"
