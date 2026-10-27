"""A body-size cap for the diary-note PUT (PR-07), enforced before the app reads the body:
over 16 KiB → 413 without buffering more than the cap (a note is at most 8000 bytes)."""

import json
import re
from typing import Any

from starlette.types import ASGIApp, Message, Receive, Scope, Send

MAX_BODY_BYTES = 16 * 1024
_NOTE_PATH = re.compile(r"^/api/v1/me/days/[^/]+/note$")


class NoteBodyLimit:
    def __init__(self, app: ASGIApp, limit: int = MAX_BODY_BYTES) -> None:
        self._app = app
        self._limit = limit

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if not (
            scope["type"] == "http" and scope["method"] == "PUT" and _NOTE_PATH.match(scope["path"])
        ):
            await self._app(scope, receive, send)
            return
        declared = dict(scope["headers"]).get(b"content-length", b"")
        if declared.isdigit() and int(declared) > self._limit:
            await _too_large(send)
            return
        # Chunked or undeclared: read at most the cap, then replay it to the app.
        body, more = b"", True
        while more:
            message = await receive()
            if message["type"] != "http.request":
                break
            body += message.get("body", b"")
            more = message.get("more_body", False)
            if len(body) > self._limit:
                await _too_large(send)
                return
        replayed = False

        async def replay() -> Message:
            nonlocal replayed
            if replayed:
                return await receive()
            replayed = True
            return {"type": "http.request", "body": body, "more_body": False}

        await self._app(scope, replay, send)


async def _too_large(send: Send) -> None:
    payload: Any = json.dumps({"code": "body_too_large"}).encode()
    await send(
        {
            "type": "http.response.start",
            "status": 413,
            "headers": [(b"content-type", b"application/json")],
        }
    )
    await send({"type": "http.response.body", "body": payload})
