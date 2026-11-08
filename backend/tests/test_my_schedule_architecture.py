"""SC-03's guard rails outside any one layer (spec §3, §7, §8; ADR-0035): `application.classes`
reads my moon city from the pure `domain.accounts.moon_follow_of` and my moon dates through the
schedule port, so it imports no log, rest or women's-health port and not `application.moon`,
with no import-linter exception; the domain module stays pure; aiogram stays in
`bots/telegram`; the port's one read replaces `staff_windows`. Import-linter itself runs in CI
(`uv run lint-imports`); this pins that the contract is there."""

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


def _contracts() -> list[dict[str, Any]]:
    project = tomllib.loads((BACKEND / "pyproject.toml").read_text())
    return project["tool"]["importlinter"]["contracts"]


def test_an_import_contract_keeps_the_classes_use_cases_off_private_ports() -> None:
    forbidden = PRIVATE_PORTS | {"tristhana.application.moon"}

    found = [
        c
        for c in _contracts()
        if "tristhana.application.classes" in c.get("source_modules", [])
        and forbidden <= set(c.get("forbidden_modules", []))
    ]

    assert len(found) == 1
    assert found[0].get("ignore_imports", []) == []  # no exception (spec §3)


def test_the_classes_use_cases_import_none_of_them_directly() -> None:
    imported = _imports(SRC / "application" / "classes.py")

    for name in imported:
        assert not any(name.startswith(p) for p in PRIVATE_PORTS), name
        assert not name.startswith("tristhana.application.moon"), name
        assert not name.startswith("tristhana.application.ports.moon"), name


def test_my_moon_city_comes_from_the_pure_domain_function() -> None:
    assert "tristhana.domain.accounts.moon_follow_of" in _imports(
        SRC / "application" / "classes.py"
    )


def test_the_domain_module_is_pure() -> None:
    allowed = (
        "collections",
        "dataclasses",
        "datetime",
        "enum",
        "typing",
        "uuid",
        "zoneinfo",
        "tristhana.domain",
    )

    for name in _imports(SRC / "domain" / "classes.py"):
        assert name.startswith(allowed), name


def test_aiogram_stays_in_the_bot_adapter() -> None:
    for path in (
        SRC / "domain" / "classes.py",
        SRC / "application" / "classes.py",
        SRC / "application" / "ports" / "classes.py",
        SRC / "api" / "v1" / "classes.py",
    ):
        assert not any(n.startswith("aiogram") for n in _imports(path)), path


def test_the_port_has_member_windows_instead_of_staff_windows() -> None:
    params = inspect.signature(ScheduleRepository.member_windows).parameters

    # SC-06 (spec §3) appends `moon_end`; `test_calendar_feed_architecture.py` pins it.
    assert list(params)[:6] == ["self", "me", "start", "end", "staff_only", "moon_city"]
    assert params["staff_only"].default is False
    assert params["moon_city"].default is None
    assert not hasattr(ScheduleRepository, "staff_windows")


def test_the_adapter_reads_only_the_moon_table_of_the_private_data() -> None:
    """`member_windows` reads `moon_day` (and teacher links), never a log, rest or 🌸 table."""
    source = (SRC / "infrastructure" / "db" / "classes.py").read_text()
    names = {n.rsplit(".", 1)[-1] for n in _imports(SRC / "infrastructure" / "db" / "classes.py")}

    assert "member_windows" in source
    assert not names & {"day_log", "rest_period", "check_in", "diary_note", "practice"}
