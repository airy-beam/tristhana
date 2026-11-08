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


@pytest.mark.parametrize("fmt", ["json", "text"])
def test_calendar_feed_tokens_never_reach_the_log(
    fmt: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """SC-06: the feed URL is the secret; uvicorn's access line must not carry it."""
    token = "Xy3kP9qR2sT5uV8wZ1aB4cD7eF0gH3iJ6kL9mN2oP5q"
    configure_logging("INFO", fmt)  # pyright: ignore[reportArgumentType]

    access = logging.getLogger("uvicorn.access")
    access.info('%s - "%s %s HTTP/%s" %d', "1.2.3.4:0", "GET", f"/ical/v1/{token}.ics", "1.1", 200)
    access.info(
        '%s - "%s %s HTTP/%s" %d', "1.2.3.4:0", "GET", f"/ical/v1/{token}/subscribe", "1.1", 302
    )
    access.info('%s - "%s %s HTTP/%s" %d', "1.2.3.4:0", "GET", "/api/v1/health", "1.1", 200)

    out = capsys.readouterr().out
    assert token not in out
    assert out.count("/ical/v1/***") == 2
    assert "/api/v1/health" in out
