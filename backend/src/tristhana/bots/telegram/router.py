"""Handlers: Telegram update → use case → localized reply. No business logic here.

Handlers return an unexecuted Bot API method: in webhook mode it becomes the HTTP response
(webhook reply, ADR-0012); in polling mode aiogram executes it. `account` is injected by
`AccountMiddleware` (ID-01), so every reply uses the account's locale.
"""

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.filters import Command, CommandStart
from aiogram.methods import SendMessage
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo

from tristhana.application.accounts import EnsureAccount
from tristhana.application.ports.i18n import Translator
from tristhana.bots.telegram.middleware import AccountMiddleware
from tristhana.domain.accounts import Account


def build_router(ensure: EnsureAccount, translator: Translator, miniapp_url: str = "") -> Router:
    router = Router(name="tristhana")
    router.message.filter(F.chat.type == ChatType.PRIVATE)
    router.callback_query.filter(F.message.chat.type == ChatType.PRIVATE)
    accounts = AccountMiddleware(ensure, translator)
    router.message.middleware(accounts)
    router.callback_query.middleware(accounts)

    @router.message(CommandStart())
    async def on_start(message: Message, account: Account) -> SendMessage:  # pyright: ignore[reportUnusedFunction]
        text = translator.t(account.locale, "start-greeting")
        if not miniapp_url:
            return message.answer(text)
        button = InlineKeyboardButton(
            text=translator.t(account.locale, "start-open-app"), web_app=WebAppInfo(url=miniapp_url)
        )
        return message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[button]]))

    @router.message(Command("help"))
    async def on_help(message: Message, account: Account) -> SendMessage:  # pyright: ignore[reportUnusedFunction]
        return message.answer(translator.t(account.locale, "help-text"))

    @router.message(F.text)
    async def on_other(message: Message, account: Account) -> SendMessage:  # pyright: ignore[reportUnusedFunction]
        return message.answer(translator.t(account.locale, "fallback-text"))

    return router
