"""The catalog for practice lengths, loaded once per process (ADR-0017)."""

import hashlib
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from tristhana.domain.practice import PracticeCatalog
from tristhana.infrastructure.seed.catalog_yaml import load_catalog


@dataclass(frozen=True, slots=True)
class LoadedCatalog:
    catalog: PracticeCatalog
    version: str  # content hash of the seed files: the API's ETag


@cache
def load_practice_catalog(seed_dir: Path) -> LoadedCatalog:
    asanas, sequences = seed_dir / "asanas.yaml", seed_dir / "sequences.yaml"
    digest = hashlib.sha256(asanas.read_bytes() + b"\0" + sequences.read_bytes()).hexdigest()
    return LoadedCatalog(PracticeCatalog(load_catalog(asanas, sequences)), digest[:16])
