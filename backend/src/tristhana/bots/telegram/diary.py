"""Diary-note screens (PR-07, ADR-0025): the note screen N, the confirm step before removing,
and writing by replying to a ForceReply prompt. The prompt's first line is a fixed token
(`📓 YYYY-MM-DD`): a reply to our own prompt saves to that date, always for the sender's own
account. The note text is never echoed back, and N shows no status (a 🌸 stays private).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, Any

from aiogram import F, Router
from aiogram.filters import Filter
from aiogram.methods import SendMessage
from aiogram.types import (
    CallbackQuery,
    ForceReply,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from tristhana.application.policies import Principal
from tristhana.application.ports.i18n import DateArg, Translator
from tristhana.application.ports.storage import StorageUnavailable
from tristhana.bots.telegram.diary_callbacks import PREFIX, DiaryCallback, Origin, decode, encode
from tristhana.bots.telegram.screens import Reply, Screen, answered, button, show
from tristhana.domain.accounts import Account
from tristhana.domain.days import DateInFuture, DateTooEarly
from tristhana.domain.diary import MAX_CHARS, DiaryNote, NoteTooLong
from tristhana.domain.locale import Locale

if TYPE_CHECKING:
    from tristhana.bots.telegram.check_in import CheckInScreens
    from tristhana.bots.telegram.days import DayScreens
    from tristhana.bots.telegram.runtime import DiaryUseCases

PREVIEW_CHARS = 100
# Line 1 of our prompt: the only thing a reply is matched on (ISO, locale-independent).
_TOKEN = re.compile(r"\A📓 (\d{4}-\d{2}-\d{2})\n")


def register_diary(router: Router, screens: DiaryScreens) -> None:
    @router.callback_query(F.data.startswith(f"{PREFIX}:"))
    async def on_diary(callback: CallbackQuery, account: Account) -> Reply | None:  # pyright: ignore[reportUnusedFunction]
        cb = decode(callback.data)
        try:
            reply = await answered(callback, screens.handle(Principal(account), cb))
        except StorageUnavailable:  # the account loaded, then the database went away
            text = screens.t.t(account.locale, "error-temporary")
            return SendMessage(chat_id=callback.from_user.id, text=text)
        if isinstance(reply, Prompt):  # ForceReply can't go on an edit: a new message
            return SendMessage(
                chat_id=callback.from_user.id, text=reply.text, reply_markup=reply.markup
            )
        return show(callback, reply) if reply else None


class _ToPrompt(Filter):
    """Matches a reply to our own write prompt and hands its date to the handler."""

    async def __call__(self, message: Message) -> bool | dict[str, Any]:
        day = prompt_date(message)
        return False if day is None else {"day": day}


def register_diary_reply(router: Router, screens: DiaryScreens) -> None:
    """Register **last**, just before the fallback: commands (also sent as a reply, since
    ForceReply keeps the field in reply mode) and other replies reach their own handlers."""

    @router.message(_ToPrompt(), ~F.text.startswith("/"))
    async def on_reply(message: Message, account: Account, day: date) -> SendMessage:  # pyright: ignore[reportUnusedFunction]
        locale = account.locale
        if message.text is None:  # voice, photo, sticker, a caption
            return message.answer(screens.t.t(locale, "diary-text-only"))
        try:
            screen = await screens.save(Principal(account), day, message.text)
        except StorageUnavailable:
            return message.answer(screens.t.t(locale, "error-temporary"))
        return message.answer(screen.text, reply_markup=screen.markup)


def prompt_date(message: Message) -> date | None:
    """The date of our own prompt this message replies to, or None."""
    target = message.reply_to_message
    bot = message.bot
    if target is None or bot is None or target.from_user is None:
        return None
    if target.from_user.id != bot.id or target.text is None:
        return None
    found = _TOKEN.match(target.text)
    if found is None:
        return None
    try:
        return date.fromisoformat(found.group(1))
    except ValueError:
        return None


@dataclass(frozen=True, slots=True)
class Prompt:
    """The write prompt: sent as a new message with ForceReply (not an inline screen)."""

    text: str
    markup: ForceReply


def preview(t: Translator, locale: Locale, note: DiaryNote | None) -> str | None:
    """The picker's one line: the first 100 characters; none when absent or unreadable."""
    if note is None or note.text is None:
        return None
    text = note.text if len(note.text) <= PREVIEW_CHARS else note.text[:PREVIEW_CHARS] + "…"
    return t.t(locale, "diary-preview", text=text)


def note_button(t: Translator, locale: Locale, day: date, origin: Origin) -> InlineKeyboardButton:
    return button(t, locale, "diary-button", encode(DiaryCallback("open", day, origin)))


