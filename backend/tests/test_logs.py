import json
import logging
import sys

import pytest

from tristhana.logs import JsonFormatter, configure_logging


def _record(msg: str, *args: object, exc_info: bool = False) -> logging.LogRecord:
    info = None
    if exc_info:
        try:
            raise ValueError("boom")
        except ValueError:
            info = sys.exc_info()
    return logging.LogRecord("tristhana.test", logging.WARNING, __file__, 1, msg, args, info)


def test_json_formatter_emits_cloud_logging_fields() -> None:
    line = JsonFormatter().format(_record("Namaste %s", "🙏"))

    entry = json.loads(line)
    assert entry["severity"] == "WARNING"
    assert entry["message"] == "Namaste 🙏"
    assert entry["logger"] == "tristhana.test"
    assert entry["time"].endswith("+00:00")


def test_json_formatter_includes_exception() -> None:
    entry = json.loads(JsonFormatter().format(_record("failed", exc_info=True)))

    assert "ValueError: boom" in entry["exception"]


def test_configure_logging_routes_uvicorn_through_root(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("INFO", "json")

    logging.getLogger("uvicorn.error").info("started")

    entry = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert entry["logger"] == "uvicorn.error"
    assert entry["message"] == "started"
