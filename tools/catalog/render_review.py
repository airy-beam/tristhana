"""Render the seed catalog as a Markdown review table for the owner (Obsidian notes).

    cd backend && uv run python ../tools/catalog/render_review.py \
        "/home/pumpkin_vibe/Documents/pumpkin_notes/02_projects/tristhana_bot"

Writes `08b Asana Catalog Review (generated).md`. Overwritten on every run; never hand-edit it.
Corrections go into data/seed/*.yaml.
"""

import argparse
import datetime as dt
from pathlib import Path

from tristhana.domain.catalog import Asana, validate_catalog
from tristhana.infrastructure.seed.catalog_yaml import read_catalog

SEED = Path(__file__).resolve().parents[2] / "data" / "seed"
OUT_NAME = "08b Asana Catalog Review (generated).md"


def _cell(text: str | None) -> str:
    return (text or "-").replace("|", "\\|").replace("\n", " ")


def render() -> str:
    catalog = read_catalog(SEED / "asanas.yaml", SEED / "sequences.yaml")
    issues = validate_catalog(catalog)
    asanas: dict[str, Asana] = {a.slug: a for a in catalog.asanas}
    flagged = _review_flags(SEED / "asanas.yaml")

    lines = [
        "---",
        "tags: [tristhana_bot, asanas, generated]",
        f"generated: {dt.date.today().isoformat()}",
        "---",
        "# Asana Catalog Review (generated)",
        "",
        "> [!warning] Generated from `data/seed/*.yaml` by `tools/catalog/render_review.py`.",
        "> Don't edit this note: corrections go into the YAML. ⏹ = stop point, ○ = optional,",
        "> 🎯 = milestone, ❓ = needs an answer (see its `REVIEW:` comment in asanas.yaml).",
        "",
        f"Reviewed: **{catalog.reviewed_on or 'not yet'}** · validation issues: **{len(issues)}**",
        "",
        *(f"- ⚠️ {issue}" for issue in issues),
    ]
    for seq in catalog.sequences:
        title = f"## {seq.names.en} / {seq.names.ru}"
        if seq.traditional_name:
            title += f" ({seq.traditional_name.latin})"
        lines += [title, ""]
        if not seq.items:
            lines += [f"_Empty ({seq.status})._", ""]
            continue
        lines += [
            "| # | Slug | Display | IAST | RU | Meaning EN | Meaning RU | |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for pos, item in enumerate(seq.items, 1):
            a = asanas.get(item.asana)
            if a is None:
                lines.append(f"| {pos} | `{item.key}` | ⚠️ unknown asana | | | | | |")
                continue
            suffix = f" {item.variant.upper()}" if item.variant else ""
            marks = "".join(
                m
                for m, on in [
                    ("⏹", item.stop),
                    ("○", item.optional),
                    ("🎯", item.milestone),
                    ("❓", a.slug in flagged),
                ]
                if on
            )
            lines.append(
                f"| {pos} | `{item.key}` | {_cell(a.names.latin + suffix)} | {_cell(a.names.iast)} "
                f"| {_cell(a.names.ru + suffix)} | {_cell(a.meaning.en)} | {_cell(a.meaning.ru)} "
                f"| {marks} |"
            )
        lines.append("")
    return "\n".join(lines)


def _review_flags(path: Path) -> set[str]:
    """Slugs of asanas preceded by a `# REVIEW:` comment in the YAML."""
    flagged: set[str] = set()
    pending = False
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("# REVIEW:"):
            pending = True
        elif stripped.startswith("- slug:") and pending:
            flagged.add(stripped.removeprefix("- slug:").strip())
            pending = False
    return flagged


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("notes_dir", type=Path)
    args = parser.parse_args()
    out = args.notes_dir / OUT_NAME
    out.write_text(render() + "\n", encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
