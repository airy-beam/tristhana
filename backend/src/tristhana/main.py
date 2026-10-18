"""Composition root: wires settings, logging and adapters into one ASGI app.

Run with `uvicorn tristhana.main:app`.
"""

import asyncio
import logging
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI

from tristhana import __version__
from tristhana.api import v1
from tristhana.application.start import StartUseCase
from tristhana.bots.telegram.runtime import BotRuntime, build_runtime
from tristhana.bots.telegram.webhook import make_webhook_router
from tristhana.infrastructure.i18n.fluent import FluentTranslator
from tristhana.logs import configure_logging
from tristhana.settings import Settings, get_settings

log = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.effective_log_format)

    bot = _LazyBot(settings)
    app = FastAPI(
        title="Tristhana API",
        version=__version__,
        # Interactive docs only outside prod; the OpenAPI schema stays available for codegen.
        docs_url=None if settings.app_env == "prod" else "/docs",
        redoc_url=None,
        lifespan=bot.lifespan,
    )
    app.state.settings = settings
    app.include_router(v1.router)

    secret = settings.telegram_webhook_secret
    if _webhook_enabled(settings) and secret is not None:
        app.include_router(make_webhook_router(secret.get_secret_value(), bot.get))
    elif settings.telegram_mode == "webhook":
        log.warning("telegram webhook disabled: bot token or webhook secret not set")
    return app


def _webhook_enabled(settings: Settings) -> bool:
    return (
        settings.telegram_mode == "webhook"
        and settings.telegram_bot_token is not None
        and settings.telegram_webhook_secret is not None
    )


class _LazyBot:
    """Builds the aiogram runtime once. No network at startup; aiogram is imported during
    startup only when the webhook is enabled (preload, UI-01 spec), else on first use."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._runtime: BotRuntime | None = None

    def get(self) -> BotRuntime:
        if self._runtime is None:
            token = self._settings.telegram_bot_token
            if token is None:
                raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")
            self._runtime = build_runtime(
                token.get_secret_value(), StartUseCase(), FluentTranslator()
            )
        return self._runtime

    @asynccontextmanager
    async def lifespan(self, _app: FastAPI) -> AsyncGenerator[None]:
        polling: asyncio.Task[None] | None = None
        if _webhook_enabled(self._settings):
            # Preload aiogram (~3 s: it builds every Telegram type's schema on import) before
            # accepting traffic. Cloud Run gives full CPU at startup but throttles it after a
            # response, so a background import could stall on an instance kept warm by pings.
            started = time.perf_counter()
            await asyncio.to_thread(self.get)
            log.info("telegram runtime ready in %.0f ms", (time.perf_counter() - started) * 1000)
        if self._settings.telegram_mode == "polling" and self._settings.telegram_bot_token:
            from tristhana.bots.telegram.polling import run_polling

            polling = asyncio.create_task(run_polling(self.get()))
            polling.add_done_callback(_log_polling_end)
            log.info("telegram long polling started (dev)")
        try:
            yield
        finally:
            if polling is not None:
                polling.cancel()
                with suppress(asyncio.CancelledError, Exception):  # already logged
                    await polling
            if self._runtime is not None:
                await self._runtime.bot.session.close()


def _log_polling_end(task: asyncio.Task[None]) -> None:
    if not task.cancelled() and task.exception() is not None:
        # The type only: aiogram errors can echo request details.
        log.error("telegram polling stopped: %s", type(task.exception()).__name__)


app = create_app()
