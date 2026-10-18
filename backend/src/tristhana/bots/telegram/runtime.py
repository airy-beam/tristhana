"""aiogram runtime, built once per process (preloaded at startup when the webhook is on).

This module itself doesn't import aiogram at import time, so `/health`-only paths stay light.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from tristhana.application.ports.i18n import Translator
from tristhana.application.start import StartUseCase

if TYPE_CHECKING:
    from aiogram import Bot, Dispatcher
    from aiogram.methods import TelegramMethod


@dataclass(frozen=True, slots=True)
class BotRuntime:
    bot: Bot
    dispatcher: Dispatcher


def build_runtime(token: str, start: StartUseCase, translator: Translator) -> BotRuntime:
    """No network: `Bot()` only validates the token format."""
    from aiogram import Bot, Dispatcher

    from tristhana.bots.telegram.router import build_router

    dispatcher = Dispatcher()
    dispatcher.include_router(build_router(start, translator))
    return BotRuntime(bot=Bot(token), dispatcher=dispatcher)


def webhook_reply(runtime: BotRuntime, method: TelegramMethod[Any]) -> dict[str, Any]:
    """The Bot API call as a webhook-reply JSON body (`{"method": ..., params...}`)."""
    body: dict[str, Any] = {"method": method.__api_method__}
    files: dict[str, Any] = {}
    for key, value in method.model_dump(warnings=False).items():
        # _dumps_json=False: native JSON values (aiogram's default stringifies for form posts);
        # bot defaults such as parse_mode are resolved here.
        prepared = runtime.bot.session.prepare_value(
            value, bot=runtime.bot, files=files, _dumps_json=False
        )
        if prepared is not None:
            body[key] = prepared
    if files:
        raise ValueError("file uploads cannot be sent as a webhook reply")
    return body
