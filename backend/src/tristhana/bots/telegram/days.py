"""Day-status screens (PR-01, PR-04): `/log`, the status picker, the week picker.

Every tap edits the same message (the webhook reply, ADR-0012) and answers the callback in
parallel. One DB statement per tap besides the account lookup.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import date, timedelta

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.methods import EditMessageText, SendMessage
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from tristhana.application.policies import Principal
from tristhana.application.ports.i18n import DateArg, Translator
from tristhana.bots.telegram.callbacks import PREFIX, DayCallback, decode, encode
from tristhana.bots.telegram.runtime import DayUseCases
from tristhana.domain.accounts import Account
from tristhana.domain.days import MIN_LOG_DATE, DateInFuture, DateTooEarly, DayStatus
from tristhana.domain.locale import Locale

log = logging.getLogger(__name__)

WEEK = 7
# Grid order: Practiced alone on top; "No practice" last, next to Travel (ashtanga-expert).
_GRID: tuple[tuple[DayStatus, ...], ...] = (
    (DayStatus.PRACTICED,),
    (DayStatus.REST, DayStatus.MOON),
    (DayStatus.LADIES, DayStatus.SICK),
    (DayStatus.TRAVEL, DayStatus.SKIPPED),
)
# The week picker is glanceable in chat history, so a ladies' holiday shows as rest there.
_WEEK_EMOJI: dict[DayStatus | None, str] = {
    DayStatus.PRACTICED: "🧘",
    DayStatus.REST: "😌",
    DayStatus.MOON: "🌙",
    DayStatus.LADIES: "😌",
    DayStatus.SICK: "🤒",
    DayStatus.TRAVEL: "✈️",
    DayStatus.SKIPPED: "🌱",
}

type Reply = SendMessage | EditMessageText


@dataclass(frozen=True, slots=True)
class Screen:
    text: str
    markup: InlineKeyboardMarkup


def register(router: Router, days: DayUseCases, translator: Translator) -> None:
    screens = _Screens(days, translator)

    @router.message(Command("log"))
    async def on_log(message: Message, account: Account) -> SendMessage:  # pyright: ignore[reportUnusedFunction]
        screen = await screens.status(Principal(account), None)
        return message.answer(screen.text, reply_markup=screen.markup)

    @router.callback_query(F.data.startswith(f"{PREFIX}:"))
    async def on_day(callback: CallbackQuery, account: Account) -> Reply | None:  # pyright: ignore[reportUnusedFunction]
        cb = decode(callback.data)
        # Answer first, in parallel with the work; awaited before the webhook response,
        # since Cloud Run throttles the CPU afterwards.
        answering = asyncio.ensure_future(_answer(callback))
        try:
            screen = await screens.handle(Principal(account), cb) if cb else None
        finally:
            await answering
        if screen is None:
            return None
        if cb is not None and cb.action == "today":
            # "Log today" sits under the /start greeting: keep that message (and its "Open
            # the app" button) and start a new one.
            return SendMessage(
                chat_id=callback.from_user.id, text=screen.text, reply_markup=screen.markup
            )
        return _show(callback, screen)


async def _answer(callback: CallbackQuery) -> None:
    try:
        await callback.answer()
    except Exception as e:  # the edit still goes out; a spinner is not worth a failure
        log.warning("answerCallbackQuery failed: %s", type(e).__name__)


def _show(callback: CallbackQuery, screen: Screen) -> Reply:
    message = callback.message
    if isinstance(message, Message):
        return message.edit_text(screen.text, reply_markup=screen.markup)
    # Too old to edit (InaccessibleMessage): send the screen as a new message.
    return SendMessage(chat_id=callback.from_user.id, text=screen.text, reply_markup=screen.markup)


class _Screens:
    def __init__(self, days: DayUseCases, translator: Translator) -> None:
        self._days = days
        self._t = translator

    async def handle(self, principal: Principal, cb: DayCallback) -> Screen:
        match cb.action, cb.day, cb.status:
            case "set", date() as day, DayStatus() as status:
                return await self.saved(principal, day, status)
            case "clear", date() as day, _:
                await self._days.clear.execute(principal, day)
                return await self.status(principal, day, note="log-cleared", known=True)
            case "week", date() as day, _:
                return await self.week(principal, day)
            case "open", date() as day, _:
                return await self.status(principal, day)
            case _:
                return await self.status(principal, None)

    async def status(
        self, principal: Principal, day: date | None, note: str | None = None, known: bool = False
    ) -> Screen:
        """The picker for one day (today when `day` is None), with ✓ on the current status.
        `known`: the day is known to be empty (just cleared), so skip reading it back."""
        today, _ = self._days.get.today(principal)
        day = day or today
        current = None
        if not known:
            view = await self._days.get.execute(principal, day, day)
            current = view.days[0].status if view.days else None
        locale = principal.account.locale
        label = self._day(locale, day, today)
        text = self._t.t(locale, "log-prompt", day=label)
        if note:
            text = self._t.t(locale, note, day=label) + "\n\n" + text
        rows = [[self._status_button(locale, day, s, current) for s in row] for row in _GRID]
        last = [self._button(locale, "log-another-day", DayCallback("week", today))]
        if current is not None:
            last.append(self._button(locale, "log-clear", DayCallback("clear", day)))
        return Screen(text, InlineKeyboardMarkup(inline_keyboard=[*rows, last]))

    async def saved(self, principal: Principal, day: date, status: DayStatus) -> Screen:
        locale = principal.account.locale
        today, zone_known = self._days.get.today(principal)
        try:
            await self._days.set.execute(principal, day, status)
        except DateInFuture:  # a stale keyboard after a zone change, or a forged tap
            return await self.week(principal, today, note="log-date-future")
        except DateTooEarly:
            return await self.week(principal, today, note="log-date-too-early")
        label = self._t.t(locale, f"status-{status.value}")
        lines = [
            self._t.t(
                locale,
                "log-saved",
                day=self._day(locale, day, today),
                label=label,
                status=status.value,
            )
        ]
        if status is DayStatus.LADIES:
            lines.append(self._t.t(locale, "log-private-note"))
        if not zone_known:
            lines.append(self._t.t(locale, "log-zone-hint"))
        markup = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    self._button(locale, "log-change", DayCallback("open", day)),
                    self._button(locale, "log-another-day", DayCallback("week", today)),
                ]
            ]
        )
        return Screen("\n\n".join(lines), markup)

    async def week(self, principal: Principal, end: date, note: str | None = None) -> Screen:
        today, _ = self._days.get.today(principal)
        end = min(end, today)
        start = max(end - timedelta(days=WEEK - 1), MIN_LOG_DATE)
        view = await self._days.get.execute(principal, start, end)
        logged = {d.local_date: d.status for d in view.days}
        locale = principal.account.locale
        text = self._t.t(locale, "log-pick-day")
        if note:
            text = self._t.t(locale, note) + "\n\n" + text
        return Screen(text, self._week_markup(locale, end, logged, today))

    def _week_markup(
        self, locale: Locale, end: date, logged: dict[date, DayStatus], today: date
    ) -> InlineKeyboardMarkup:
        days = [end - timedelta(days=i) for i in range(WEEK)]  # newest first
        days = [d for d in days if d >= MIN_LOG_DATE]
        buttons = [
            InlineKeyboardButton(
                text=f"{_WEEK_EMOJI.get(logged.get(d), '·')} {self._day(locale, d, today)}",
                callback_data=encode(DayCallback("open", d)),
            )
            for d in days
        ]
        rows = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
        earlier = end - timedelta(days=WEEK)
        paging: list[InlineKeyboardButton] = []
        if earlier >= MIN_LOG_DATE:
            paging.append(self._button(locale, "log-earlier", DayCallback("week", earlier)))
        if end < today:
            later = min(end + timedelta(days=WEEK), today)
            paging.append(self._button(locale, "log-later", DayCallback("week", later)))
        return InlineKeyboardMarkup(inline_keyboard=[*rows, paging] if paging else rows)

    def _status_button(
        self, locale: Locale, day: date, status: DayStatus, current: DayStatus | None
    ) -> InlineKeyboardButton:
        text = self._t.t(locale, f"status-{status.value}")
        return InlineKeyboardButton(
            text=f"✓ {text}" if status is current else text,
            callback_data=encode(DayCallback("set", day, status)),
        )

    def _button(self, locale: Locale, key: str, cb: DayCallback) -> InlineKeyboardButton:
        return InlineKeyboardButton(text=self._t.t(locale, key), callback_data=encode(cb))

    def _day(self, locale: Locale, day: date, today: date) -> str:
        rel = "today" if day == today else "yesterday" if day == today - timedelta(1) else "other"
        return self._t.t(
            locale, "day-label", rel=rel, date=DateArg(day, with_year=day.year != today.year)
        )


def log_today_button(translator: Translator, locale: Locale) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text=translator.t(locale, "start-log-today"), callback_data=encode(DayCallback("today"))
    )
