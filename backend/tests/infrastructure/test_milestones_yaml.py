from pathlib import Path

import pytest

from tristhana.infrastructure.seed.catalog_yaml import CatalogLoadError
from tristhana.infrastructure.seed.milestones_yaml import load_milestones

ROOT = Path(__file__).resolve().parents[3]


def test_the_seed_has_100_365_1000() -> None:
    counts = load_milestones(ROOT / "data" / "seed" / "milestones.yaml")

    assert counts.thresholds == (100, 365, 1000)


@pytest.mark.parametrize(
    "body",
    [
        "practice_counts: []\n",
        "practice_counts: [365, 100]\n",
        "practice_counts: [0]\n",
        "practice_counts: ['100']\n",
        "practice_counts: [100]\nbadges: [108]\n",
        "other: 1\n",
    ],
)
def test_a_malformed_file_is_refused(tmp_path: Path, body: str) -> None:
    path = tmp_path / "milestones.yaml"
    path.write_text(body, encoding="utf-8")

    with pytest.raises(CatalogLoadError):
        load_milestones(path)
