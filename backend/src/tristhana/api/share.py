"""The public share card image (ST-07, ADR-0040): `/share/v1/{token}.png`.

The token is the access (a capability URL), so the route sits outside `/api/v1` auth and
OpenAPI. Unknown, expired and malformed tokens get the same 404. Our log line carries only
a hash prefix of the token; `MaskFeedTokens` masks it in access lines too.
"""

import hashlib
import logging
from typing import cast

from fastapi import APIRouter, Request, Response

from tristhana.application.share_cards import ShareCardUseCases

log = logging.getLogger(__name__)
PREFIX = "/share/"


def _not_found() -> Response:
    return Response(
        status_code=404,
        content=b"Not found\n",
        media_type="text/plain",
        headers={"Cache-Control": "no-store", "X-Robots-Tag": "noindex"},
    )


def make_share_router() -> APIRouter:
    router = APIRouter(prefix="/share/v1", include_in_schema=False)

    @router.api_route("/{token}.png", methods=["GET", "HEAD"])
    async def image(token: str, request: Request) -> Response:  # pyright: ignore[reportUnusedFunction]
        use_cases = cast(ShareCardUseCases, request.app.state.share_cards)
        png = await use_cases.image.execute(token) if use_cases.available else None
        if png is None:
            log.info("share card 404 token=%s", hashlib.sha256(token.encode()).hexdigest()[:8])
            return _not_found()
        headers = {
            "Cache-Control": "public, max-age=3600",  # the card lives 24 h at most
            "X-Content-Type-Options": "nosniff",
            "X-Robots-Tag": "noindex",
            "Referrer-Policy": "no-referrer",
        }
        if request.method == "HEAD":
            headers["Content-Length"] = str(len(png))
            return Response(media_type="image/png", headers=headers)
        return Response(png, media_type="image/png", headers=headers)

    return router
