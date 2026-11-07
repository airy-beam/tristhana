"""ID-04's guard rails outside any one layer (spec §6, §8, §10): `segno` stays behind
`infrastructure/qr.py` and off the import path, `domain/teacher_links.py` is pure, and the new
`TELEGRAM_BOT_USERNAME` setting reaches every place it is configured. Import-linter itself runs
in CI (`uv run lint-imports`); this pins that the contract is there."""

import ast
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

import pytest

from tristhana.settings import Settings

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
SRC = BACKEND / "src" / "tristhana"


def _pyproject() -> dict[str, Any]:
    return tomllib.loads((BACKEND / "pyproject.toml").read_text())


def test_segno_is_a_runtime_dependency() -> None:
    assert any(d.startswith("segno") for d in _pyproject()["project"]["dependencies"])


def test_an_import_contract_keeps_segno_in_infrastructure_qr() -> None:
    contracts = _pyproject()["tool"]["importlinter"]["contracts"]

    [contract] = [c for c in contracts if "segno" in c.get("forbidden_modules", [])]

    assert contract["ignore_imports"] == ["tristhana.infrastructure.qr -> segno"]
    assert {
        "tristhana.domain",
        "tristhana.application",
        "tristhana.infrastructure",
        "tristhana.api",
        "tristhana.bots",
        "tristhana.jobs",
        "tristhana.main",
    } <= set(contract["source_modules"])


def test_importing_the_app_does_not_load_segno() -> None:
    code = "import sys, tristhana.main; assert 'segno' not in sys.modules"

    subprocess.run([sys.executable, "-c", code], check=True)  # noqa: S603


async def test_the_qr_adapter_makes_a_png() -> None:
    from tristhana.infrastructure.qr import SegnoQrCodes

    png = SegnoQrCodes().png("https://t.me/tristhana_bot?start=t_aB3dE6gH9jK2mN5p")

    assert png.startswith(b"\x89PNG\r\n\x1a\n")


def test_the_domain_module_imports_only_the_standard_library() -> None:
    tree = ast.parse((SRC / "domain" / "teacher_links.py").read_text())

    imported = {
        (node.module or "").split(".")[0] if isinstance(node, ast.ImportFrom) else alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import | ast.ImportFrom)
        for alias in node.names
    }

    assert imported <= {
        "collections",
        "dataclasses",
        "datetime",
        "enum",
        "re",
        "typing",
        "unicodedata",
        "uuid",
    }


def test_the_bot_username_setting_defaults_to_empty() -> None:
    assert Settings(app_env="test").telegram_bot_username == ""  # pyright: ignore[reportAttributeAccessIssue]


@pytest.mark.parametrize("path", [".github/workflows/backend.yml", "backend/.env.example"])
def test_the_bot_username_is_configured(path: str) -> None:
    assert "TELEGRAM_BOT_USERNAME" in (ROOT / path).read_text()


def test_the_production_bot_name_is_set_on_deploy() -> None:
    assert (
        "TELEGRAM_BOT_USERNAME=tristhana_bot"
        in (ROOT / ".github/workflows/backend.yml").read_text()
    )
