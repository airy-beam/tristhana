from pathlib import Path

import pytest

from tristhana.infrastructure.seed.catalog_yaml import CatalogLoadError, load_catalog, read_catalog

ASANAS = """\
meta: {schema_version: 1, reviewed_by: null, reviewed_on: null}
asanas:
  - slug: padmasana
    names: {latin: Padmasana, iast: Padmāsana, ru: Падмасана}
    meaning: {en: Lotus pose, ru: Поза лотоса}
"""
SEQUENCES = """\
sequences:
  - slug: finishing
    kind: block
    status: confirmed
    names: {en: Finishing, ru: Завершающая последовательность}
    items:
      - {asana: padmasana}
"""


def _write(tmp_path: Path, asanas: str = ASANAS, sequences: str = SEQUENCES) -> tuple[Path, Path]:
    a, s = tmp_path / "asanas.yaml", tmp_path / "sequences.yaml"
    a.write_text(asanas, encoding="utf-8")
    s.write_text(sequences, encoding="utf-8")
    return a, s


def test_loads_into_domain_types(tmp_path: Path) -> None:
    catalog = read_catalog(*_write(tmp_path))

    assert catalog.asanas[0].names.iast == "Padmāsana"
    assert catalog.sequences[0].items[0].key == "padmasana"
    assert catalog.reviewed_on is None


def test_rejects_duplicate_keys(tmp_path: Path) -> None:
    dup = ASANAS.replace("slug: padmasana", "slug: padmasana\n    slug: padma")

    with pytest.raises(CatalogLoadError, match=r"asanas\.yaml.*duplicate key 'slug'"):
        read_catalog(*_write(tmp_path, asanas=dup))


def test_rejects_unknown_fields(tmp_path: Path) -> None:
    extra = ASANAS.replace("meaning:", "category: hip\n    meaning:")

    with pytest.raises(CatalogLoadError, match=r"asanas\.yaml.*category"):
        read_catalog(*_write(tmp_path, asanas=extra))


def test_rejects_yaml_boolean_coercion(tmp_path: Path) -> None:
    coerced = SEQUENCES.replace("{asana: padmasana}", "{asana: padmasana, variant: no}")

    with pytest.raises(CatalogLoadError, match=r"sequences\.yaml.*variant"):
        read_catalog(*_write(tmp_path, sequences=coerced))


def test_missing_file(tmp_path: Path) -> None:
    with pytest.raises(CatalogLoadError, match=r"nope\.yaml"):
        read_catalog(tmp_path / "nope.yaml", tmp_path / "sequences.yaml")


def test_rejects_non_string_keys(tmp_path: Path) -> None:
    complex_key = ASANAS.replace("slug: padmasana", "slug: padmasana\n    ? {a: 1}\n    : 2")

    with pytest.raises(CatalogLoadError, match="keys must be strings"):
        read_catalog(*_write(tmp_path, asanas=complex_key))


def test_rejects_quoted_number(tmp_path: Path) -> None:
    series = SEQUENCES.replace("kind: block", 'kind: series\n    number: "1"')

    with pytest.raises(CatalogLoadError, match=r"sequences\.yaml.*number"):
        read_catalog(*_write(tmp_path, sequences=series))


def test_load_catalog_validates(tmp_path: Path) -> None:
    # The minimal files parse, but are not a complete catalog (no series, three blocks missing).
    with pytest.raises(CatalogLoadError, match="series numbers must be exactly 1-6"):
        load_catalog(*_write(tmp_path))
