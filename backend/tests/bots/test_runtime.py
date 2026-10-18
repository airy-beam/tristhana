"""Webhook-reply serialization: native JSON, bot defaults resolved, no file uploads."""

import pytest
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.methods import SendMessage, SendPhoto
from aiogram.types import BufferedInputFile, InlineKeyboardButton, InlineKeyboardMarkup

from tests.fakes import FixedClock, InMemoryAccounts, day_use_cases
from tristhana.application.accounts import EnsureAccount
from tristhana.bots.telegram.runtime import BotRuntime, build_runtime, webhook_reply
from tristhana.infrastructure.i18n.fluent import FluentTranslator

TOKEN = "123456:TEST-token-for-unit-tests-only_xxxxxxxxxxx"


def _runtime(**defaults: object) -> BotRuntime:
    runtime = build_runtime(
        TOKEN, EnsureAccount(InMemoryAccounts(), FixedClock()), day_use_cases(), FluentTranslator()
    )
    if defaults:
        bot = Bot(TOKEN, default=DefaultBotProperties(**defaults))  # type: ignore[arg-type]
        return BotRuntime(bot=bot, dispatcher=runtime.dispatcher)
    return runtime


def test_reply_markup_is_a_json_object() -> None:
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Log", callback_data="pl:t")]]
    )

    body = webhook_reply(_runtime(), SendMessage(chat_id=1, text="hi", reply_markup=keyboard))

    assert body["method"] == "sendMessage"
    assert body["chat_id"] == 1
    assert body["reply_markup"] == {"inline_keyboard": [[{"text": "Log", "callback_data": "pl:t"}]]}
    assert "entities" not in body  # None values are dropped


def test_bot_defaults_are_resolved() -> None:
    runtime = _runtime(parse_mode="HTML", link_preview_is_disabled=True)

    body = webhook_reply(runtime, SendMessage(chat_id=1, text="<b>hi</b>"))

    assert body["parse_mode"] == "HTML"
    assert body["link_preview_options"] == {"is_disabled": True}


def test_file_uploads_cannot_be_webhook_replies() -> None:
    photo = SendPhoto(chat_id=1, photo=BufferedInputFile(b"\x89PNG", filename="a.png"))

    with pytest.raises(ValueError, match="file uploads"):
        webhook_reply(_runtime(), photo)
