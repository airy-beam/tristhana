"""Composition root: wires settings, logging and adapters into one ASGI app.

Run with `uvicorn tristhana.main:app`.
"""

import asyncio
import importlib
import logging
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from tristhana import __version__
from tristhana.api import v1
from tristhana.api.errors import install_error_handlers
from tristhana.application.accounts import EnsureAccount, RecordDeviceTimezone
from tristhana.application.days import ClearDayStatus, GetDays, SetDayStatus
from tristhana.application.moon import (
    GetMoonView,
    NotificationSettingsUseCase,
    SetMoonLocation,
    UpdateMoonReminders,
    UseCityTimezone,
)
from tristhana.application.ports.notifications import Notifier
from tristhana.application.ports.storage import Storage
from tristhana.application.practice import (
    ClearPractice,
    CopyLastPractice,
    GetPracticePresets,
    SavePractice,
)
from tristhana.application.remind import (
    AnswerPracticeOffer,
    QuickLogSameAsLast,
    UpdatePracticeReminder,
)
from tristhana.application.rest_days import DismissDayOffQuestion, SetDayOff
from tristhana.application.settings import PatchNotificationSettings, UpdateProfile
from tristhana.application.stats import GetYearStats
from tristhana.application.tick import RunTick
from tristhana.bots.telegram.notifier import TelegramNotifier
from tristhana.bots.telegram.runtime import (
    BotRuntime,
    DayUseCases,
    MoonUseCases,
    PracticeUseCases,
    RemindUseCases,
    SettingsUseCases,
    build_runtime,
)
from tristhana.bots.telegram.webhook import make_webhook_router
from tristhana.infrastructure.clock import SystemClock
from tristhana.infrastructure.db.storage import PostgresStorage, UnconfiguredStorage
from tristhana.infrastructure.i18n.fluent import FluentTranslator
from tristhana.infrastructure.moon_calc import GeneratorMoonCalculator
from tristhana.infrastructure.seed.cities_yaml import load_cities
from tristhana.infrastructure.seed.practice_catalog import load_practice_catalog
from tristhana.logs import configure_logging
from tristhana.settings import Settings, get_settings

log = logging.getLogger(__name__)


def create_app(
    settings: Settings | None = None,
    storage: Storage | None = None,
    notifier: Notifier | None = None,
) -> FastAPI:
    """`storage` and `notifier` are for tests (fakes); by default they follow the settings."""
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.effective_log_format)

    bot = _LazyBot(settings)
    services = _Services(
        storage or _storage(settings),
        bot,
        settings,
        notifier or TelegramNotifier(bot.get, FluentTranslator()),
    )
    app = FastAPI(
        title="Tristhana API",
        version=__version__,
        # Interactive docs only outside prod; the OpenAPI schema stays available for codegen.
        docs_url=None if settings.app_env == "prod" else "/docs",
        redoc_url=None,
        lifespan=services.lifespan,
    )
    app.state.settings = settings
    if settings.cors_origin_list:
        # Exact origins, no credentials (bearer tokens, not cookies); the long max_age means
        # one preflight per session instead of one per request.
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origin_list,
            allow_credentials=False,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
            allow_headers=["Authorization", "Content-Type"],
            max_age=7200,
        )
    install_error_handlers(app)
    app.include_router(v1.router)

    token = settings.telegram_bot_token
    if settings.app_env == "dev" and settings.dev_init_data and token is not None:
        from tristhana.api.dev import make_dev_router

        app.include_router(make_dev_router(token.get_secret_value()))

    tick_token = settings.internal_tick_token
    if tick_token is not None:
        from tristhana.jobs.tick import make_tick_router

        app.include_router(make_tick_router(tick_token.get_secret_value()))

    secret = settings.telegram_webhook_secret
    if _webhook_enabled(settings) and secret is not None:
        app.include_router(make_webhook_router(secret.get_secret_value(), bot.get))
    elif settings.telegram_mode == "webhook":
        log.warning("telegram webhook disabled: bot token or webhook secret not set")
    return app


def _storage(settings: Settings) -> Storage:
    if settings.database_url is None:
        return UnconfiguredStorage()
    from tristhana.infrastructure.crypto import FieldCipher, MissingCipher

    keys = settings.field_encryption_keys
    return PostgresStorage(
        settings.database_url.get_secret_value(),
        ca_file=settings.database_ca_file,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        cipher=FieldCipher(keys.get_secret_value()) if keys else MissingCipher(),
    )


def _webhook_enabled(settings: Settings) -> bool:
    return (
        settings.telegram_mode == "webhook"
        and settings.telegram_bot_token is not None
        and settings.telegram_webhook_secret is not None
    )


