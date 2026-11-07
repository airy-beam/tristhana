"""ST-06's guard rails outside any one layer (spec §1, §3, §7, ADR-0031): the read path has no key
and no second way to the private tables, `domain/stats.py` is not reused, the pure module is pure,
and the import contract exists. Import-linter itself runs in CI (`uv run lint-imports`); this pins
that the contract is there."""

import ast
import inspect
import tomllib
from pathlib import Path
from typing import Any, get_type_hints

import pytest

from tristhana.application import policies
from tristhana.application.ports.storage import Storage
from tristhana.application.ports.teacher_view import TeacherViewRepository
from tristhana.application.teacher_view import GetStudent, GetStudents

BACKEND = Path(__file__).resolve().parents[1]
SRC = BACKEND / "src" / "tristhana"
READ_PATH = [
    SRC / "domain" / "teacher_view.py",
    SRC / "application" / "teacher_view.py",
    SRC / "application" / "ports" / "teacher_view.py",
    SRC / "infrastructure" / "db" / "teacher_view.py",
]


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


def test_an_import_contract_keeps_the_read_path_off_the_key_and_the_private_ports() -> None:
    sources = {"tristhana.infrastructure.db.teacher_view", "tristhana.application.teacher_view"}
    forbidden = {
        "tristhana.infrastructure.crypto",
        "tristhana.application.ports.days",
        "tristhana.application.ports.progression",
    }

    found = [
        c
        for c in _contracts()
        if sources <= set(c.get("source_modules", []))
        and forbidden <= set(c.get("forbidden_modules", []))
    ]

    assert len(found) == 1


@pytest.mark.parametrize("path", READ_PATH, ids=lambda p: f"{p.parent.name}-{p.name}")
def test_no_module_of_the_read_path_touches_stats_the_key_or_the_private_ports(path: Path) -> None:
    imported = _imports(path)

    for name in imported:
        assert not name.startswith("tristhana.domain.stats"), name
        assert not name.startswith("tristhana.application.stats"), name
        assert not name.startswith("tristhana.infrastructure.crypto"), name
        assert not name.startswith("tristhana.application.ports.days"), name
        assert not name.startswith("tristhana.application.ports.progression"), name


def test_the_domain_module_is_pure() -> None:
    allowed = (
        "collections",
        "dataclasses",
        "datetime",
        "enum",
        "typing",
        "uuid",
        "tristhana.domain",
    )

    for name in _imports(READ_PATH[0]):
        assert name.startswith(allowed), name


def test_the_adapter_imports_no_table_it_must_not_read() -> None:
    names = {name.rsplit(".", 1)[-1] for name in _imports(READ_PATH[3])}

    assert not names & {
        "check_in",
        "diary_note",
        "progression_event",
        "practice_milestone",
        "notification_delivery",
    }


def test_the_adapter_doesnt_select_a_whole_table() -> None:
    """`select(practice)` would bring the private columns with it."""
    tree = ast.parse(READ_PATH[3].read_text())
    whole = {"account", "day_log", "rest_period", "practice", "progression", "teacher_link"}

    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "select":
            bare = {a.id for a in node.args if isinstance(a, ast.Name)}
            assert not bare & whole, ast.unparse(node)


def test_the_use_cases_module_loads_no_account_of_the_student() -> None:
    assert "tristhana.application.ports.accounts" not in _imports(READ_PATH[1])


@pytest.mark.parametrize("use_case", [GetStudents, GetStudent])
def test_both_use_cases_depend_on_the_port_and_the_clock(use_case: type) -> None:
    hints = get_type_hints(use_case.__init__)
    hints.pop("return", None)

    assert len(hints) == 2
    assert TeacherViewRepository in hints.values()


def test_storage_exposes_the_port() -> None:
    assert isinstance(inspect.getattr_static(Storage, "teacher_view"), property)


def test_the_policies_docstring_no_longer_promises_progression_to_teachers() -> None:
    assert "ST-06 adds linked teachers" not in (policies.can_view_progression.__doc__ or "")
