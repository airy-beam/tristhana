"""The public calendar feed (SC-06, ADR-0036): `/ical/v1/{token}.ics` for calendar apps.

The token is the authentication (a capability URL), so these routes sit outside `/api/v1`
auth, CORS and OpenAPI. Every dead link (malformed, unknown, rotated, revoked, deleted
account) gets the same 404. Our log line carries only a hash prefix of the token; the
platform's request log needs an exclusion filter for `/ical/` (Q153).
"""

import hashlib
import logging
import time
from typing import cast

from fastapi import APIRouter, Request, Response
from fastapi.responses import RedirectResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from tristhana.api.ics import render
from tristhana.application.calendar_feed import CalendarFeedUseCases, webcal_url
from tristhana.domain.calendar_feed import TOKEN_RE

log = logging.getLogger(__name__)
PREFIX = "/ical/"
_HEADERS = {
    "Cache-Control": "private, max-age=1800",
    "Content-Disposition": 'inline; filename="tristhana.ics"',
    "X-Robots-Tag": "noindex",
    "Referrer-Policy": "no-referrer",
}


def _hint(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()[:8]


def _not_found() -> Response:
    return Response(
        status_code=404,
        content=b"Not found\n",
        media_type="text/plain",
        headers={"Cache-Control": "no-store", "X-Robots-Tag": "noindex"},
    )


def make_ical_router() -> APIRouter:
    router = APIRouter(prefix="/ical/v1", include_in_schema=False)

    @router.api_route("/{token}.ics", methods=["GET", "HEAD"])
    async def feed(token: str, request: Request) -> Response:  # pyright: ignore[reportUnusedFunction]
        started = time.perf_counter()
        use_cases = cast(CalendarFeedUseCases, request.app.state.calendar_feed)
        # Off (no PUBLIC_API_URL): no feed is served, not only hidden.
        found = await use_cases.feed.execute(token) if use_cases.available else None
        if found is None:
            log.info("ical feed 404 token=%s", _hint(token))
            return _not_found()
        body = render(found)
        etag = f'"{hashlib.sha256(body).hexdigest()[:16]}"'
        headers = {**_HEADERS, "ETag": etag}
        sent = {
            t.strip().removeprefix("W/")
            for t in request.headers.get("if-none-match", "").split(",")
        }
        matched = etag in sent or "*" in sent
        log.info(
            "ical feed %s token=%s events=%d bytes=%d ms=%.1f",
            304 if matched else 200,
            _hint(token),
            len(found.events),
            len(body),
            (time.perf_counter() - started) * 1000,
        )
        if matched:
            return Response(status_code=304, headers=headers)
        if request.method == "HEAD":
            return Response(media_type="text/calendar; charset=utf-8", headers=headers)
        return Response(body, media_type="text/calendar; charset=utf-8", headers=headers)

    @router.get("/{token}/subscribe")
    async def subscribe(token: str, request: Request) -> Response:  # pyright: ignore[reportUnusedFunction]
        """Telegram only opens https links: this hands Apple/Outlook the webcal:// form. No
        read: a dead but well-formed token just gets a dead calendar link."""
        use_cases = cast(CalendarFeedUseCases, request.app.state.calendar_feed)
        if not use_cases.available or TOKEN_RE.fullmatch(token) is None:
            return _not_found()
        return RedirectResponse(
            webcal_url(use_cases.public_url, token),
            status_code=302,
            headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
        )

    return router


class NoCorsForFeed:
    """Strips CORS headers from `/ical/` responses: the feed is for calendar apps, never for
    a browser page (added outside CORSMiddleware)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = str(scope.get("path", ""))
        if scope["type"] != "http" or not path.startswith((PREFIX, "/share/")):
            await self.app(scope, receive, send)
            return

        async def without_cors(message: Message) -> None:
            if message["type"] == "http.response.start":
                message["headers"] = [
                    (k, v)
                    for k, v in message.get("headers", [])
                    if not k.lower().startswith(b"access-control-")
                ]
            await send(message)

        await self.app(scope, receive, without_cors)
