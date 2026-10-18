"""Day-status screens (PR-01, PR-04): `/log`, the status picker, the week picker.

Every tap edits the same message (the webhook reply, ADR-0012) and answers the callback in
parallel. One DB statement per tap besides the account lookup. Saving 🧘 Practiced opens
the practice-details screen (PR-02, `practice.py`).
"""

from datetime import date, timedelta

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.methods import SendMessage
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from tristhana.application.policies import Principal
from tristhana.application.ports.i18n import Translator
from tristhana.bots.telegram import practice_callbacks as pcb
from tristhana.bots.telegram.callbacks import PREFIX, DayCallback, decode, encode
from tristhana.bots.telegram.practice import PracticeScreens, register_practice
from tristhana.bots.telegram.runtime import DayUseCases, PracticeUseCases
from tristhana.bots.telegram.screens import Reply, Screen, answered, day_label, show
from tristhana.domain.accounts import Account
from tristhana.domain.days import MIN_LOG_DATE, DateInFuture, DateTooEarly, DayStatus
from tristhana.domain.locale import Locale

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


def register(
    router: Router, days: DayUseCases, practices: PracticeUseCases, translator: Translator
) -> None:
    screens = DayScreens(days, translator)
    screens.practice = PracticeScreens(days, practices, translator, screens)
    register_practice(router, screens.practice)

    @router.message(Command("log"))
    async def on_log(message: Message, account: Account) -> SendMessage:  # pyright: ignore[reportUnusedFunction]
        screen = await screens.status(Principal(account), None)
        return message.answer(screen.text, reply_markup=screen.markup)

    @router.callback_query(F.data.startswith(f"{PREFIX}:"))
    async def on_day(callback: CallbackQuery, account: Account) -> Reply | None:  # pyright: ignore[reportUnusedFunction]
        cb = decode(callback.data)
        if cb is None:
            await answered(callback, _nothing())
            return None
        screen = await answered(callback, screens.handle(Principal(account), cb))
        if cb.action == "today":
            # "Log today" sits under the /start greeting: keep that message (and its "Open
            # the app" button) and start a new one.
            return SendMessage(
                chat_id=callback.from_user.id, text=screen.text, reply_markup=screen.markup
            )
        return show(callback, screen)


async def _nothing() -> None:
    return None


class DayScreens:
    def __init__(self, days: DayUseCases, translator: Translator) -> None:
        self._days = days
        self._t = translator
        self.practice: PracticeScreens | None = None  # set by `register`

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
        label = self.day(locale, day, today)
        text = self._t.t(locale, "log-prompt", day=label)
        if note:
            text = self._t.t(locale, note, day=label) + "\n\n" + text
        rows = [[self._status_button(locale, day, s, current) for s in row] for row in _GRID]
        last = [self._button(locale, "log-another-day", encode(DayCallback("week", today)))]
        if current is DayStatus.PRACTICED:
            last.insert(0, self._button(locale, "practice-details", _details(day)))
        if current is not None:
            last.append(self._button(locale, "log-clear", encode(DayCallback("clear", day))))
        return Screen(text, InlineKeyboardMarkup(inline_keyboard=[*rows, last]))

    async def saved(self, principal: Principal, day: date, status: DayStatus) -> Screen:
        today, _ = self._days.get.today(principal)
        try:
            await self._days.set.execute(principal, day, status)
        except DateInFuture:  # a stale keyboard after a zone change, or a forged tap
            return await self.week(principal, today, note="log-date-future")
        except DateTooEarly:
            return await self.week(principal, today, note="log-date-too-early")
        if status is DayStatus.PRACTICED and self.practice is not None:
            return await self.practice.details(principal, day)
        locale = principal.account.locale
        markup = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    self._button(locale, "log-change", _open(day)),
                    self._button(locale, "log-another-day", encode(DayCallback("week", today))),
                ]
            ]
        )
        return Screen("\n\n".join(self.saved_lines(principal, day, status)), markup)

    def saved_lines(self, principal: Principal, day: date, status: DayStatus) -> list[str]:
        """ "✓ Today, Sun, Oct 18: 🧘 Practiced" + the cheer, privacy note, zone hint."""
        locale = principal.account.locale
        today, zone_known = self._days.get.today(principal)
        label = self._t.t(locale, f"status-{status.value}")
        lines = [
            self._t.t(
                locale,
                "log-saved",
                day=self.day(locale, day, today),
                label=label,
                status=status.value,
            )
        ]
        if status is DayStatus.LADIES:
            lines.append(self._t.t(locale, "log-private-note"))
        if not zone_known:
            lines.append(self._t.t(locale, "log-zone-hint"))
        return lines

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
                text=f"{_WEEK_EMOJI.get(logged.get(d), '·')} {self.day(locale, d, today)}",
                callback_data=_open(d),
            )
            for d in days
        ]
        rows = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
        earlier = end - timedelta(days=WEEK)
        paging: list[InlineKeyboardButton] = []
        if earlier >= MIN_LOG_DATE:
            paging.append(self._button(locale, "log-earlier", encode(DayCallback("week", earlier))))
        if end < today:
            later = min(end + timedelta(days=WEEK), today)
            paging.append(self._button(locale, "log-later", encode(DayCallback("week", later))))
        return InlineKeyboardMarkup(inline_keyboard=[*rows, paging] if paging else rows)

    def _status_button(
        self, locale: Locale, day: date, status: DayStatus, current: DayStatus | None
    ) -> InlineKeyboardButton:
        text = self._t.t(locale, f"status-{status.value}")
        return InlineKeyboardButton(
            text=f"✓ {text}" if status is current else text,
            callback_data=encode(DayCallback("set", day, status)),
        )

    def _button(self, locale: Locale, key: str, data: str) -> InlineKeyboardButton:
        return InlineKeyboardButton(text=self._t.t(locale, key), callback_data=data)

    def day(self, locale: Locale, day: date, today: date) -> str:
        return day_label(self._t, locale, day, today)


def _open(day: date) -> str:
    return encode(DayCallback("open", day))


def _details(day: date) -> str:
    return pcb.encode(pcb.PracticeCallback("open", day))


def log_today_button(translator: Translator, locale: Locale) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text=translator.t(locale, "start-log-today"), callback_data=encode(DayCallback("today"))
    )