class _Services:
    """Starts storage, builds the use cases once it is up, then hands them to the adapters."""

    def __init__(
        self, storage: Storage, bot: "_LazyBot", settings: Settings, notifier: Notifier
    ) -> None:
        self._storage = storage
        self._bot = bot
        self._settings = settings
        self._notifier = notifier

    @asynccontextmanager
    async def lifespan(self, app: FastAPI) -> AsyncGenerator[None]:
        # The aiogram import and the catalog parse (CPU, in threads) overlap the DB warm-up's
        # network wait.
        seed = self._settings.seed_dir
        _, _, loaded, cities = await asyncio.gather(
            self._storage.start(),
            self._bot.preimport(),
            asyncio.to_thread(load_practice_catalog, seed),
            asyncio.to_thread(load_cities, seed / "cities.yaml"),
        )
        clock = SystemClock()
        ensure = EnsureAccount(self._storage.accounts, clock)
        days = DayUseCases(
            get=GetDays(self._storage.days, cities, clock),
            set=SetDayStatus(self._storage.days, clock),
            clear=ClearDayStatus(self._storage.days),
        )
        app.state.storage = self._storage
        app.state.ensure_account = ensure
        app.state.record_device_timezone = RecordDeviceTimezone(self._storage.accounts)
        app.state.get_days, app.state.set_day_status = days.get, days.set
        app.state.clear_day_status = days.clear
        practices = PracticeUseCases(
            save=SavePractice(self._storage.practices, loaded.catalog),
            copy_last=CopyLastPractice(self._storage.practices),
            clear=ClearPractice(self._storage.practices),
            presets=GetPracticePresets(self._storage.practices, loaded.catalog),
            catalog=loaded.catalog,
        )
        app.state.save_practice, app.state.clear_practice = practices.save, practices.clear
        app.state.practice_presets = practices.presets
        app.state.practice_catalog, app.state.catalog_version = loaded.catalog, loaded.version
        moon = MoonUseCases(
            cities=cities,
            view=GetMoonView(cities, self._storage.moon, self._storage.notifications, clock),
            set_location=SetMoonLocation(cities, self._storage.accounts),
            use_city_zone=UseCityTimezone(cities, self._storage.accounts),
            reminders=UpdateMoonReminders(self._storage.notifications),
        )
        app.state.moon, app.state.cities = moon, cities
        app.state.year_stats = GetYearStats(
            self._storage.days, self._storage.moon, cities, loaded.catalog, clock
        )
        notification_settings = NotificationSettingsUseCase(self._storage.notifications)
        app.state.notification_settings = notification_settings
        app.state.update_profile = UpdateProfile(self._storage.accounts)
        app.state.patch_notification_settings = PatchNotificationSettings(
            self._storage.notifications
        )
        remind = RemindUseCases(
            settings=notification_settings,
            update=UpdatePracticeReminder(self._storage.notifications),
            offer=AnswerPracticeOffer(self._storage.notifications, clock),
            quick_log=QuickLogSameAsLast(self._storage.days, self._storage.practices, clock),
            day_off=SetDayOff(self._storage.accounts, clock),
            dismiss_day_off=DismissDayOffQuestion(self._storage.accounts),
        )
        app.state.set_day_off, app.state.dismiss_day_off = remind.day_off, remind.dismiss_day_off
        app.state.run_tick = RunTick(
            clock,
            cities,
            self._storage.moon,
            GeneratorMoonCalculator(),
            self._storage.notifications,
            self._notifier,
        )
        self._bot.ensure_account = ensure
        self._bot.days = days
        self._bot.practices = practices
        self._bot.moon = moon
        self._bot.remind = remind
        self._bot.settings = SettingsUseCases(
            profile=app.state.update_profile,
            settings=notification_settings,
            cities=cities,
            today=days.get.today,
            day_off=remind.day_off,
        )
        try:
            async with self._bot.lifespan():
                yield
        finally:
            await self._storage.stop()


class _LazyBot:
    """Builds the aiogram runtime once. No network at startup; aiogram is imported during
    startup only when the webhook is enabled (preload, UI-01 spec), else on first use."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._runtime: BotRuntime | None = None
        self.ensure_account: EnsureAccount | None = None  # set in the lifespan
        self.days: DayUseCases | None = None
        self.practices: PracticeUseCases | None = None
        self.moon: MoonUseCases | None = None
        self.remind: RemindUseCases | None = None
        self.settings: SettingsUseCases | None = None

    def get(self) -> BotRuntime:
        if self._runtime is None:
            token = self._settings.telegram_bot_token
            if token is None:
                raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")
            if (
                self.ensure_account is None
                or self.days is None
                or self.practices is None
                or self.moon is None
                or self.remind is None
                or self.settings is None
            ):
                raise RuntimeError("bot used before startup")
            self._runtime = build_runtime(
                token.get_secret_value(),
                self.ensure_account,
                self.days,
                self.practices,
                self.moon,
                self.remind,
                self.settings,
                FluentTranslator(),
                self._settings.miniapp_url,
            )
        return self._runtime

    async def preimport(self) -> None:
        if _webhook_enabled(self._settings):
            # Preload aiogram (~3 s: it builds every Telegram type's schema on import) before
            # accepting traffic. Cloud Run gives full CPU at startup but throttles it after a
            # response, so a background import could stall on an instance kept warm by pings.
            started = time.perf_counter()
            await asyncio.to_thread(importlib.import_module, "tristhana.bots.telegram.router")
            log.info("aiogram imported in %.0f ms", (time.perf_counter() - started) * 1000)

    @asynccontextmanager
    async def lifespan(self) -> AsyncGenerator[None]:
        polling: asyncio.Task[None] | None = None
        if _webhook_enabled(self._settings):
            self.get()  # build the runtime now that aiogram is imported
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
