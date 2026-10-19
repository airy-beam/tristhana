"""Strict loader for data/seed/cities.yaml (MD-03, ADR-0019), cached per process."""

import re
from functools import cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from tristhana.domain.moon import Cities, City, MoonLocation
from tristhana.infrastructure.seed.catalog_yaml import (
    CatalogLoadError,
    _load_yaml,  # pyright: ignore[reportPrivateUsage] - the shared strict YAML reader
    _YamlError,  # pyright: ignore[reportPrivateUsage]
)

MAX_SLUG = 24  # callback data budget (m1:s:<slug>)
_SLUG = re.compile(r"[a-z]+(-[a-z]+)*")


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class _Names(_Model):
    en: str = Field(min_length=1)
    ru: str = Field(min_length=1)


class _City(_Model):
    slug: str
    names: _Names
    lat: float
    lon: float
    tz: str


class _File(_Model):
    default: str
    cities: list[_City]


@cache
def load_cities(path: Path) -> Cities:
    try:
        raw = _load_yaml(path.read_text(encoding="utf-8"))
        parsed = _File.model_validate(raw)
    except (OSError, ValidationError, _YamlError) as e:
        raise CatalogLoadError(f"{path.name}: {e}") from e
    cities: list[City] = []
    for c in parsed.cities:
        if not _SLUG.fullmatch(c.slug) or len(c.slug) > MAX_SLUG:
            raise CatalogLoadError(f"{path.name}: slug {c.slug!r}: kebab-case, <= {MAX_SLUG}")
        try:
            location = MoonLocation(float(c.lat), float(c.lon), c.tz)
        except ValueError as e:
            raise CatalogLoadError(f"{path.name}: {c.slug}: {e}") from e
        cities.append(City(c.slug, c.names.en, c.names.ru, location))
    slugs = [c.slug for c in cities]
    if len(set(slugs)) != len(slugs):
        raise CatalogLoadError(f"{path.name}: duplicate slugs")
    try:
        return Cities(tuple(cities), parsed.default)
    except ValueError as e:
        raise CatalogLoadError(f"{path.name}: {e}") from e
