"""ID-07's guard rails outside any one layer (spec §3, §8; ADR-0046): a request is not a
link, so the request modules may not reach a log, a practice, a progression or the teacher
view; and no request table name appears in a reader of links. Import-linter itself runs in CI
(`uv run lint-imports`); this pins that the contract is there and names the right modules."""

import ast
import tomllib
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parents[1]
SRC = BACKEND / "src" / "tristhana"
MODULES = (
    "domain/teacher_requests.py",
    "application/teacher_requests.py",
    "application/ports/teacher_requests.py",
    "infrastructure/db/teacher_requests.py",
)
FORBIDDEN = ("days", "practice", "progression", "diary", "check_in", "teacher_view", "crypto")


def _contract() -> dict[str, Any]:
    contracts = tomllib.loads((BACKEND / "pyproject.toml").read_text())["tool"]["importlinter"][
        "contracts"
    ]
    [contract] = [c for c in contracts if "ID-07" in c["name"]]
    return contract


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            found.add(node.module or "")
        elif isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
    return found


def test_an_import_contract_keeps_requests_away_from_what_a_link_grants() -> None:
    contract = _contract()

    assert contract["type"] == "forbidden"
    assert set(contract["source_modules"]) == {
        "tristhana." + m.removesuffix(".py").replace("/", ".") for m in MODULES
    }
    for port in ("days", "practice", "progression", "diary", "check_in", "teacher_view"):
        assert f"tristhana.application.ports.{port}" in contract["forbidden_modules"]
    assert "tristhana.infrastructure.crypto" in contract["forbidden_modules"]


def test_the_request_modules_import_none_of_them() -> None:
    for module in MODULES:
        for imported in _imports(SRC / module):
            assert imported.rsplit(".", 1)[-1] not in FORBIDDEN, (module, imported)


def test_the_request_tables_reach_no_log_table() -> None:
    """The SQL repository names only people, memberships, links and the ledger."""
    tree = ast.parse((SRC / "infrastructure/db/teacher_requests.py").read_text())
    tables = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "tristhana.infrastructure.db.tables"
        for alias in node.names
    }

    assert tables == {
        "account",
        "identity",
        "notification_delivery",
        "notification_settings",
        "shala",
        "shala_staff",
        "shala_student",
        "teacher_link",
        "teacher_request",
    }


def test_no_reader_of_links_learns_that_requests_exist() -> None:
    """`teacher_link` gained no state (ADR-0046): the teacher view, the marks, the account
    load and the announcements never name the request table."""
    for reader in ("teacher_view", "progression", "accounts", "announcements", "notifications"):
        source = (SRC / "infrastructure" / "db" / f"{reader}.py").read_text()
        assert "teacher_request" not in source, reader
