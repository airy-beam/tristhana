"""Strict loader for data/seed/badges.yaml (GM-02, ADR-0041): parsed once per process, then
checked against the catalog (`Track`) by `validate`."""

from datetime import time
from functools import cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from tristhana.domain.badges import BadgeDef, Group, InvalidBadges, RuleKind, validate
from tristhana.domain.practice import PracticeContext
from tristhana.domain.progression import Position, Track
from tristhana.infrastructure.seed.catalog_yaml import (
    CatalogLoadError,
    _load_yaml,  # pyright: ignore[reportPrivateUsage] - the shared strict YAML reader
    _YamlError,  # pyright: ignore[reportPrivateUsage]
)


class _Badge(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    key: str
    group: Literal["practice", "asanas"]
    icon: str = Field(min_length=1, max_length=16)
    rule: Literal[
        "practices",
        "run",
        "context",
        "early_start",
        "moon_rest",
        "return",
        "series_complete",
        "series_begins",
        "stop",
        "item",
    ]
    count: int | None = None
    days: int | None = None
    before: str | None = Field(default=None, pattern=r"^\d\d:\d\d$")
    context: Literal["led", "self"] | None = None
    series: str | None = None
    stop: str | None = None
    item: str | None = None

    def to_def(self) -> BadgeDef:
        target = Position(self.series, self.stop) if self.series is not None else None
        if target is None and self.stop is not None:
            raise InvalidBadges(f"{self.key}: a stop needs its series")
        return BadgeDef(
            self.key,
            Group(self.group),
            self.icon,
            RuleKind(self.rule),
            count=self.count,
            days=self.days,
            before=time.fromisoformat(self.before) if self.before is not None else None,
            context=PracticeContext(self.context) if self.context is not None else None,
            target=target,
            item=self.item,
        )


class _File(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    badges: list[_Badge] = Field(min_length=1)


@cache
def parse_badges(path: Path) -> tuple[BadgeDef, ...]:
    """The definitions as written (no catalog check yet): run alongside the catalog parse."""
    try:
        parsed = _File.model_validate(_load_yaml(path.read_text(encoding="utf-8")))
        return tuple(b.to_def() for b in parsed.badges)
    except (OSError, ValidationError, _YamlError, ValueError) as e:
        raise CatalogLoadError(f"{path.name}: {e}") from e


def check_badges(path: Path, defs: tuple[BadgeDef, ...], track: Track) -> tuple[BadgeDef, ...]:
    try:
        validate(defs, track)
    except InvalidBadges as e:
        raise CatalogLoadError(f"{path.name}: {e}") from e
    return defs


def load_badges(path: Path, track: Track) -> tuple[BadgeDef, ...]:
    return check_badges(path, parse_badges(path), track)
