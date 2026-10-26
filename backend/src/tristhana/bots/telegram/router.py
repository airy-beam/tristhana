"""Handlers: Telegram update → use case → localized reply. No business logic here.

Handlers return an unexecuted Bot API method: in webhook mode it becomes the HTTP response
(webhook reply, ADR-0012); in polling mode aiogram executes it. `account` is injected by
`AccountMiddleware` (ID-01), so every reply uses the account's locale.
"""

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.filters import Command
from aiogram.methods import AnswerCallbackQuery, SendMessage
from aiogram.types import (
    CallbackQuery,
    Message,
)

from tristhana.application.accounts import EnsureAccount
from tristhana.application.ports.i18n import Translator
from tristhana.bots.telegram import days as day_screens
from tristhana.bots.telegram.middleware import AccountMiddleware
from tristhana.bots.telegram.moon import register_moon
from tristhana.bots.telegram.remind import register_remind
from tristhana.bots.telegram.rest import register_rest
from tristhana.bots.telegram.runtime import (
    DayUseCases,
    MoonUseCases,
    PracticeUseCases,
    RemindUseCases,
    RestUseCases,
    SettingsUseCases,
)
from tristhana.bots.telegram.settings import register_settings
from tristhana.bots.telegram.start import register_start
from tristhana.domain.accounts import Account


def build_router(
    ensure: EnsureAccount,
    days: DayUseCases,
    practices: PracticeUseCases,
    moon: MoonUseCases,
    remind: RemindUseCases,
    settings: SettingsUseCases,
    translator: Translator,
    miniapp_url: str = "",
    rest: RestUseCases | None = None,
) -> Router:
    router = Router(name="tristhana")
    router.message.filter(F.chat.type == ChatType.PRIVATE)
    router.callback_query.filter(F.message.chat.type == ChatType.PRIVATE)
    accounts = AccountMiddleware(ensure, translator)
    router.message.middleware(accounts)
    router.callback_query.middleware(accounts)

    @router.message(Command("help"))
    async def on_help(message: Message, account: Account) -> SendMessage:  # pyright: ignore[reportUnusedFunction]
        return message.answer(translator.t(account.locale, "help-text"))

    screens = day_screens.register(router, days, practices, translator, remind, miniapp_url)
    register_start(router, screens, settings, translator, miniapp_url)
    register_moon(router, moon, translator)
    remind_screens = register_remind(router, remind, screens, translator, rest)
    if rest is not None:  # WH-01 rest periods (always wired by the app)
        register_rest(router, rest, remind, screens, remind_screens, translator)
    register_settings(router, settings, translator, miniapp_url)

    @router.callback_query()
    async def on_unknown_callback(callback: CallbackQuery) -> AnswerCallbackQuery:  # pyright: ignore[reportUnusedFunction]
        return callback.answer()  # an old or unknown keyboard: stop the spinner, do nothing

    @router.message(F.text)
    async def on_other(message: Message, account: Account) -> SendMessage:  # pyright: ignore[reportUnusedFunction]
        return message.answer(translator.t(account.locale, "fallback-text"))

    return router
