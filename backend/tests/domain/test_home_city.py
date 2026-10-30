"""MD-04 + ID-06 (ADR-0029): the home city drives the zone, labels and the local moon FYI."""

from dataclasses import replace
from datetime import UTC, date, datetime
from uuid import uuid4

import pytest

from tristhana.domain.accounts import (
    NOT_LISTED,
    NOT_NOW,
    Account,
    ExternalProfile,
    IdentityKey,
    IdentityProvider,
    InvalidTimezone,
    ProfileChange,
    ProfilePatch,
    UnknownCity,
    home_city_of,
    resolve_profile,
)
from tristhana.domain.moon import (
    Cities,
    City,
    MoonDay,
    MoonDayKind,
    MoonLocation,
    home_dates,
    label_city,
)

NOW = datetime(2026, 10, 30, 5, tzinfo=UTC)
ME = Account(uuid4(), "Ash", "en", "Asia/Almaty", NOW)
TG = ExternalProfile(IdentityKey(IdentityProvider.TELEGRAM, "42"), "Ash", "en")


def _city(slug: str, name: str, tz: str) -> City:
    return City(slug, name, name, MoonLocation(45.0, 60.0, tz))


CITIES = Cities(
    (
        _city("mysuru", "Mysuru", "Asia/Kolkata"),
        _city("almaty", "Almaty", "Asia/Almaty"),
        _city("astana", "Astana", "Asia/Almaty"),
        _city("moscow", "Moscow", "Europe/Moscow"),
        _city("sochi", "Sochi", "Europe/Moscow"),
    ),
    "mysuru",
)


def _resolve(account: Account, patch: ProfilePatch) -> ProfileChange:
    return resolve_profile(account, patch, TG, CITIES)


# The invariant: a city slug implies timezone == city.tz.


def test_picking_a_city_writes_the_city_and_its_zone() -> None:
    change = _resolve(replace(ME, timezone=None), ProfilePatch(home_city="astana"))

    assert (change.home_city, change.timezone) == ("astana", "Asia/Almaty")
    assert change.fields == {"home_city", "timezone"}


def test_a_city_with_the_same_zone_in_the_patch_is_fine() -> None:
    change = _resolve(ME, ProfilePatch(home_city="sochi", timezone="Europe/Moscow"))

    assert (change.home_city, change.timezone) == ("sochi", "Europe/Moscow")


def test_a_city_with_another_zone_in_the_patch_is_rejected() -> None:
    with pytest.raises(InvalidTimezone):
        _resolve(ME, ProfilePatch(home_city="sochi", timezone="Asia/Almaty"))


@pytest.mark.parametrize("slug", ["atlantis", "-", ""])
def test_an_unknown_city_is_rejected(slug: str) -> None:
    with pytest.raises(UnknownCity):
        _resolve(ME, ProfilePatch(home_city=slug))


def test_not_listed_or_not_now_stores_the_marker_and_keeps_the_zone() -> None:
    change = _resolve(replace(ME, home_city="almaty"), ProfilePatch(home_city=None))

    assert (change.home_city, change.timezone) == (NOT_LISTED, "Asia/Almaty")
    assert change.fields == {"home_city"}


def test_not_listed_with_a_zone_writes_both() -> None:
    change = _resolve(ME, ProfilePatch(home_city=None, timezone="Asia/Bangkok"))

    assert (change.home_city, change.timezone) == (NOT_LISTED, "Asia/Bangkok")
    assert change.fields == {"home_city", "timezone"}


@pytest.mark.parametrize("zone", ["Asia/Bangkok", "UTC"])
def test_a_zone_that_is_not_the_citys_clears_the_city(zone: str) -> None:
    change = _resolve(replace(ME, home_city="astana"), ProfilePatch(timezone=zone))

    assert (change.home_city, change.timezone) == (NOT_LISTED, zone)
    assert change.fields == {"home_city", "timezone"}


def test_the_same_zone_keeps_the_city() -> None:
    change = _resolve(replace(ME, home_city="astana"), ProfilePatch(timezone="Asia/Almaty"))

    assert change.home_city == "astana"
    # Written with the zone, so a stale read can't leave a city in another zone.
    assert change.fields == {"home_city", "timezone"}


def test_a_zone_change_never_answers_the_nudge() -> None:
    change = _resolve(ME, ProfilePatch(timezone="Asia/Bangkok"))

    assert change.home_city is None  # still never chosen: the nudge stays


# "Not now" answers the nudge only while it is unanswered (a stale button keeps a city).


def test_not_now_answers_an_unanswered_nudge() -> None:
    change = _resolve(ME, ProfilePatch(home_city=NOT_NOW))

    assert (change.home_city, change.timezone) == (NOT_LISTED, "Asia/Almaty")
    assert change.fields == {"home_city"}


@pytest.mark.parametrize("home", ["astana", NOT_LISTED])
def test_a_stale_not_now_keeps_the_answer_given_since(home: str) -> None:
    change = _resolve(replace(ME, home_city=home), ProfilePatch(home_city=NOT_NOW))

    assert change.home_city == home
    assert "home_city" not in change.fields


def test_a_removed_city_is_normalised_on_the_next_zone_write() -> None:
    change = _resolve(replace(ME, home_city="atlantis"), ProfilePatch(timezone="Asia/Almaty"))

    assert change.home_city == NOT_LISTED


