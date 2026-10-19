"""Shared pieces of the inline-keyboard screens (days, practice details)."""

import asyncio
import logging
from collections.abc import Awaitable
from dataclasses import dataclass
from datetime import date, timedelta

from aiogram.methods import EditMessageText, SendMessage
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    WebAppInfo,
)

from tristhana.application.ports.i18n import DateArg, Translator
from tristhana.domain.locale import Locale

log = logging.getLogger(__name__)

type Reply = SendMessage | EditMessageText


@dataclass(frozen=True, slots=True)
class Screen:
    text: str
    markup: InlineKeyboardMarkup


def button(
    t: Translator, locale: Locale, key: str, data: str, mark: bool = False
) -> InlineKeyboardButton:
    text = t.t(locale, key)
    return InlineKeyboardButton(text=f"✓ {text}" if mark else text, callback_data=data)


def app_button(t: Translator, locale: Locale, url: str) -> InlineKeyboardButton:
    """Opens the Mini App (which also records the device time zone, ID-01)."""
    return InlineKeyboardButton(text=t.t(locale, "start-open-app"), web_app=WebAppInfo(url=url))


def day_label(t: Translator, locale: Locale, day: date, today: date) -> str:
    rel = "today" if day == today else "yesterday" if day == today - timedelta(1) else "other"
    return t.t(locale, "day-label", rel=rel, date=DateArg(day, with_year=day.year != today.year))


async def answered[T](callback: CallbackQuery, work: Awaitable[T]) -> T:
    """Run `work` while answering the callback in parallel (stops the spinner); both are
    awaited before the webhook response, since Cloud Run throttles the CPU afterwards."""
    answering = asyncio.ensure_future(_answer(callback))
    try:
        return await work
    finally:
        await answering


async def _answer(callback: CallbackQuery) -> None:
    try:
        await callback.answer()
    except Exception as e:  # the edit still goes out; a spinner is not worth a failure
        log.warning("answerCallbackQuery failed: %s", type(e).__name__)


def show(callback: CallbackQuery, screen: Screen) -> Reply:
    message = callback.message
    if isinstance(message, Message):
        return message.edit_text(screen.text, reply_markup=screen.markup)
    # Too old to edit (InaccessibleMessage): send the screen as a new message.
    return SendMessage(chat_id=callback.from_user.id, text=screen.text, reply_markup=screen.markup)
