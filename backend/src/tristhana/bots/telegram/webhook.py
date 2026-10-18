"""`POST /telegram/webhook` (UI-01, ADR-0012). Imports only FastAPI/stdlib at module level.

Telegram retries non-2xx responses, so everything except a bad secret answers 200.
The handler runs to completion before responding: Cloud Run throttles CPU afterwards.
"""

from __future__ import annotations

import hmac
import logging
import time
import traceback
from collections import OrderedDict
from collections.abc import Callable
from typing import TYPE_CHECKING

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

if TYPE_CHECKING:
    from tristhana.bots.telegram.runtime import BotRuntime

log = logging.getLogger(__name__)

SECRET_HEADER = "X-Telegram-Bot-Api-Secret-Token"  # noqa: S105 - a header name, not a secret


class RecentUpdates:
    """Bounded per-instance memory of handled update_ids (Phase 1 moves this to the DB)."""

    def __init__(self, size: int = 1024) -> None:
        self._size = size
        self._seen: OrderedDict[int, None] = OrderedDict()

    def __contains__(self, update_id: int) -> bool:
        return update_id in self._seen

    def add(self, update_id: int) -> None:
        self._seen[update_id] = None
        if len(self._seen) > self._size:
            self._seen.popitem(last=False)


def make_webhook_router(secret: str, runtime: Callable[[], BotRuntime]) -> APIRouter:
    router = APIRouter(include_in_schema=False)
    expected = secret.encode()
    recent = RecentUpdates()

    @router.post("/telegram/webhook")
    async def telegram_webhook(request: Request) -> Response:  # pyright: ignore[reportUnusedFunction]
        given = request.headers.get(SECRET_HEADER, "").encode()
        if not hmac.compare_digest(given, expected):
            return Response(status_code=401)

        started = time.perf_counter()
        from aiogram.types import Update
        from pydantic import ValidationError

        rt = runtime()
        try:
            update = Update.model_validate_json(await request.body(), context={"bot": rt.bot})
        except ValidationError:
            log.warning("telegram update rejected: malformed body")
            return Response(status_code=200)

        if update.update_id in recent:
            _log(update.update_id, update.event_type, "duplicate", started)
            return Response(status_code=200)

        try:
            result = await rt.dispatcher.feed_update(rt.bot, update)
        except Exception as e:  # a code bug is not fixed by Telegram retrying
            # Type and stack frames only: exception messages may echo user text.
            _log(update.update_id, update.event_type, f"error {type(e).__name__}", started)
            log.error(
                "telegram handler failed (update_id=%s): %s\n%s",
                update.update_id,
                type(e).__name__,
                "".join(traceback.format_tb(e.__traceback__)),
            )
            return Response(status_code=200)
        recent.add(update.update_id)

        from aiogram.dispatcher.event.bases import UNHANDLED
        from aiogram.methods import TelegramMethod

        from tristhana.bots.telegram.runtime import webhook_reply

        if isinstance(result, TelegramMethod):
            _log(update.update_id, update.event_type, f"reply {result.__api_method__}", started)
            return JSONResponse(webhook_reply(rt, result))  # pyright: ignore[reportUnknownArgumentType]
        outcome = "unhandled" if result is UNHANDLED else "handled"
        _log(update.update_id, update.event_type, outcome, started)
        return Response(status_code=200)

    return router


def _log(update_id: int, event_type: str, outcome: str, started: float) -> None:
    # Never the body, headers, user ids, names or message text (privacy).
    log.info(
        "telegram update %s %s: %s in %.1f ms",
        update_id,
        event_type,
        outcome,
        (time.perf_counter() - started) * 1000,
    )
