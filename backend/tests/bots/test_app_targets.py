"""The bot's buttons into the Mini App land somewhere (UI-06 stage 6, spec §2, §9).

`screens.APP_OPEN` lists every `open` value the bot builds; each must be a `case` of the Mini
App's `launchNav` (`miniapp/src/shell/nav.ts`), where an unknown value opens Today. Every
literal `app_url(…, "<open>")` in the bot must be in that list, so a new target cannot skip it.
"""

import re
from pathlib import Path

from tristhana.bots.telegram import screens

_ROOT = Path(__file__).resolve().parents[3]
_NAV = _ROOT / "miniapp" / "src" / "shell" / "nav.ts"
_BOT = _ROOT / "backend" / "src" / "tristhana" / "bots" / "telegram"


def _nav_cases() -> set[str]:
    source = _NAV.read_text(encoding="utf-8")
    body = source[source.index("export function launchNav") :]
    return set(re.findall(r'case "([a-z-]+)":', body))


def _bot_targets() -> dict[str, set[str]]:
    """`open` values passed as a string literal to `app_url`, by file."""
    found: dict[str, set[str]] = {}
    for file in sorted(_BOT.glob("*.py")):
        for value in re.findall(
            r'app_url\(\s*[^,()]+,\s*"([a-z][a-z-]*)"', file.read_text("utf-8")
        ):
            found.setdefault(value, set()).add(file.name)
    return found


def test_every_target_the_bot_builds_is_a_case_in_the_mini_apps_launch_nav() -> None:
    cases = _nav_cases()
    assert "shala" in cases  # the reader works: the four stage 6 targets are there
    assert set(screens.APP_OPEN) - cases == set()


def test_every_literal_target_in_the_bot_is_listed() -> None:
    targets = _bot_targets()
    # The stage 6 buttons are built here (card, week, My schedule, Today's step, overview).
    assert {"shala", "class", "edit-shala", "schedule"} <= set(targets)
    unlisted = {value: files for value, files in targets.items() if value not in screens.APP_OPEN}
    assert unlisted == {}


def test_app_url_builds_the_query() -> None:
    url = screens.app_url("https://app.example", "class", shala="abc")
    assert url == "https://app.example?open=class&shala=abc"
    assert screens.app_url("https://app.example?x=1", "schedule") == (
        "https://app.example?x=1&open=schedule"
    )
    assert screens.app_url("https://app.example", "shala", shala=None) == (
        "https://app.example?open=shala"
    )
