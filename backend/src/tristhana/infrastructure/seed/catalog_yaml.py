"""Strict loader for data/seed/asanas.yaml + sequences.yaml into domain catalog types.

Strict on purpose: duplicate YAML keys, unknown fields and YAML 1.1 coercions (`no` → False)
are errors, so typos in hand-edited seed files never load silently.
"""

from datetime import date
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from tristhana.domain.catalog import (
    Asana,
    AsanaNames,
    Catalog,
    Meaning,
    Sequence,
    SequenceItem,
    SequenceKind,
    SequenceNames,
    SequenceStatus,
    validate_catalog,
)


class CatalogLoadError(Exception):
    """A seed file is missing, malformed, or does not match the schema."""


class _Model(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)


class _Names(_Model):
    latin: str
    iast: str | None
    ru: str


class _Meaning(_Model):
    en: str
    ru: str


class _Asana(_Model):
    slug: str
    names: _Names
    meaning: _Meaning
    variants: list[str] = []


class _Meta(_Model):
    schema_version: Literal[1]
    reviewed_by: str | None
    reviewed_on: date | None


class _AsanasFile(_Model):
    meta: _Meta
    asanas: list[_Asana]


class _Item(_Model):
    asana: str
    variant: str | None = None
    stop: bool = False
    optional: bool = False
    milestone: bool = False


class _SequenceNames(_Model):
    en: str
    ru: str


class _Sequence(_Model):
    slug: str
    kind: Literal["series", "block"]
    status: Literal["confirmed", "pending", "placeholder"]
    number: int | None = None
    names: _SequenceNames
    traditional_name: _Names | None = None
    items: list[_Item]


class _SequencesFile(_Model):
    sequences: list[_Sequence]


def load_catalog(asanas_path: Path, sequences_path: Path) -> Catalog:
    """Read and validate the seed files; raises CatalogLoadError listing every issue."""
    catalog = read_catalog(asanas_path, sequences_path)
    issues = validate_catalog(catalog)
    if issues:
        raise CatalogLoadError("invalid catalog:\n" + "\n".join(str(i) for i in issues))
    return catalog


def read_catalog(asanas_path: Path, sequences_path: Path) -> Catalog:
    """Read the seed files without validating the catalog (for review tooling)."""
    asanas = _parse(asanas_path, _AsanasFile)
    sequences = _parse(sequences_path, _SequencesFile)
    return Catalog(
        asanas=tuple(
            Asana(
                slug=a.slug,
                names=_names(a.names),
                meaning=Meaning(en=a.meaning.en, ru=a.meaning.ru),
                variants=tuple(a.variants),
            )
            for a in asanas.asanas
        ),
        sequences=tuple(
            Sequence(
                slug=s.slug,
                kind=SequenceKind(s.kind),
                status=SequenceStatus(s.status),
                names=SequenceNames(en=s.names.en, ru=s.names.ru),
                items=tuple(
                    SequenceItem(
                        asana=i.asana,
                        variant=i.variant,
                        stop=i.stop,
                        optional=i.optional,
                        milestone=i.milestone,
                    )
                    for i in s.items
                ),
                number=s.number,
                traditional_name=(
                    _names(s.traditional_name) if s.traditional_name is not None else None
                ),
            )
            for s in sequences.sequences
        ),
        reviewed_by=asanas.meta.reviewed_by,
        reviewed_on=asanas.meta.reviewed_on,
    )


def _names(n: _Names) -> AsanaNames:
    return AsanaNames(latin=n.latin, iast=n.iast, ru=n.ru)


def _parse[M: _Model](path: Path, model: type[M]) -> M:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        raise CatalogLoadError(f"{path}: cannot read ({e.strerror})") from e
    try:
        raw = _load_yaml(text)
        return model.model_validate(raw)
    except ValidationError as e:
        problems = "; ".join(
            f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in e.errors()
        )
        raise CatalogLoadError(f"{path.name}: {problems}") from e
    except _YamlError as e:
        raise CatalogLoadError(f"{path.name}: {e}") from e


class _YamlError(ValueError):
    pass


def _load_yaml(text: str) -> Any:
    import yaml  # lazy: only seeding needs it

    class StrictLoader(yaml.SafeLoader):
        pass

    def construct_mapping(loader: StrictLoader, node: yaml.MappingNode) -> dict[Any, Any]:
        mapping: dict[Any, Any] = {}
        for key_node, value_node in node.value:
            key = loader.construct_object(key_node)  # pyright: ignore[reportUnknownMemberType]
            if not isinstance(key, str):
                raise _YamlError(f"keys must be strings, line {key_node.start_mark.line + 1}")
            if key in mapping:
                raise _YamlError(f"duplicate key {key!r} at line {key_node.start_mark.line + 1}")
            mapping[key] = loader.construct_object(value_node)  # pyright: ignore[reportUnknownMemberType]
        return mapping

    StrictLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, construct_mapping)
    try:
        return yaml.load(text, Loader=StrictLoader)  # noqa: S506 - StrictLoader is a SafeLoader
    except yaml.YAMLError as e:
        raise _YamlError(f"invalid YAML: {e}") from e