def test_other_settings_leave_the_city_alone() -> None:
    change = _resolve(replace(ME, home_city="astana"), ProfilePatch(locale="ru"))

    assert change.home_city == "astana"
    assert "home_city" not in change.fields


# Reading the city back.


def test_find_never_falls_back_to_the_default() -> None:
    assert CITIES.find(None) is None
    assert CITIES.find(NOT_LISTED) is None
    assert CITIES.find("atlantis") is None
    city = CITIES.find("astana")
    assert city is not None
    assert city.name_en == "Astana"


def test_home_city_of_needs_a_listed_city_in_the_accounts_zone() -> None:
    astana = replace(ME, home_city="astana")

    assert home_city_of(astana, CITIES) == CITIES.find("astana")
    assert home_city_of(replace(astana, timezone="Asia/Bangkok"), CITIES) is None
    assert home_city_of(replace(ME, home_city=NOT_LISTED), CITIES) is None
    assert home_city_of(replace(ME, home_city="atlantis"), CITIES) is None
    assert home_city_of(ME, CITIES) is None


# DST zones: the rules compare zone names, so a summer or winter offset changes nothing.

DST = Cities(
    (_city("london", "London", "Europe/London"), _city("berlin", "Berlin", "Europe/Berlin")),
    "london",
)


@pytest.mark.parametrize(
    ("slug", "zone"), [("london", "Europe/London"), ("berlin", "Europe/Berlin")]
)
def test_dst_cities_keep_their_city_and_label(slug: str, zone: str) -> None:
    city = DST.find(slug)
    picked = resolve_profile(replace(ME, timezone=None), ProfilePatch(home_city=slug), TG, DST)
    same = resolve_profile(replace(ME, home_city=slug), ProfilePatch(timezone=zone), TG, DST)
    moved = resolve_profile(replace(ME, home_city=slug), ProfilePatch(timezone="UTC"), TG, DST)

    assert (picked.home_city, picked.timezone) == (slug, zone)
    assert same.home_city == slug
    assert moved.home_city == NOT_LISTED  # UTC is not London, even in winter
    assert label_city(city, zone) is city
    # A pair across the end of summer time (25 Oct 2026) is matched as on any other day.
    followed = [MoonDay(date(2026, 10, 25), MoonDayKind.PURNIMA)]
    assert home_dates(followed, [MoonDay(date(2026, 10, 26), MoonDayKind.PURNIMA)]) == {
        date(2026, 10, 25): date(2026, 10, 26)
    }


def test_label_city_only_names_its_own_zone() -> None:
    astana = CITIES.find("astana")

    assert label_city(astana, "Asia/Almaty") is astana
    assert label_city(astana, "Asia/Bangkok") is None
    assert label_city(astana, None) is None
    assert label_city(None, "Asia/Almaty") is None


# MD-04: pair the followed calendar with the home city's by phase, ±1 day.

P, A = MoonDayKind.PURNIMA, MoonDayKind.AMAVASYA
KP, KA = MoonDayKind.KSHAYA_PURNIMA, MoonDayKind.KSHAYA_AMAVASYA


def _days(*items: tuple[int, int, MoonDayKind]) -> list[MoonDay]:
    return [MoonDay(date(2026, m, d), k) for m, d, k in items]


def test_only_differing_pairs_are_kept() -> None:
    followed = _days((10, 25, P), (11, 9, A))
    home = _days((10, 26, P), (11, 9, A))

    assert home_dates(followed, home) == {date(2026, 10, 25): date(2026, 10, 26)}


def test_pairs_one_day_either_way() -> None:
    followed = _days((10, 25, P), (11, 9, A))
    home = _days((10, 24, P), (11, 10, A))

    assert home_dates(followed, home) == {
        date(2026, 10, 25): date(2026, 10, 24),
        date(2026, 11, 9): date(2026, 11, 10),
    }


def test_two_days_apart_is_not_a_pair() -> None:
    assert home_dates(_days((10, 25, P)), _days((10, 27, P))) == {}


def test_kshaya_is_the_same_phase() -> None:
    followed = _days((2, 27, KA), (12, 4, P))
    home = _days((2, 28, A), (12, 5, KP))

    assert home_dates(followed, home) == {
        date(2026, 2, 27): date(2026, 2, 28),
        date(2026, 12, 4): date(2026, 12, 5),
    }


def test_another_phase_never_pairs() -> None:
    assert home_dates(_days((10, 25, P)), _days((10, 26, A))) == {}


def test_an_ambiguous_match_is_left_out() -> None:
    followed = [MoonDay(date(2026, 10, 25), P)]
    home = [MoonDay(date(2026, 10, 24), P), MoonDay(date(2026, 10, 26), P)]

    assert home_dates(followed, home) == {}


def test_pairs_across_the_year_edge() -> None:
    followed = [MoonDay(date(2026, 12, 31), A)]
    home = [MoonDay(date(2027, 1, 1), A)]

    assert home_dates(followed, home) == {date(2026, 12, 31): date(2027, 1, 1)}


def test_the_same_calendar_has_no_differences() -> None:
    days = _days((10, 25, P), (11, 9, A))

    assert home_dates(days, days) == {}


def test_a_half_hour_zone_city_is_just_another_city() -> None:
    goa = City("goa", "Goa", "Гоа", MoonLocation(15.4909, 73.8278, "Asia/Kolkata"))

    assert label_city(goa, "Asia/Kolkata") is goa  # same zone as Mysuru, own name
