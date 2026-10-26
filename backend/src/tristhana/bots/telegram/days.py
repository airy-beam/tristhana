"""Day-status screens (PR-01, PR-04): `/log`, the status picker, the week picker.

Every tap edits the same message (the webhook reply, ADR-0012) and answers the callback in
parallel. One DB statement per tap besides the account lookup. Saving 🧘 Practiced opens
the practice-details screen (PR-02, `practice.py`).
"""

from __future__ import annotations

from datetime import date, timedelta

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.methods import SendMessage
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from tristhana.application.days import DaysView
from tristhana.application.policies import Principal
from tristhana.application.ports.i18n import DateArg, Translator
from tristhana.bots.telegram import practice_callbacks as pcb
from tristhana.bots.telegram import rest_callbacks as acb
from tristhana.bots.telegram.callbacks import PREFIX, DayCallback, decode, encode
from tristhana.bots.telegram.practice import PracticeScreens, register_practice
from tristhana.bots.telegram.runtime import DayUseCases, PracticeUseCases, RemindUseCases
from tristhana.bots.telegram.screens import (
    Reply,
    Screen,
    answered,
    app_button,
    day_label,
    show,
)
from tristhana.domain.accounts import Account
from tristhana.domain.days import MIN_LOG_DATE, DateInFuture, DateTooEarly, DayStatus
from tristhana.domain.locale import Locale
from tristhana.domain.rest_days import AutoKind
from tristhana.domain.rest_periods import PAUSE_DAYS, RestPeriod

WEEK = 7
# Grid order: Practiced alone on top; "No practice" last, next to Travel (ashtanga-expert).
_GRID: tuple[tuple[DayStatus, ...], ...] = (
    (DayStatus.PRACTICED,),
    (DayStatus.REST, DayStatus.MOON),
    (DayStatus.LADIES, DayStatus.SICK),
    (DayStatus.TRAVEL, DayStatus.SKIPPED),
)
# "Hide the 🌸 button" (WH-01): the same order without it.
_GRID_NO_LADIES: tuple[tuple[DayStatus, ...], ...] = (
    (DayStatus.PRACTICED,),
    (DayStatus.REST, DayStatus.MOON),
    (DayStatus.SICK, DayStatus.TRAVEL),
    (DayStatus.SKIPPED,),
)
CHIPS_PER_ROW = 3
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
_AUTO_STATUS = {AutoKind.MOON: DayStatus.MOON, AutoKind.DAY_OFF: DayStatus.REST}


def register(
    router: Router,
    days: DayUseCases,
    practices: PracticeUseCases,
    translator: Translator,
    remind: RemindUseCases | None = None,
    miniapp_url: str = "",
) -> DayScreens:
    screens = DayScreens(days, translator, miniapp_url)
    screens.practice = PracticeScreens(days, practices, translator, screens, remind)
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
            # Legacy `d1:t` ("Log today" under old /start greetings still in chat history,
            # UI-01): keep that message and start a new one.
            return SendMessage(
                chat_id=callback.from_user.id, text=screen.text, reply_markup=screen.markup
            )
        return show(callback, screen)

    return screens


async def _nothing() -> None:
    return None


