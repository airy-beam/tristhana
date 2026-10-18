"""Handlers: Telegram update → use case → localized reply. No business logic here.

Handlers return an unexecuted Bot API method: in webhook mode it becomes the HTTP response
(webhook reply, ADR-0012); in polling mode aiogram executes it. `account` is injected by
`AccountMiddleware` (ID-01), so every reply uses the account's locale.
"""

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.filters import Command, CommandStart
from aiogram.methods import AnswerCallbackQuery, SendMessage
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    WebAppInfo,
)

from tristhana.application.accounts import EnsureAccount
from tristhana.application.ports.i18n import Translator
from tristhana.bots.telegram import days as day_screens
from tristhana.bots.telegram.middleware import AccountMiddleware
from tristhana.bots.telegram.runtime import DayUseCases, PracticeUseCases
from tristhana.domain.accounts import Account


def build_router(
    ensure: EnsureAccount,
    days: DayUseCases,
    practices: PracticeUseCases,
    translator: Translator,
    miniapp_url: str = "",
) -> Router:
    router = Router(name="tristhana")
    router.message.filter(F.chat.type == ChatType.PRIVATE)
    router.callback_query.filter(F.message.chat.type == ChatType.PRIVATE)
    accounts = AccountMiddleware(ensure, translator)
    router.message.middleware(accounts)
    router.callback_query.middleware(accounts)

    @router.message(CommandStart())
    async def on_start(message: Message, account: Account) -> SendMessage:  # pyright: ignore[reportUnusedFunction]
        text = translator.t(account.locale, "start-greeting")
        rows = [[day_screens.log_today_button(translator, account.locale)]]
        if miniapp_url:
            app = InlineKeyboardButton(
                text=translator.t(account.locale, "start-open-app"),
                web_app=WebAppInfo(url=miniapp_url),
            )
            rows.append([app])
        return message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))

    @router.message(Command("help"))
    async def on_help(message: Message, account: Account) -> SendMessage:  # pyright: ignore[reportUnusedFunction]
        return message.answer(translator.t(account.locale, "help-text"))

    day_screens.register(router, days, practices, translator)

    @router.callback_query()
    async def on_unknown_callback(callback: CallbackQuery) -> AnswerCallbackQuery:  # pyright: ignore[reportUnusedFunction]
        return callback.answer()  # an old or unknown keyboard: stop the spinner, do nothing

    @router.message(F.text)
    async def on_other(message: Message, account: Account) -> SendMessage:  # pyright: ignore[reportUnusedFunction]
        return message.answer(translator.t(account.locale, "fallback-text"))

    return router
