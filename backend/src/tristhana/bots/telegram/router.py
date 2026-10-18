"""Handlers: Telegram update → use case → localized reply. No business logic here.

Handlers return an unexecuted Bot API method: in webhook mode it becomes the HTTP response
(webhook reply, ADR-0012); in polling mode aiogram executes it.
"""

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.filters import Command, CommandStart
from aiogram.methods import SendMessage
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo

from tristhana.application.ports.i18n import Translator
from tristhana.application.start import StartCommand, StartUseCase
from tristhana.domain.locale import Locale, negotiate_locale


def build_router(start: StartUseCase, translator: Translator, miniapp_url: str = "") -> Router:
    router = Router(name="tristhana")
    router.message.filter(F.chat.type == ChatType.PRIVATE)

    @router.message(CommandStart(), F.from_user)
    async def on_start(message: Message) -> SendMessage:  # pyright: ignore[reportUnusedFunction]
        user = message.from_user
        if user is None:  # excluded by the F.from_user filter
            raise ValueError("/start without a sender")
        result = await start.execute(
            StartCommand(telegram_user_id=user.id, language_code=user.language_code)
        )
        text = translator.t(result.locale, "start-greeting")
        if not miniapp_url:
            return message.answer(text)
        button = InlineKeyboardButton(
            text=translator.t(result.locale, "start-open-app"), web_app=WebAppInfo(url=miniapp_url)
        )
        return message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[button]]))

    @router.message(Command("help"))
    async def on_help(message: Message) -> SendMessage:  # pyright: ignore[reportUnusedFunction]
        return message.answer(translator.t(_locale(message), "help-text"))

    @router.message(F.text)
    async def on_other(message: Message) -> SendMessage:  # pyright: ignore[reportUnusedFunction]
        return message.answer(translator.t(_locale(message), "fallback-text"))

    return router


def _locale(message: Message) -> Locale:
    return negotiate_locale(message.from_user.language_code if message.from_user else None)
