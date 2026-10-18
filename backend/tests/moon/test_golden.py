"""Golden tests: the port must reproduce the owner-verified generator.py exactly."""

import json
from datetime import date
from functools import cache
from pathlib import Path
from typing import Any

import pytest

from tristhana.domain.moon import MoonDay, MoonDayKind, MoonLocation, MoonPhase
from tristhana.moon import compute_moon_days

FIXTURES = Path(__file__).parent.parent / "fixtures" / "moon"
CITIES = sorted(p.stem for p in (FIXTURES / "generator").glob("*.json"))
SAMPLED_YEARS = [*range(2025, 2031), *range(2040, 2101, 10)]
ALL_YEARS = list(range(2025, 2101))


@cache
def _fixture(city: str) -> dict[str, Any]:
    return json.loads((FIXTURES / "generator" / f"{city}.json").read_text(encoding="utf-8"))


def _location(city: str) -> MoonLocation:
    loc = _fixture(city)["meta"]["location"]
    return MoonLocation(lat=loc["lat"], lon=loc["lon"], tz=loc["tz"])


def _expected(city: str, year: int) -> list[MoonDay]:
    return [
        MoonDay(date.fromisoformat(d), MoonDayKind(k))
        for d, k in _fixture(city)["events"]
        if d.startswith(f"{year}-")
    ]


def _year(city: str, year: int) -> list[MoonDay]:
    return compute_moon_days(_location(city), date(year, 1, 1), date(year, 12, 31))


def test_fixtures_cover_the_ten_verified_cities() -> None:
    assert len(CITIES) == 10


@pytest.mark.parametrize("year", SAMPLED_YEARS)
@pytest.mark.parametrize("city", CITIES)
def test_matches_generator_sampled(city: str, year: int) -> None:
    assert _year(city, year) == _expected(city, year)


@pytest.mark.slow
@pytest.mark.parametrize("year", ALL_YEARS)
@pytest.mark.parametrize("city", CITIES)
def test_matches_generator_full(city: str, year: int) -> None:
    assert _year(city, year) == _expected(city, year)


@pytest.mark.parametrize("city", ["mysuru", "yekaterinburg"])
def test_per_year_runs_equal_one_continuous_run(city: str) -> None:
    continuous = compute_moon_days(_location(city), date(2025, 1, 1), date(2035, 12, 31))

    per_year = [day for year in range(2025, 2036) for day in _year(city, year)]

    assert per_year == continuous


def test_syc_2025_matches_except_reviewed_differences() -> None:
    syc = json.loads((FIXTURES / "syc_2025.json").read_text(encoding="utf-8"))
    known = {tuple(d["syc"]): tuple(d["generator"]) for d in syc["known_differences"]}
    computed = {(d.date.isoformat(), d.kind) for d in _year("mysuru", 2025)}

    expected: set[tuple[str, MoonDayKind]] = set()
    for iso, phase in syc["dates"]:
        gen_iso, gen_kind = known.get((iso, phase), (iso, None))
        matches = [k for d, k in computed if d == gen_iso and k.phase is MoonPhase(phase)]
        assert gen_kind is None or MoonDayKind(gen_kind) in matches, (iso, phase)
        assert len(matches) == 1, f"SYC {iso} {phase}: computed has no match on {gen_iso}"
        expected.add((gen_iso, matches[0]))

    assert computed == expected


def test_amavasya_march_2026_differs_by_location() -> None:
    march = date(2026, 3, 15), date(2026, 3, 22)

    def amavasya(city: str) -> list[MoonDay]:
        return compute_moon_days(_location(city), *march)

    assert amavasya("mysuru") == [MoonDay(date(2026, 3, 19), MoonDayKind.AMAVASYA)]
    for city in ["moscow", "saint-petersburg", "kyiv", "minsk"]:
        assert amavasya(city) == [MoonDay(date(2026, 3, 18), MoonDayKind.AMAVASYA)], city
    [yekaterinburg] = amavasya("yekaterinburg")
    assert yekaterinburg.kind is MoonDayKind.KSHAYA_AMAVASYA


def test_amavasya_may_2026_is_kshaya_east_of_the_urals() -> None:
    may = date(2026, 5, 13), date(2026, 5, 19)

    assert compute_moon_days(_location("mysuru"), *may) == [
        MoonDay(date(2026, 5, 16), MoonDayKind.AMAVASYA)
    ]
    for city in ["yekaterinburg", "novosibirsk", "astana", "almaty"]:
        assert compute_moon_days(_location(city), *may) == [
            MoonDay(date(2026, 5, 16), MoonDayKind.KSHAYA_AMAVASYA)
        ], city
