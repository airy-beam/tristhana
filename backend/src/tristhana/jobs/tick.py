"""`POST /internal/tick` (ADR-0018): Cloud Scheduler calls it every 10 minutes. It sends due
reminders and keeps moon calendars filled, all inside the request (Cloud Run throttles the
CPU after the response). Auth: a shared secret header; a mismatch looks like no route."""

import hmac
import logging
from datetime import timedelta
from typing import cast

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

from tristhana.application.tick import RunTick

log = logging.getLogger(__name__)

TOKEN_HEADER = "X-Tristhana-Tick-Token"  # noqa: S105 - a header name, not a secret
BUDGET = timedelta(seconds=40)  # the service timeout is 60 s


def make_tick_router(token: str) -> APIRouter:
    router = APIRouter(include_in_schema=False)
    expected = token.encode()

    @router.post("/internal/tick")
    async def tick(request: Request) -> Response:  # pyright: ignore[reportUnusedFunction]
        given = request.headers.get(TOKEN_HEADER, "").encode()
        if not hmac.compare_digest(given, expected):
            return Response(status_code=404)
        run = cast(RunTick, request.app.state.run_tick)
        result = await run.execute(BUDGET)
        body = {
            "sent": result.sent,
            "skipped": result.skipped,
            "failed": result.failed,
            "blocked": result.blocked,
            "computed": result.computed,
            "pruned": result.pruned,
            "stopped_early": result.stopped_early,
        }
        log.info("tick: %s", body)  # counts only, never ids or text
        return JSONResponse(body)

    return router
