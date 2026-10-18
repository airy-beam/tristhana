import json
from pathlib import Path

import pytest

from tristhana import openapi_dump


def test_dump_is_stable_and_excludes_the_webhook(tmp_path: Path) -> None:
    out = tmp_path / "openapi.json"

    openapi_dump.write(out)
    first = out.read_text()
    openapi_dump.write(out)

    assert out.read_text() == first
    schema = json.loads(first)
    assert "/api/v1/health" in schema["paths"]
    assert "/telegram/webhook" not in schema["paths"]


def test_check_detects_a_stale_file(tmp_path: Path) -> None:
    out = tmp_path / "openapi.json"
    out.write_text("{}\n")

    assert openapi_dump.is_fresh(out) is False
    openapi_dump.write(out)
    assert openapi_dump.is_fresh(out) is True


def test_committed_schema_is_fresh() -> None:
    if not openapi_dump.DEFAULT_PATH.exists():
        pytest.fail(f"missing {openapi_dump.DEFAULT_PATH}: run `uv run tristhana-openapi`")
    assert openapi_dump.is_fresh(openapi_dump.DEFAULT_PATH), "run `uv run tristhana-openapi`"
