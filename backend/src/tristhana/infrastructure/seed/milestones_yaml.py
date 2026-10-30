"""Strict loader for data/seed/milestones.yaml (GM-01 part 2, ADR-0028), cached per process."""

from functools import cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from tristhana.domain.milestones import InvalidThresholds, PracticeCounts
from tristhana.infrastructure.seed.catalog_yaml import (
    CatalogLoadError,
    _load_yaml,  # pyright: ignore[reportPrivateUsage] - the shared strict YAML reader
    _YamlError,  # pyright: ignore[reportPrivateUsage]
)


class _File(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    practice_counts: list[int] = Field(min_length=1)


@cache
def load_milestones(path: Path) -> PracticeCounts:
    try:
        parsed = _File.model_validate(_load_yaml(path.read_text(encoding="utf-8")))
        return PracticeCounts(tuple(parsed.practice_counts))
    except (OSError, ValidationError, _YamlError, InvalidThresholds) as e:
        raise CatalogLoadError(f"{path.name}: {e}") from e
