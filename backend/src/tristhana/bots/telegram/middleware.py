"""Resolves the sender's account before a handler runs (ID-01): the first contact creates it.

An inner middleware, so it runs only after a handler's filters matched: group chats and
unhandled updates cost no DB round trip.
"""

from collections.abc import Awaitable, Callable
from contextlib import suppress
from typing import Any, override

from aiogram import BaseMiddleware
from aiogram.methods import SendMessage
from aiogram.types import CallbackQuery, Message, TelegramObject

from tristhana.application.accounts import EnsureAccount
from tristhana.application.ports.export import AccountGone
from tristhana.application.ports.i18n import Translator
from tristhana.application.ports.storage import StorageUnavailable
from tristhana.domain.accounts import ExternalProfile, IdentityKey, IdentityProvider
from tristhana.domain.locale import negotiate_locale

type Handler = Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]]


class AccountMiddleware(BaseMiddleware):
    """Puts `account` into the handler data; a down database gets a gentle retry message,
    whether it fails before the account loads or later, inside any handler (Q48)."""

    def __init__(self, ensure: EnsureAccount, translator: Translator) -> None:
        self._ensure = ensure
        self._translator = translator

    @override
    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        if not isinstance(event, Message | CallbackQuery):
            return await handler(event, data)
        user = event.from_user
        if user is None or user.is_bot:
            return None  # channel posts, anonymous admins: nobody to create an account for
        key = IdentityKey(IdentityProvider.TELEGRAM, str(user.id))
        profile = ExternalProfile(
            key, display_name=user.first_name, language_code=user.language_code
        )
        try:
            account = data["account"] = await self._ensure.execute(profile)
        except StorageUnavailable:
            text = self._translator.t(negotiate_locale(user.language_code), "error-temporary")
            # A message gets a reply; a callback query gets its answer (a toast), as it must.
            return event.answer(text)
        try:
            return await handler(event, data)
        except StorageUnavailable:  # the account loaded, then the database went away
            text = self._translator.t(account.locale, "error-temporary")
            if isinstance(event, Message):
                return event.answer(text)
            # A new message, not a toast: most handlers answered the tap before the failure,
            # and a second answer shows nothing. The screen under the finger stays as it was.
            with suppress(Exception):  # stops the spinner if the handler had not yet
                await event.answer()
            return SendMessage(chat_id=user.id, text=text)
        except AccountGone:  # the account was deleted mid-tap (ST-09): stay silent
            if isinstance(event, CallbackQuery):
                with suppress(Exception):  # the tap may already have its answer
                    await event.answer()
            return None
