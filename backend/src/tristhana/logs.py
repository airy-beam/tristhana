"""Logging setup: structured JSON lines for Cloud Logging, plain text for local dev."""

import json
import logging
import re
import sys
from datetime import UTC, datetime
from typing import override

from tristhana.settings import LogFormat

# Loggers that install their own handlers; we route them through the root handler instead.
_FRAMEWORK_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access")

# SC-06: a calendar feed URL is a capability (ADR-0036); access lines must not carry it.
# ST-07: share card image URLs are capabilities too (ADR-0040).
_FEED_TOKEN = re.compile(r"(/ical/v1/|/share/v1/|/me/share-cards/)[A-Za-z0-9_-]+")


class MaskFeedTokens(logging.Filter):
    @override
    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        if "/ical/" in message or "/share" in message:
            record.msg, record.args = _FEED_TOKEN.sub(r"\1***", message), None
        return True


class JsonFormatter(logging.Formatter):
    """One JSON object per line, using the field names Cloud Logging understands."""

    @override
    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, object] = {
            "time": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "severity": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False, default=str)


def configure_logging(level: str, fmt: LogFormat) -> None:
    handler = logging.StreamHandler(sys.stdout)
    if fmt == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s", "%H:%M:%S")
        )

    handler.addFilter(MaskFeedTokens())

    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())

    for name in _FRAMEWORK_LOGGERS:
        framework_logger = logging.getLogger(name)
        framework_logger.handlers.clear()
        framework_logger.propagate = True
