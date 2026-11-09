"""SC-06's guard rails outside any one layer (spec §3, §7; ADR-0036): an import-linter
contract keeps `application.calendar_feed` off the log, diary, check-in, rest, progression and
teacher-view ports (direct imports, as SC-03), with no exception; the module itself imports none
of them; the domain module is pure; the serializer is a pure adapter with no runtime calendar
library (`icalendar` is dev-only, if anywhere); aiogram stays in `bots/telegram`; hashing and
token generation are stdlib; `member_windows` gains `moon_end`; the export excludes the table.
Import-linter itself runs in CI (`uv run lint-imports`); this pins that the contract is there."""

import ast
import inspect
import tomllib
from pathlib import Path
from typing import Any

from tristhana.application.ports.classes import ScheduleRepository

BACKEND = Path(__file__).resolve().parents[1]
SRC = BACKEND / "src" / "tristhana"
PRIVATE_PORTS = {
    "tristhana.application.ports.practice",
    "tristhana.application.ports.diary",
    "tristhana.application.ports.check_in",
    "tristhana.application.ports.rest_periods",
    "tristhana.application.ports.progression",
    "tristhana.application.ports.teacher_view",
}


def _imports(path: Path) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            found |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            found.add(module)
            found |= {f"{module}.{alias.name}" for alias in node.names}
    return found


def _project() -> dict[str, Any]:
    return tomllib.loads((BACKEND / "pyproject.toml").read_text())


def _contracts() -> list[dict[str, Any]]:
    return _project()["tool"]["importlinter"]["contracts"]


def test_an_import_contract_keeps_the_feed_off_private_ports() -> None:
    found = [
        c
        for c in _contracts()
        if "tristhana.application.calendar_feed" in c.get("source_modules", [])
        and set(c.get("forbidden_modules", [])) >= PRIVATE_PORTS
    ]

    assert len(found) == 1
    assert found[0]["type"] == "forbidden"
    assert found[0].get("ignore_imports", []) == []


def test_the_feed_use_cases_import_none_of_them_directly() -> None:
    for name in _imports(SRC / "application" / "calendar_feed.py"):
        assert not any(name.startswith(p) for p in PRIVATE_PORTS), name
        assert not name.startswith("tristhana.application.moon"), name


def test_the_domain_module_is_pure() -> None:
    allowed = (
        "collections",
        "dataclasses",
        "datetime",
        "enum",
        "re",
        "typing",
        "uuid",
        "tristhana.domain",
    )

    for name in _imports(SRC / "domain" / "calendar_feed.py"):
        assert name.startswith(allowed), name


def test_the_serializer_is_pure_and_hand_written() -> None:
    allowed = (
        "collections",
        "dataclasses",
        "datetime",
        "re",
        "typing",
        "tristhana.domain",
        "tristhana.application.calendar_feed",
    )

    for name in _imports(SRC / "api" / "ics.py"):
        assert name.startswith(allowed), name


def test_no_calendar_library_at_runtime() -> None:
    runtime = " ".join(_project()["project"]["dependencies"]).lower()

    assert "icalendar" not in runtime
    assert not any(d.lower().startswith("ics") for d in _project()["project"]["dependencies"])


def test_hashing_and_tokens_are_stdlib() -> None:
    use_cases = _imports(SRC / "application" / "calendar_feed.py")

    assert "hashlib" in use_cases


def test_aiogram_stays_in_the_bot_adapter() -> None:
    for path in (
        SRC / "domain" / "calendar_feed.py",
        SRC / "application" / "calendar_feed.py",
        SRC / "application" / "ports" / "calendar_feed.py",
        SRC / "api" / "ics.py",
    ):
        assert not any(n.startswith("aiogram") for n in _imports(path)), path


def test_member_windows_gains_a_moon_range() -> None:
    """Build decision: a `moon_start` too, so moon days reach 30 days back (Q148) while the
    classes read starts 16 days back."""
    params = inspect.signature(ScheduleRepository.member_windows).parameters

    assert list(params) == [
        "self", "me", "start", "end", "staff_only", "moon_city", "moon_end", "moon_start",
        "attendance",
    ]  # fmt: skip
    assert params["moon_end"].default is None
    assert params["attendance"].default is True  # SC-05 review: the feed passes False
    assert params["moon_start"].default is None


def test_my_windows_carries_the_moon_kinds() -> None:
    from dataclasses import fields

    from tristhana.application.ports.classes import MyWindows

    assert {"windows", "teachers", "my_moon", "my_moon_kinds"} <= {
        f.name for f in fields(MyWindows)
    }