class DayScreens:
    def __init__(self, days: DayUseCases, translator: Translator, miniapp_url: str = "") -> None:
        self._days = days
        self._t = translator
        self.app_url = miniapp_url
        self.practice: PracticeScreens | None = None  # set by `register`

    def today(self, principal: Principal) -> tuple[date, bool]:
        return self._days.get.today(principal)

    async def read(self, principal: Principal, start: date, end: date) -> DaysView:
        return await self._days.get.execute(principal, start, end)

    async def handle(self, principal: Principal, cb: DayCallback) -> Screen:
        match cb.action, cb.day, cb.status:
            case "set", date() as day, DayStatus() as status:
                return await self.saved(principal, day, status)
            case "clear", date() as day, _:
                await self._days.clear.execute(principal, day)
                # Read back: the day may now show as auto-rest (PR-09).
                return await self.status(principal, day, note="log-cleared")
            case "week", date() as day, _:
                return await self.week(principal, day)
            case "open", date() as day, _:
                return await self.status(principal, day)
            case _:
                return await self.status(principal, None)

    async def status(
        self, principal: Principal, day: date | None, note: str | None = None
    ) -> Screen:
        """The picker for one day (today when `day` is None), with ✓ on the current status.
        An auto-rest day (PR-09) has no ✓, just a line saying why it shows as rest."""
        screen, _ = await self._picker(principal, day, note)
        return screen

    async def today_picker(self, principal: Principal) -> tuple[Screen, str | None]:
        """Today's picker and its auto-rest line (for /start, which has its own text)."""
        return await self._picker(principal, None, None)

    async def _picker(
        self, principal: Principal, day: date | None, note: str | None, lead: str | None = None
    ) -> tuple[Screen, str | None]:
        today, _ = self._days.get.today(principal)
        day = day or today
        view = await self._days.get.execute(principal, day, day)
        current = view.days[0].status if view.days else None
        locale = principal.account.locale
        label = self.day(locale, day, today)
        lines = [self._t.t(locale, note, day=label)] if note else []
        if lead:
            lines.insert(0, lead)
        auto = self.auto_line(locale, view, day)
        if auto:
            lines.append(auto)
        text = "\n\n".join([*lines, self._t.t(locale, "log-prompt", day=label)])
        shown = current or view.covered.get(day)
        rows = self.status_rows(principal, day, current, shown)
        period = view.period_on(day)
        if period is not None and period.end >= today:  # still running: it can end early
            rows.append([self.end_button(locale, period, view.practice_on)])
        last = [self._button(locale, "log-another-day", encode(DayCallback("week", today)))]
        if current is DayStatus.PRACTICED:
            last.insert(0, self._button(locale, "practice-details", _details(day)))
        if current is not None:
            last.append(self._button(locale, "log-clear", encode(DayCallback("clear", day))))
        return Screen(text, InlineKeyboardMarkup(inline_keyboard=[*rows, last])), auto

    def status_rows(
        self,
        principal: Principal,
        day: date,
        current: DayStatus | None,
        shown: DayStatus | None,
    ) -> list[list[InlineKeyboardButton]]:
        """The status grid, ✓ on the logged status; without 🌸 when the person hid it,
        unless the day shows as 🌸 (WH-01)."""
        locale = principal.account.locale
        hide = principal.account.hide_ladies and shown is not DayStatus.LADIES
        grid = _GRID_NO_LADIES if hide else _GRID
        return [[self._status_button(locale, day, s, current) for s in row] for row in grid]

    def auto_line(self, locale: Locale, view: DaysView, day: date) -> str | None:
        """ "🌙 Moon day (📍 Mysuru), a traditional rest day…" for an unlogged auto day, or
        "🤒 Sick / injury through …" for an unlogged day a rest period covers (WH-01)."""
        covered = view.covered.get(day)
        period = view.period_on(day)
        if covered is not None and period is not None:
            return self._t.t(
                locale, "log-auto-period", label=self.label(locale, covered), until=_until(period)
            )
        auto = view.auto.get(day)
        if auto is None:
            return None
        if auto.kind is AutoKind.MOON:
            dayoff = "yes" if auto.also_day_off else "no"
            return self._t.t(locale, "log-auto-moon", city=view.city.name(locale), dayoff=dayoff)
        return self._t.t(locale, "log-auto-day-off")

    async def saved(self, principal: Principal, day: date, status: DayStatus) -> Screen:
        today, _ = self._days.get.today(principal)
        try:
            saved = await self._days.set.execute(principal, day, status)
        except DateInFuture:  # a stale keyboard after a zone change, or a forged tap
            return await self.week(principal, today, note="log-date-future")
        except DateTooEarly:
            return await self.week(principal, today, note="log-date-too-early")
        if status is DayStatus.PRACTICED and self.practice is not None:
            return await self.practice.details(principal, day, cut=saved.cut)
        if saved.offer is not None:  # "for how many days?" (WH-01)
            return self.question(principal, day, status, saved.offer.reminders_on)
        if saved.period is not None:
            return self.period_saved(principal, day, status, saved.period, saved.practice_on)
        return self.saved_screen(principal, day, status)

    def question(
        self,
        principal: Principal,
        day: date,
        kind: DayStatus,
        reminders_on: bool,
        more: bool = False,
    ) -> Screen:
        """V + "for how many days?" with the kind's day counts (or its "Other…" ones). A
        pure render: Other… and Back need no DB. Ignoring it means no pause."""
        locale = principal.account.locale
        today, _ = self._days.get.today(principal)
        lines = self.saved_lines(principal, day, kind)
        lines.append(
            self._t.t(
                locale,
                "pause-ask",
                label=self.label(locale, kind),
                rel="yesterday" if day == today - timedelta(days=1) else "today",
                reminders=_on(reminders_on),
            )
        )
        first, other = PAUSE_DAYS[kind]
        chips = [
            InlineKeyboardButton(
                text=self._t.t(locale, "pause-days", n=n),
                callback_data=acb.encode(acb.RestCallback("start", day, kind, days=n)),
            )
            for n in (other if more else first)
        ]
        rows = [chips[i : i + CHIPS_PER_ROW] for i in range(0, len(chips), CHIPS_PER_ROW)]
        flip = acb.RestCallback("back" if more else "more", day, kind, reminders_on=reminders_on)
        rows.append(
            [self._button(locale, "pause-back" if more else "pause-other", acb.encode(flip))]
        )
        rows.append(self._change_row(locale, day, today))
        rows += self.app_rows(principal)
        return Screen("\n\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows))

    def period_saved(
        self,
        principal: Principal,
        day: date,
        status: DayStatus,
        period: RestPeriod,
        reminders_on: bool,
    ) -> Screen:
        """A day logged inside a rest period (or the pause just chosen): what the pause
        does, and [End the pause]. Rendered without a read."""
        locale = principal.account.locale
        today, _ = self._days.get.today(principal)
        lines = self.saved_lines(principal, day, status)
        lines.append(self.pause_set_line(locale, period, reminders_on))
        rows: list[list[InlineKeyboardButton]] = []
        if period.end >= today:
            rows.append([self.end_button(locale, period, reminders_on)])
        rows.append(self._change_row(locale, day, today))
        rows += self.app_rows(principal)
        return Screen("\n\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows))

    def pause_set_line(self, locale: Locale, period: RestPeriod, reminders_on: bool) -> str:
        return self._t.t(
            locale,
            "pause-set",
            label=self.label(locale, period.kind),
            until=_until(period),
            reminders=_on(reminders_on),
        )

    def end_button(
        self, locale: Locale, period: RestPeriod, reminders_on: bool
    ) -> InlineKeyboardButton:
        data = acb.encode(acb.RestCallback("end", period.start, reminders_on=reminders_on))
        return InlineKeyboardButton(
            text=self._t.t(locale, "pause-end", reminders=_on(reminders_on)), callback_data=data
        )

    async def ended(self, principal: Principal, lead: str | None) -> Screen:
        """After "End the pause": the line, then today's picker (so today can be logged in
        the same message)."""
        screen, _ = await self._picker(principal, None, None, lead=lead)
        return screen

    def label(self, locale: Locale, status: DayStatus) -> str:
        return self._t.t(locale, f"status-{status.value}")

    def _change_row(self, locale: Locale, day: date, today: date) -> list[InlineKeyboardButton]:
        return [
            self._button(locale, "log-change", _open(day)),
            self._button(locale, "log-another-day", encode(DayCallback("week", today))),
        ]

    def saved_screen(self, principal: Principal, day: date, status: DayStatus) -> Screen:
        """What a day shows once logged (not practiced: that has its own summary)."""
        today, _ = self._days.get.today(principal)
        locale = principal.account.locale
        rows = [self._change_row(locale, day, today)]
        rows += self.app_rows(principal)
        return Screen(
            "\n\n".join(self.saved_lines(principal, day, status)),
            InlineKeyboardMarkup(inline_keyboard=rows),
        )

    def app_rows(self, principal: Principal) -> list[list[InlineKeyboardButton]]:
        """[Open the app] while the time zone is unknown: opening it records the zone."""
        if principal.account.timezone is not None or not self.app_url:
            return []
        return [[app_button(self._t, principal.account.locale, self.app_url)]]

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
        # Auto-rest (PR-09) shows like the rest it stands for: 🌙 or 😌; days a rest period
        # covers as its kind (🌸 as 😌 here, WH-01).
        shown = {d: _AUTO_STATUS[a.kind] for d, a in view.auto.items()} | view.covered | logged
        locale = principal.account.locale
        text = self._t.t(locale, "log-pick-day")
        if note:
            text = self._t.t(locale, note) + "\n\n" + text
        return Screen(text, self._week_markup(locale, end, shown, today))

    def _week_markup(
        self, locale: Locale, end: date, shown: dict[date, DayStatus], today: date
    ) -> InlineKeyboardMarkup:
        days = [end - timedelta(days=i) for i in range(WEEK)]  # newest first
        days = [d for d in days if d >= MIN_LOG_DATE]
        buttons = [
            InlineKeyboardButton(
                text=f"{_WEEK_EMOJI.get(shown.get(d), '·')} {self.day(locale, d, today)}",
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


def _on(flag: bool) -> str:
    return "on" if flag else "off"


def _until(period: RestPeriod) -> DateArg:
    return DateArg(period.end)


def _open(day: date) -> str:
    return encode(DayCallback("open", day))


def _details(day: date) -> str:
    return pcb.encode(pcb.PracticeCallback("open", day))
