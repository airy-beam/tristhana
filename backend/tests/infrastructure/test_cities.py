import json
from datetime import date
from pathlib import Path

import pytest

from tristhana.domain.moon import calendar_years
from tristhana.infrastructure.seed.catalog_yaml import CatalogLoadError
from tristhana.infrastructure.seed.cities_yaml import load_cities
from tristhana.moon import compute_moon_days

ROOT = Path(__file__).resolve().parents[3]
CITIES = ROOT / "data" / "seed" / "cities.yaml"
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "moon" / "generator"


def test_mysuru_is_the_default_and_first() -> None:
    cities = load_cities(CITIES)

    assert cities.default.slug == "mysuru"
    assert cities.ordered("ru")[0].name("ru") == "Майсур"
    assert len(cities.all) >= 30
    assert cities.get(None) is cities.default
    assert cities.get("atlantis") is None


def test_fixture_cities_use_the_verified_coordinates() -> None:
    cities = load_cities(CITIES)
    for fixture in FIXTURES.glob("*.json"):
        meta = json.loads(fixture.read_text())["meta"]
        city = cities.get(fixture.stem)
        assert city is not None, fixture.stem
        loc = meta["location"]
        assert (city.location.lat, city.location.lon, city.location.tz) == (
            loc["lat"],
            loc["lon"],
            loc["tz"],
        )


def test_every_city_has_moon_days_in_every_stored_year() -> None:
    years = calendar_years(date.today())
    for city in load_cities(CITIES).all:
        days = compute_moon_days(city.location, date(years[0], 1, 1), date(years[-1], 12, 31))
        assert len(days) >= 24 * len(years), city.slug  # ~25 per year; never polar


def test_bad_files_are_rejected(tmp_path: Path) -> None:
    bad = tmp_path / "cities.yaml"
    bad.write_text(
        "default: x\ncities:\n"
        "  - {slug: Bad Slug, names: {en: A, ru: Б}, lat: 1.0, lon: 1.0, tz: UTC}\n"
    )
    with pytest.raises(CatalogLoadError):
        load_cities(bad)
