"""Dump golden moon-day fixtures by running the ORIGINAL, owner-verified generator.py.

Nothing from the prior-art tree is copied into the repo; the generator is imported
read-only and only its output is written. Needs pytz (the generator uses it):

    cd backend && uv run --with pytz python ../tools/moon/dump_generator_fixtures.py \
        /path/to/ashtanga/moon_days
"""

import argparse
import datetime as dt
import importlib.util
import json
import sys
from importlib.metadata import version
from pathlib import Path

FIRST_YEAR, LAST_YEAR = 2025, 2100
# Start a month early so dedup state at 2025-01-01 matches a long continuous run.
SCAN_START = dt.date(FIRST_YEAR - 1, 12, 1)
SCAN_END = dt.date(LAST_YEAR, 12, 31)

KIND_NAMES = {0: "purnima", 1: "amavasya", 2: "kshaya_purnima", 3: "kshaya_amavasya"}

OUT_DIR = Path(__file__).resolve().parents[2] / "backend/tests/fixtures/moon/generator"


def load_generator(moon_days_dir: Path):
    path = moon_days_dir / "generator" / "generator.py"
    spec = importlib.util.spec_from_file_location("prior_art_generator", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # The generator sets a cwd-relative path at import; point it at the real files.
    module.swe.set_ephe_path(str(moon_days_dir / "swisseph"))
    module.START_DATE = SCAN_START
    module.END_DATE = SCAN_END
    return module


def slug(city: str) -> str:
    return city.lower().replace(" ", "-")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("moon_days_dir", type=Path)
    args = parser.parse_args()

    gen = load_generator(args.moon_days_dir.resolve())
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    meta_common = {
        "source": "moon_days/generator/generator.py (owner-verified), run unmodified",
        "pyswisseph": version("pyswisseph"),
        "pytz": version("pytz"),
        "scan": [SCAN_START.isoformat(), SCAN_END.isoformat()],
        "range": [f"{FIRST_YEAR}-01-01", f"{LAST_YEAR}-12-31"],
    }
    for name, city in gen.CITIES.items():
        events = [
            [e.date.isoformat(), KIND_NAMES[e.kind]]
            for e in gen.generate_moon_days(city)
            if e.date.year >= FIRST_YEAR
        ]
        doc = {
            "meta": meta_common | {"city": name, "location": city},
            "events": events,
        }
        out = OUT_DIR / f"{slug(name)}.json"
        out.write_text(json.dumps(doc, ensure_ascii=False, indent=0) + "\n", encoding="utf-8")
        print(f"{name:16} {len(events):5} events -> {out.name}", file=sys.stderr)


if __name__ == "__main__":
    main()
