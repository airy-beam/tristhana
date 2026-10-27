"""Integrity of the real seed files in data/seed/ (AC-01)."""

from functools import cache
from pathlib import Path

import pytest

from tristhana.domain.catalog import (
    Catalog,
    Sequence,
    SequenceItem,
    SequenceKind,
    SequenceStatus,
    validate_catalog,
)
from tristhana.infrastructure.seed.catalog_yaml import load_catalog

SEED = Path(__file__).resolve().parents[3] / "data" / "seed"


@cache
def _catalog() -> Catalog:
    return load_catalog(SEED / "asanas.yaml", SEED / "sequences.yaml")


def _seq(slug: str) -> Sequence:
    return next(s for s in _catalog().sequences if s.slug == slug)


def _item(seq: str, key: str) -> SequenceItem:
    return next(i for i in _seq(seq).items if i.key == key)


def _stops(seq: str) -> list[str]:
    return [i.key for i in _seq(seq).items if i.stop]


def test_seed_files_are_valid() -> None:
    assert [str(i) for i in validate_catalog(_catalog())] == []


def test_series_and_blocks() -> None:
    series = {s.number: s for s in _catalog().sequences if s.kind is SequenceKind.SERIES}

    assert [series[n].slug for n in range(1, 7)] == [
        "primary",
        "intermediate",
        "advanced-a",
        "advanced-b",
        "advanced-c",
        "advanced-d",
    ]
    assert series[5].status is SequenceStatus.PENDING
    assert series[5].items == ()
    assert series[6].status is SequenceStatus.PLACEHOLDER
    assert series[6].items == ()


def test_standing_ends_at_parsvottanasana() -> None:
    assert _stops("standing") == ["parsvottanasana"]
    assert not _item("standing", "utthita-trikonasana-b").stop


def test_primary_stop_points() -> None:
    stops = _stops("primary")

    assert stops[-1] == "setu-bandhasana"
    assert "navasana" in stops  # half primary
    assert "virabhadrasana-a" not in stops
    assert "virabhadrasana-b" in stops
    assert "dandasana" not in stops
    assert {"marichyasana-a", "marichyasana-b", "marichyasana-c", "marichyasana-d"} <= set(stops)
    assert {"janu-sirsasana-a", "janu-sirsasana-b", "janu-sirsasana-c"} <= set(stops)
    assert "paschimottanasana-c" in stops


def test_paschimottanasana_d_is_optional() -> None:
    d = _item("primary", "paschimottanasana-d")

    assert d.optional
    assert not d.stop


def test_intermediate_stop_points() -> None:
    stops = _stops("intermediate")

    assert stops[0] == "pasasana"
    assert stops[-1] == "baddha-hasta-sirsasana-d"
    assert "kapotasana-a" not in stops
    assert "kapotasana-b" in stops


def test_advanced_b_every_variant_is_a_stop() -> None:
    seq = _seq("advanced-b")

    assert all(i.stop for i in seq.items)
    assert seq.items[-1].key == "omkarasana"
    keys = {i.key for i in seq.items}
    assert {"samanasana", "sama-konasana", "marichyasana-e", "marichyasana-h"} <= keys


@pytest.mark.parametrize("key", ["drop-backs", "standing-up", "viparita-chakrasana"])
def test_backbending_milestones_are_optional(key: str) -> None:
    item = _item("backbending", key)

    assert item.optional
    assert item.milestone
    assert not item.stop


def test_backbending_order() -> None:
    assert [i.key for i in _seq("backbending").items] == [
        "urdhva-dhanurasana",
        "drop-backs",
        "standing-up",
        "vrksasana",
        "viparita-chakrasana",
        "paschimottanasana",
    ]


def test_catalog_is_signed_off_by_the_owner() -> None:
    # Users may only see names/meanings the owner has reviewed (AC-01 spec).
    catalog = _catalog()

    assert catalog.reviewed_by
    assert catalog.reviewed_on is not None
