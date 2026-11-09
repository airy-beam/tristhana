"""GM-02 seed (spec §2, §4, §9): the strict loader refuses malformed files, the shipped file
validates against the catalog, and every badge has its copy in the Mini App's `badges.ftl`."""

import re
from functools import cache
from pathlib import Path

import pytest

from tests.domain.test_practice import catalog
from tristhana.domain.badges import Group, RuleKind
from tristhana.domain.progression import Position, Track
from tristhana.infrastructure.seed.badges_yaml import load_badges
from tristhana.infrastructure.seed.catalog_yaml import CatalogLoadError

ROOT = Path(__file__).resolve().parents[3]
SEED = ROOT / "data" / "seed" / "badges.yaml"
LOCALES = ROOT / "miniapp" / "src" / "locales"


@cache
def track() -> Track:
    return Track(catalog())


def test_the_shipped_set_is_the_first_20_in_order() -> None:
    defs = load_badges(SEED, track())

    assert [d.key for d in defs] == [
        "ekam", "nava", "shatam", "count-108", "count-365", "sahasra", "mandala",
        "before-dawn", "led-by-the-count", "self-practice", "rest-is-practice", "return",
        "yoga-chikitsa", "nadi-shodhana", "supta-kurmasana", "kapotasana", "karandavasana",
        "drop-backs", "standing-up", "tic-tacs",
    ]  # fmt: skip
    by = {d.key: d for d in defs}
    assert (by["mandala"].rule, by["mandala"].count) == (RuleKind.RUN, 40)
    assert by["before-dawn"].before is not None
    assert by["before-dawn"].before.isoformat() == "06:00:00"
    assert by["kapotasana"].target == Position("intermediate", "kapotasana-b")
    assert by["tic-tacs"].item == "viparita-chakrasana"
    assert by["return"].days == 14
    assert {d.group for d in defs[12:]} == {Group.ASANAS}
    assert {d.group for d in defs[:12]} == {Group.PRACTICE}


@pytest.mark.parametrize(
    "body",
    [
        "badges: []\n",
        "other: 1\n",
        "badges:\n  - {key: a, group: practice, icon: x, rule: practices}\n",  # no count
        "badges:\n  - {key: a, group: practice, icon: x, rule: practices, count: '1'}\n",
        "badges:\n  - {key: a, group: nope, icon: x, rule: practices, count: 1}\n",
        "badges:\n  - {key: a, group: practice, icon: x, rule: magic, count: 1}\n",
        "badges:\n  - {key: a, group: practice, icon: x, rule: practices, count: 1, extra: 1}\n",
        "badges:\n  - {key: a, group: practice, icon: x, rule: early_start, count: 1,"
        " before: '25:00'}\n",
        "badges:\n  - {key: a, group: asanas, icon: x, rule: stop, series: primary,"
        " stop: kapotasana-b}\n",
        "badges:\n  - {key: a, group: asanas, icon: x, rule: item, item: kurmasana}\n",
        "badges:\n  - {key: a, group: practice, icon: '', rule: practices, count: 1}\n",
    ],
)
def test_a_malformed_file_is_refused(tmp_path: Path, body: str) -> None:
    path = tmp_path / "badges.yaml"
    path.write_text(body, encoding="utf-8")

    with pytest.raises(CatalogLoadError):
        load_badges(path, track())


def _ftl(locale: str) -> str:
    return (LOCALES / locale / "badges.ftl").read_text(encoding="utf-8")


@pytest.mark.parametrize("locale", ["en", "ru"])
def test_every_badge_has_a_name_and_an_about_line(locale: str) -> None:
    text = _ftl(locale)
    for d in load_badges(SEED, track()):
        entry = re.search(rf"^badge-{re.escape(d.key)} =.*\n((?:[ \t]+.*\n)*)", text, re.M)
        assert entry is not None, (locale, d.key)
        assert re.search(r"^\s+\.about =", entry.group(1), re.M), (locale, d.key)
