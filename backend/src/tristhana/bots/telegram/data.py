"""📦 My data (ST-09, ADR-0027): screen D (download / delete) under /settings, and screen X
(what deleting means, then the bound 10-minute confirm button). Handlers call the shared use
cases; the export tap is answered with "Preparing…" once the slot is claimed (a tap is
answered only once), and "too soon" is a toast with no edit."""

import logging
import math
from datetime import UTC, datetime, timedelta

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from tristhana.application.export import (
    BotUnreachable,
    ExportFailed,
    ExportTooLarge,
    ExportTooSoon,
)
from tristhana.application.policies import Principal
from tristhana.application.ports.i18n import Translator
from tristhana.application.ports.storage import StorageUnavailable
from tristhana.bots.telegram import settings_callbacks as scb
from tristhana.bots.telegram.data_callbacks import (
    CONFIRM_MINUTES,
    PREFIX,
    DataCallback,
    account_tag,
    decode,
    encode,
)
from tristhana.bots.telegram.runtime import DataUseCases
from tristhana.bots.telegram.screens import Reply, Screen, answered, button, show
from tristhana.domain.accounts import Account
from tristhana.domain.locale import Locale

log = logging.getLogger(__name__)


def register_data(router: Router, data: DataUseCases, translator: Translator) -> None:
    screens = DataScreens(data, translator)

    @router.callback_query(F.data.startswith(f"{PREFIX}:"))
    async def on_data_tap(callback: CallbackQuery, account: Account) -> Reply | None:  # pyright: ignore[reportUnusedFunction]
        cb = decode(callback.data)
        if cb is None:
            await answered(callback, _nothing())
            return None
        if cb.action == "export":
            screen = await screens.export(callback, Principal(account), cb.from_delete)
        else:
            screen = await answered(callback, screens.handle(Principal(account), cb))
        if screen is None:
            return None
        if screen.markup.inline_keyboard == [] and isinstance(callback.message, Message):
            return callback.message.edit_text(screen.text)  # delete-done: no keyboard
        return show(callback, screen)


async def _nothing() -> None:
    return None


class DataScreens:
    def __init__(self, data: DataUseCases, translator: Translator) -> None:
        self._d = data
        self._t = translator

    async def handle(self, principal: Principal, cb: DataCallback) -> Screen | None:
        locale = principal.account.locale
        match cb.action:
            case "open":
                return self.view(locale)
            case "explain":
                return self.explain(principal)
            case "delete":
                if not self._valid(principal, cb):
                    return self.explain(principal, self._t.t(locale, "delete-expired"))
                await self._d.delete.execute(principal)
                return Screen(
                    self._t.t(locale, "delete-done"), InlineKeyboardMarkup(inline_keyboard=[])
                )
            case "export":  # handled by `export` (it answers the tap itself)
                return None

    async def export(
        self, callback: CallbackQuery, principal: Principal, from_delete: bool
    ) -> Screen | None:
        locale = principal.account.locale
        answer_state = {"done": False}

        async def preparing() -> None:
            answer_state["done"] = True
            await _toast(callback, self._t.t(locale, "export-preparing"))

        def again(line: str) -> Screen:
            return self.explain(principal, line) if from_delete else self.view(locale, line)

        try:
            await self._d.export.execute(principal, preparing)
        except ExportTooSoon as e:
            minutes = max(1, math.ceil(e.wait / timedelta(minutes=1)))
            await _toast(callback, self._t.t(locale, "export-too-soon", minutes=minutes))
            return None
        except ExportTooLarge:
            return await self._after(
                callback, answer_state, again(self._t.t(locale, "export-too-large"))
            )
        except (BotUnreachable, ExportFailed, StorageUnavailable):
            return await self._after(
                callback, answer_state, again(self._t.t(locale, "error-temporary"))
            )
        return again(self._t.t(locale, "export-sent"))

    async def _after(
        self, callback: CallbackQuery, answer_state: dict[str, bool], screen: Screen
    ) -> Screen:
        if not answer_state["done"]:  # failed before the claim: the tap still needs its answer
            await _toast(callback, None)
        return screen

    def view(self, locale: Locale, line: str | None = None) -> Screen:
        """D: 0 statements."""
        text = "\n\n".join(
            part
            for part in (line, self._t.t(locale, "data-title"), self._t.t(locale, "data-intro"))
            if part
        )
        rows = [
            [button(self._t, locale, "export-button", encode(DataCallback("export")))],
            [button(self._t, locale, "delete-button", encode(DataCallback("explain")))],
            [button(self._t, locale, "settings-link", scb.encode(scb.SettingsCallback("view")))],
        ]
        return Screen(text, InlineKeyboardMarkup(inline_keyboard=rows))

    def explain(self, principal: Principal, line: str | None = None) -> Screen:
        """X: what deleting means, then the confirm button bound to this account and minute."""
        locale = principal.account.locale
        confirm = DataCallback(
            "delete", account=account_tag(principal.account.id), minute=_minute(self._d.now())
        )
        text = "\n\n".join(part for part in (line, self._t.t(locale, "delete-explain")) if part)
        rows = [
            [
                button(
                    self._t,
                    locale,
                    "delete-export-first",
                    encode(DataCallback("export", from_delete=True)),
                )
            ],
            [button(self._t, locale, "delete-confirm", encode(confirm))],
            [button(self._t, locale, "data-title", encode(DataCallback("open")))],
        ]
        return Screen(text, InlineKeyboardMarkup(inline_keyboard=rows))

    def _valid(self, principal: Principal, cb: DataCallback) -> bool:
        now = _minute(self._d.now())
        fresh = 0 <= now - cb.minute < CONFIRM_MINUTES  # never more than 10 minutes
        return fresh and cb.account == account_tag(principal.account.id)


def _minute(at: datetime) -> int:
    return int(at.astimezone(UTC).timestamp() // 60)


async def _toast(callback: CallbackQuery, text: str | None) -> None:
    try:
        await callback.answer(text)
    except Exception as e:  # the edit still goes out; a toast is not worth a failure
        log.warning("answerCallbackQuery failed: %s", type(e).__name__)
