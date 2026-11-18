"""Day-status screens (PR-01, PR-04, UI-06): Today (`/log`, and `/start` once the front door
was met), the per-day editor, "Other reason", the week picker.

Today and the editor are one builder: three choices (🧘, 😌, "Other reason"), with ✓ on the
logged one. Every tap edits the same message (the webhook reply, ADR-0012) and answers the
callback in parallel. One DB statement per tap besides the account lookup; "Other reason" is
a pure render. Saving 🧘 Practiced shows the three buttons that follow it (`practice.py`).
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.methods import SendMessage
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from tristhana.application.days import DaysView
from tristhana.application.policies import Principal
from tristhana.application.ports.i18n import DateArg, Translator
from tristhana.bots.telegram import home_callbacks as hcb
from tristhana.bots.telegram import rest_callbacks as acb
from tristhana.bots.telegram import shalas_callbacks as scb
from tristhana.bots.telegram.callbacks import PREFIX, DayCallback, Origin, decode, encode
from tristhana.bots.telegram.check_in import CheckInScreens, register_check_in
from tristhana.bots.telegram.diary import DiaryScreens, note_button, preview, register_diary
from tristhana.bots.telegram.practice import PracticeScreens, register_practice
from tristhana.bots.telegram.progression import ProgressionScreens, register_progression
from tristhana.bots.telegram.runtime import (
    CheckInUseCases,
    DayUseCases,
    DiaryUseCases,
    PracticeUseCases,
    ProgressionUseCases,
    RemindUseCases,
)
from tristhana.bots.telegram.screens import (
    Reply,
    Screen,
    answered,
    app_button,
    app_url,
    day_label,
    menu_row,
    nothing,
    show,
)
from tristhana.domain.accounts import Account
from tristhana.domain.days import MIN_LOG_DATE, DateInFuture, DateTooEarly, DayStatus
from tristhana.domain.journey import OTHER_REASONS, NextStep, Step
from tristhana.domain.locale import Locale
from tristhana.domain.moon import City
from tristhana.domain.rest_days import AutoKind
from tristhana.domain.rest_periods import PAUSE_DAYS, RestPeriod

WEEK = 7
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
# UI-06 stage 6 (B4): the next steps Today offers in the bot, the shala's own; the others stay
# in the app (the bot has its own offers). No "Not now": a step goes once its data exists.
_SHALA_STEPS = frozenset({NextStep.ADD_CLASS, NextStep.INVITE_SHALA_STUDENTS})


async def _no_steps() -> tuple[Step, ...]:
    return ()


def register(
    router: Router,
    days: DayUseCases,
    practices: PracticeUseCases,
    translator: Translator,
    remind: RemindUseCases | None = None,
    miniapp_url: str = "",
    check_ins: CheckInUseCases | None = None,
    diary: DiaryUseCases | None = None,
    progression: ProgressionUseCases | None = None,
) -> DayScreens:
    screens = DayScreens(days, translator, miniapp_url)
    screens.practice = PracticeScreens(days, practices, translator, screens, remind)
    register_practice(router, screens.practice)
    if progression is not None:  # PR-08 (always wired by the app)
        screens.practice.progression = ProgressionScreens(
            progression, translator, screens, screens.practice
        )
        register_progression(router, screens.practice.progression)
    check_in_screens = None
    if check_ins is not None:  # PR-06 (always wired by the app)
        check_in_screens = CheckInScreens(check_ins, translator, screens, screens.practice)
        check_in_screens.notes = diary is not None
        register_check_in(router, check_in_screens)
    if diary is not None:  # PR-07 (always wired by the app)
        screens.notes = True
        screens.diary = DiaryScreens(diary, translator, screens, check_in_screens)
        register_diary(router, screens.diary)  # callbacks; the reply handler goes last

    @router.message(Command("log"))
    async def on_log(message: Message, account: Account) -> SendMessage:  # pyright: ignore[reportUnusedFunction]
        screen = await screens.today_screen(Principal(account))
        return message.answer(screen.text, reply_markup=screen.markup)

    @router.callback_query(F.data.startswith(f"{PREFIX}:"))
    async def on_day(callback: CallbackQuery, account: Account) -> Reply | None:  # pyright: ignore[reportUnusedFunction]
        cb = decode(callback.data)
        if cb is None:
            await answered(callback, nothing())
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


class DayScreens:
    def __init__(self, days: DayUseCases, translator: Translator, miniapp_url: str = "") -> None:
        self._days = days
        self._t = translator
        self.app_url = miniapp_url
        self.practice: PracticeScreens | None = None  # set by `register`
        self.notes = False  # PR-07: the picker shows the day's note (set by `register`)
        self.diary: DiaryScreens | None = None  # set by `register`

    def today(self, principal: Principal) -> tuple[date, bool]:
        return self._days.get.today(principal)

    def home_city(self, principal: Principal) -> City | None:
        return self._days.get.home_city(principal)

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
            case "reasons", date() as day, _:
                return self.reasons(principal, day, cb.origin or "t")
            case _:
                return await self.today_screen(principal)

    async def today_screen(
        self,
        principal: Principal,
        lead: str | None = None,
        lead_row: list[InlineKeyboardButton] | None = None,
        hint: bool = False,
    ) -> Screen:
        """Today (UI-06 T0): the three choices and the Menu. `lead` and `lead_row` go on top
        (an answered invite, an ended pause); `hint` adds the one-time "everything else is
        under Menu" line."""
        return await self._picker(principal, None, lead=lead, lead_row=lead_row, hint=hint)

    async def status(self, principal: Principal, day: date, note: str | None = None) -> Screen:
        """The editor for one day (UI-06 E0): the same three choices as Today, then the note,
        Clear, another day and the way back to Today. An auto-rest day (PR-09) has no ✓,
        just a line saying why it shows as rest."""
        return await self._picker(principal, day, note)

    async def _picker(
        self,
        principal: Principal,
        day: date | None,
        note: str | None = None,
        *,
        lead: str | None = None,
        lead_row: list[InlineKeyboardButton] | None = None,
        hint: bool = False,
    ) -> Screen:
        """Today (`day` None) and the day editor: one read. On Today for someone on a
        shala's staff, the next steps load alongside it (UI-06 stage 6, B4: +1, in parallel)."""
        today, _ = self._days.get.today(principal)
        editor = day is not None
        day = day or today
        shala = principal.account.shala
        steps = self._days.steps
        offers = not editor and steps is not None and shala is not None and shala.staff
        view, due = await asyncio.gather(
            self._days.get.execute(principal, day, day),
            steps.execute(principal) if offers and steps is not None else _no_steps(),
        )
        step = next((s for s in due if s.kind in _SHALA_STEPS and s.shala_id is not None), None)
        current = view.days[0].status if view.days else None
        locale = principal.account.locale
        label = self.day(locale, day, today)
        lines = [lead] if lead else []
        if note:
            lines.append(self._t.t(locale, note, day=label))
        if hint:
            lines.append(self._t.t(locale, "today-menu-hint"))
        lines.append(self._day_block(locale, view, day, label, current))
        shown = preview(self._t, locale, view.notes.get(day)) if editor and self.notes else None
        if shown:  # under the day itself; the editor only (never Today or the week picker)
            lines.append(shown)
        step_row = self._step_row(locale, step) if step is not None else None
        if step is not None and step_row is not None:
            key = "next-class" if step.kind is NextStep.ADD_CLASS else "next-shala-invite"
            lines.append(self._t.t(locale, key))
        rows = [lead_row] if lead_row else []
        rows += self.choice_rows(locale, day, current, "e" if editor else "t")
        period = view.period_on(day)
        if period is not None and period.end >= today:  # still running: it can end early
            rows.append([self.end_button(locale, period, view.practice_on)])
        if step_row is not None:  # one row above the last
            rows.append(step_row)
        if editor:
            if self.notes:
                rows.append([note_button(self._t, locale, day, "d")])
            last = [self._button(locale, "log-another-day", encode(DayCallback("week", today)))]
            if current is not None:
                last.insert(0, self._button(locale, "log-clear", encode(DayCallback("clear", day))))
            rows.append(last)
            rows.append([self._button(locale, "today-back", hcb.TODAY)])
        else:
            rows.append(menu_row(self._t, locale))
        return Screen("\n\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows))

    def _step_row(self, locale: Locale, step: Step) -> list[InlineKeyboardButton] | None:
        """The step's button: the app's new class form, or the shala's student link."""
        if step.shala_id is None:
            return None
        if step.kind is NextStep.ADD_CLASS:
            if not self.app_url:  # dev without the app: the line would point at nothing
                return None
            url = app_url(self.app_url, "class", shala=str(step.shala_id))
            return [app_button(self._t, locale, "next-class-do", url)]
        return [self._button(locale, "next-shala-invite-do", scb.on_shala("i", step.shala_id))]

    def _day_block(
        self, locale: Locale, view: DaysView, day: date, label: str, current: DayStatus | None
    ) -> str:
        """The date first, always: it opens the message and a chat-list preview, which must
        never begin with "🌸 Ladies' holiday through …". Under it, what already answers
        "Practice or rest?": the auto-rest or pause line, and the status as the person logged
        it (their own screen). Only a day with neither gets the question."""
        answers: list[str] = []
        auto = self.auto_line(locale, view, day)
        if auto:
            answers.append(auto)
        if current is not None:
            answers.append(self._t.t(locale, "today-logged", label=self.label(locale, current)))
        if not answers:
            return self._t.t(locale, "start-prompt", day=label)
        return "\n".join([label, *answers])

    def choice_rows(
        self, locale: Locale, day: date, current: DayStatus | None, origin: Origin
    ) -> list[list[InlineKeyboardButton]]:
        """🧘 Practiced, 😌 Rest day, "Other reason": one per row, ✓ on the logged choice
        (on "Other reason" for any status behind it)."""
        other = self._t.t(locale, "today-other")
        reasons = encode(DayCallback("reasons", day, origin=origin))
        return [
            [self._status_button(locale, day, DayStatus.PRACTICED, current)],
            [self._status_button(locale, day, DayStatus.REST, current)],
            [
                InlineKeyboardButton(
                    text=f"✓ {other}" if current in OTHER_REASONS else other,
                    callback_data=reasons,
                )
            ],
        ]

    def reasons(self, principal: Principal, day: date, origin: Origin) -> Screen:
        """ "Other reason" (UI-06 T1): a pure render, so no ✓ here. Without 🌸 when the
        person hid it (WH-01)."""
        account = principal.account
        locale = account.locale
        today, _ = self._days.get.today(principal)
        rows = [
            [self._status_button(locale, day, status, None)]
            for status in OTHER_REASONS
            if not (status is DayStatus.LADIES and account.hide_ladies)
        ]
        back = hcb.TODAY if origin == "t" else _open(day)
        rows.append([self._button(locale, "log-back", back)])
        text = self._t.t(locale, "today-reasons-title", day=self.day(locale, day, today))
        return Screen(text, InlineKeyboardMarkup(inline_keyboard=rows))

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
            lead = self.practice.count_lead(principal.account.locale, saved.celebrations)
            return await self.practice.after_practiced(
                principal, day, saved.practice, cut=saved.cut, lead=lead
            )
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
        """V + "for how many days?" with the kind's day counts (or its "Another number…"
        ones). A pure render: Another number… and Back need no DB. Ignoring it means no pause;
        the Menu row ends it, as on every screen that closes a log (UI-06 stage 5, Q330)."""
        locale = principal.account.locale
        today, _ = self._days.get.today(principal)
        lines = self.saved_lines(principal, day, kind)
        rel = "yesterday" if day == today - timedelta(days=1) else "today"
        lines.append(
            self._t.t(
                locale,
                "pause-ask",
                label=self.label(locale, kind),
                rel=rel,
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
        only = acb.encode(acb.RestCallback("only", day, kind))
        rows.append([self._button(locale, "pause-only", only, rel=rel)])
        rows.append(self._change_row(locale, day, today))
        rows += self.app_rows(principal)
        rows.append(menu_row(self._t, locale))
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
        rows.append(menu_row(self._t, locale))
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
        """After "End the pause": the line, then Today (so today can be logged in the same
        message)."""
        return await self.today_screen(principal, lead=lead)

    def label(self, locale: Locale, status: DayStatus) -> str:
        return self._t.t(locale, f"status-{status.value}")

    def _change_row(self, locale: Locale, day: date, today: date) -> list[InlineKeyboardButton]:
        return [
            self._button(locale, "log-change", _open(day)),
            self._button(locale, "log-another-day", encode(DayCallback("week", today))),
        ]

    def saved_screen(self, principal: Principal, day: date, status: DayStatus) -> Screen:
        """What a day shows once logged (UI-06 S; not practiced: that has its own summary)."""
        today, _ = self._days.get.today(principal)
        locale = principal.account.locale
        rows = [self._change_row(locale, day, today), menu_row(self._t, locale)]
        return Screen(
            "\n\n".join(self.saved_lines(principal, day, status)),
            InlineKeyboardMarkup(inline_keyboard=rows),
        )

    def app_rows(self, principal: Principal) -> list[list[InlineKeyboardButton]]:
        """[Open the app] while the time zone is unknown: opening it records the zone."""
        if principal.account.timezone is not None or not self.app_url:
            return []
        return [[app_button(self._t, principal.account.locale, "start-open-app", self.app_url)]]

    def saved_lines(self, principal: Principal, day: date, status: DayStatus) -> list[str]:
        """ "✓ Today, Sun, Oct 18: 🧘 Practiced" + the cheer and the privacy note. No time-zone
        tip here (UI-06 Q314)."""
        locale = principal.account.locale
        today, _ = self._days.get.today(principal)
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
        if paging:
            rows.append(paging)
        rows.append(menu_row(self._t, locale))  # UI-06: opened from Help
        return InlineKeyboardMarkup(inline_keyboard=rows)

    def _status_button(
        self, locale: Locale, day: date, status: DayStatus, current: DayStatus | None
    ) -> InlineKeyboardButton:
        text = self._t.t(locale, f"status-{status.value}")
        return InlineKeyboardButton(
            text=f"✓ {text}" if status is current else text,
            callback_data=encode(DayCallback("set", day, status)),
        )

    def _button(self, locale: Locale, key: str, data: str, **args: str) -> InlineKeyboardButton:
        return InlineKeyboardButton(text=self._t.t(locale, key, **args), callback_data=data)

    def day(self, locale: Locale, day: date, today: date) -> str:
        return day_label(self._t, locale, day, today)


def _on(flag: bool) -> str:
    return "on" if flag else "off"


def _until(period: RestPeriod) -> DateArg:
    return DateArg(period.end)


def _open(day: date) -> str:
    return encode(DayCallback("open", day))