class DiaryScreens:
    def __init__(
        self,
        diary: DiaryUseCases,
        translator: Translator,
        day_screens: DayScreens,
        check_in: CheckInScreens | None = None,
    ) -> None:
        self._d = diary
        self.t = translator
        self._days = day_screens
        self._check_in = check_in

    async def handle(
        self, principal: Principal, cb: DiaryCallback | None
    ) -> Screen | Prompt | None:
        if cb is None:
            return None
        day, origin = cb.day, cb.origin
        try:
            match cb.action:
                case "open":
                    note = await self._d.get.execute(principal, day)
                    return self.note(principal, day, origin, note)
                case "write" | "rewrite":
                    return self.prompt(principal, day, rewrite=cb.action == "rewrite")
                case "confirm":
                    return self.confirm(principal, day, origin)
                case "clear":
                    await self._d.clear.execute(principal, day)
                    return self.note(principal, day, origin, None, removed=True)
                case "back":
                    return await self._back(principal, day, origin)
        except DateInFuture:
            today, _ = self._days.today(principal)
            return await self._days.week(principal, today, note="log-date-future")
        except DateTooEarly:
            today, _ = self._days.today(principal)
            return await self._days.week(principal, today, note="log-date-too-early")

    async def _back(self, principal: Principal, day: date, origin: Origin) -> Screen:
        if origin == "k" and self._check_in is not None:
            from tristhana.bots.telegram.check_in_callbacks import CheckInCallback

            screen = await self._check_in.handle(principal, CheckInCallback("open", day))
            if screen is not None:
                return screen
        return await self._days.status(principal, day)

    def _label(self, locale: Locale, principal: Principal, day: date) -> str:
        """📓 + the date only: N stays in the chat, so it never names the status."""
        today, _ = self._days.today(principal)
        return self.t.t(locale, "diary-preview", text=self._days.day(locale, day, today))

    # Screen N.
    def note(
        self,
        principal: Principal,
        day: date,
        origin: Origin,
        note: DiaryNote | None,
        removed: bool = False,
    ) -> Screen:
        locale = principal.account.locale
        lines = [self._label(locale, principal, day)]
        if removed:
            lines.append(self.t.t(locale, "diary-removed"))
        elif note is None:
            lines.append(self.t.t(locale, "diary-empty"))
        elif note.text is None:
            lines.append(self.t.t(locale, "diary-unreadable"))
        else:
            lines.append(note.text)
        return Screen("\n\n".join(lines), self._rows(locale, day, origin, note is not None))

    def _rows(
        self, locale: Locale, day: date, origin: Origin, exists: bool
    ) -> InlineKeyboardMarkup:
        def data(action: str) -> str:
            return encode(DiaryCallback(action, day, origin))  # type: ignore[arg-type]

        first = [
            button(
                self.t,
                locale,
                "diary-rewrite" if exists else "diary-write",
                data("rewrite" if exists else "write"),
            )
        ]
        if exists:
            first.append(button(self.t, locale, "diary-clear", data("confirm")))
        rows = [first, [button(self.t, locale, "log-back", data("back"))]]
        return InlineKeyboardMarkup(inline_keyboard=rows)

    def confirm(self, principal: Principal, day: date, origin: Origin) -> Screen:
        locale = principal.account.locale
        text = "\n\n".join(
            [self._label(locale, principal, day), self.t.t(locale, "diary-clear-confirm")]
        )
        rows = [
            [
                button(
                    self.t, locale, "diary-clear-yes", encode(DiaryCallback("clear", day, origin))
                ),
                button(self.t, locale, "log-back", encode(DiaryCallback("open", day, origin))),
            ]
        ]
        return Screen(text, InlineKeyboardMarkup(inline_keyboard=rows))

    def prompt(self, principal: Principal, day: date, rewrite: bool) -> Prompt:
        locale = principal.account.locale
        today, _ = self._days.today(principal)
        rel = "today" if day == today else "yesterday" if (today - day).days == 1 else "other"
        date_arg = DateArg(day, with_year=day.year != today.year)
        lines = [self.t.t(locale, "diary-prompt", rel=rel, date=date_arg)]
        if rewrite:
            lines.append(self.t.t(locale, "diary-prompt-replace"))
        text = f"📓 {day.isoformat()}\n" + "\n\n".join(lines)
        placeholder = self.t.t(locale, "diary-placeholder")
        return Prompt(text, ForceReply(force_reply=True, input_field_placeholder=placeholder))

    async def save(self, principal: Principal, day: date, text: str) -> Screen:
        """A reply: save (1 upsert), then a short confirmation, never the text itself."""
        locale = principal.account.locale
        try:
            saved = await self._d.save.execute(principal, day, text)
        except NoteTooLong:
            return Screen(
                self.t.t(locale, "diary-too-long", max=MAX_CHARS),
                InlineKeyboardMarkup(inline_keyboard=[]),
            )
        except DateInFuture:
            today, _ = self._days.today(principal)
            return await self._days.week(principal, today, note="log-date-future")
        except DateTooEarly:
            today, _ = self._days.today(principal)
            return await self._days.week(principal, today, note="log-date-too-early")
        if saved is None:  # blank: the note was removed
            return self.note(principal, day, "d", None, removed=True)
        return Screen(self.t.t(locale, "diary-saved"), self._rows(locale, day, "d", True))
