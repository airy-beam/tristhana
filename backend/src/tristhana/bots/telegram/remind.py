"""The daily practice reminder (PR-10): `/remind`, its settings, the reminder message with
quick-log buttons (rendered here for the notifier, so wording lives in one place), and the
one-time offer under "practice saved"."""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from typing import TYPE_CHECKING

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.methods import SendMessage
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from tristhana.application.policies import Principal
from tristhana.application.ports.i18n import DateArg, TimeArg, Translator
from tristhana.application.ports.notifications import (
    PracticePause,
    PracticeReminder,
    ReminderPatch,
)
from tristhana.bots.telegram import callbacks as dcb
from tristhana.bots.telegram import moon_callbacks as mcb
from tristhana.bots.telegram import rest_callbacks as acb
from tristhana.bots.telegram import settings_callbacks as scb
from tristhana.bots.telegram.day_off import day_off_picker
from tristhana.bots.telegram.remind_callbacks import PREFIX, RemindCallback, decode, encode
from tristhana.bots.telegram.runtime import RemindUseCases, RestUseCases
from tristhana.bots.telegram.screens import Reply, Screen, answered, button, day_label, show
from tristhana.domain.accounts import Account
from tristhana.domain.days import DateInFuture, DateTooEarly, DayStatus
from tristhana.domain.locale import Locale
from tristhana.domain.moon import City
from tristhana.domain.notifications import (
    COPIED_DATE_AFTER,
    PRACTICE_TIMES,
    WEEKDAYS,
    InvalidSettings,
    NotificationSettings,
    day_off_question,
)
from tristhana.domain.rest_days import InvalidDayOff

if TYPE_CHECKING:
    from tristhana.bots.telegram.days import DayScreens


def _data(**kw: object) -> str:
    return encode(RemindCallback(**kw))  # type: ignore[arg-type]


def reminder_screen(
    t: Translator, locale: Locale, r: PracticeReminder, status: str | None = None
) -> Screen:
    """The reminder (also re-rendered after 🔕 / back on, with a status line), or the one
    note after a long silence."""
    if r.pause:
        rows = [
            [button(t, locale, "remind-turn-back-on", _data(action="quick", on=True, day=r.day))]
        ]
        return Screen(t.t(locale, "remind-paused"), InlineKeyboardMarkup(inline_keyboard=rows))
    # "Today, Mon, Oct 19" / «Сегодня, пн, 19 окт.»: sent on the day it asks about.
    text = t.t(locale, "remind-practice", day=day_label(t, locale, r.day, r.day))
    if status:
        text += "\n\n" + t.t(locale, status)
    if status == "remind-off-note":
        rows = [
            [button(t, locale, "remind-turn-back-on", _data(action="quick", on=True, day=r.day))]
        ]
        return Screen(text, InlineKeyboardMarkup(inline_keyboard=rows))
    rows = [
        [button(t, locale, "remind-same", _data(action="same", day=r.day))],
        [
            # Insert-if-absent (Q26): a day logged since (maybe 🌸) is never overwritten.
            button(t, locale, "remind-practiced", _data(action="log_practiced", day=r.day)),
            button(t, locale, "status-rest", _data(action="log_rest", day=r.day)),
        ],
        [
            button(t, locale, "remind-other", dcb.encode(dcb.DayCallback("open", r.day))),
            button(t, locale, "remind-turn-off", _data(action="quick", on=False, day=r.day)),
        ],
    ]
    return Screen(text, InlineKeyboardMarkup(inline_keyboard=rows))


def practice_status(
    t: Translator,
    locale: Locale,
    settings: NotificationSettings,
    zone: str | None,
    today: date,
    place: City | None = None,
) -> str:
    """The practice reminder line ("🔔 Practice reminder: every day except Saturday, …")."""
    p = settings.practice
    if not p.enabled:
        return t.t(locale, "remind-status-off")
    # Without a known zone there is no honest zone label: "10:00 your time".
    time_text = (
        t.t(locale, "time-label", time=TimeArg(today, p.at, zone, place))
        if zone
        else t.t(locale, "remind-local-time", time=f"{p.at:%H:%M}")
    )
    return t.t(locale, "remind-status-on", days=_days_text(t, locale, p.days), time=time_text)


def _days_text(t: Translator, locale: Locale, days: frozenset[int]) -> str:
    if days == WEEKDAYS:
        return t.t(locale, "remind-every-day")
    missing = WEEKDAYS - days
    if len(missing) == 1:
        return t.t(locale, "remind-days-except", d=next(iter(missing)))
    return ", ".join(t.t(locale, "remind-weekday", d=d) for d in sorted(days))


def offer_row(t: Translator, locale: Locale, day: date) -> list[InlineKeyboardButton]:
    return [
        button(t, locale, "remind-offer-yes", _data(action="yes", day=day)),
        button(t, locale, "remind-offer-no", _data(action="no", day=day)),
    ]


def register_remind(
    router: Router,
    remind: RemindUseCases,
    days: DayScreens,
    translator: Translator,
    rest: RestUseCases | None = None,
) -> RemindScreens:
    screens = RemindScreens(remind, days, translator, rest)

    @router.message(Command("remind"))
    async def on_remind(message: Message, account: Account) -> SendMessage:  # pyright: ignore[reportUnusedFunction]
        screen = await screens.settings(Principal(account))
        return message.answer(screen.text, reply_markup=screen.markup)

    @router.callback_query(F.data.startswith(f"{PREFIX}:"))
    async def on_remind_tap(callback: CallbackQuery, account: Account) -> Reply | None:  # pyright: ignore[reportUnusedFunction]
        cb = decode(callback.data)
        screen = await answered(callback, screens.handle(Principal(account), cb))
        return show(callback, screen) if screen else None

    return screens


class RemindScreens:
    def __init__(
        self,
        remind: RemindUseCases,
        days: DayScreens,
        translator: Translator,
        rest: RestUseCases | None = None,
    ) -> None:
        self._r = remind
        self._days = days
        self._t = translator
        self._rest = rest

    async def handle(self, principal: Principal, cb: RemindCallback | None) -> Screen | None:
        if cb is None:
            return None
        try:
            match cb.action:
                case "view":
                    return await self.settings(principal)
                case "switch":
                    patch = ReminderPatch(on=cb.on)
                    saved, pause = await self._r.update.execute_with_pause(principal, patch)
                    return self.settings_screen(principal, saved, pause)
                case "time":
                    patch = ReminderPatch(at=cb.at)
                    saved, pause = await self._r.update.execute_with_pause(principal, patch)
                    return self.settings_screen(principal, saved, pause)
                case "yes" | "no":
                    saved = await self._r.offer.execute(principal, cb.action == "yes")
                    if cb.action == "yes":
                        return self.settings_screen(principal, saved)
                    assert cb.day is not None  # noqa: S101 - decoded with a date
                    return await self._practice_summary(principal, cb.day)
                case "same":
                    assert cb.day is not None  # noqa: S101
                    return await self._same(principal, cb.day)
                case "log_practiced" | "log_rest":
                    assert cb.day is not None  # noqa: S101
                    practiced = cb.action == "log_practiced"
                    status = DayStatus.PRACTICED if practiced else DayStatus.REST
                    return await self._log(principal, cb.day, status)
                case "quick":
                    assert cb.day is not None  # noqa: S101
                    await self._r.update.execute(principal, ReminderPatch(on=cb.on))
                    status = "remind-on-again" if cb.on else "remind-off-note"
                    locale = principal.account.locale
                    return reminder_screen(self._t, locale, PracticeReminder(cb.day), status)
                case "day_off":  # the question's answers
                    saved = await self._r.day_off.execute(principal, cb.days_off)
                    return await self.settings(Principal(saved.account))
                case "day_off_toggle":
                    saved = await self._r.day_off.execute(principal, cb.days_off)
                    return self.day_off(Principal(saved.account))
                case "day_off_pick":
                    return self.day_off(principal)
                case "day_off_later":
                    await self._r.dismiss_day_off.execute(principal)
                    dismissed = replace(principal.account, day_off_dismissed=True)
                    return await self.settings(Principal(dismissed))
        except (InvalidSettings, InvalidDayOff):
            return await self.settings(principal)  # stale or forged: just reshow

    def day_off(self, principal: Principal) -> Screen:
        locale = principal.account.locale
        return day_off_picker(
            self._t,
            locale,
            principal.account.day_off.days,
            lambda days: _data(action="day_off_toggle", days_off=days),
            _data(action="day_off_pick"),
            button(self._t, locale, "remind-practice-link", _data(action="view")),
        )

    async def _practice_summary(self, principal: Principal, day: date) -> Screen:
        practice = self._days.practice
        assert practice is not None  # noqa: S101 - wired by days.register
        return await practice.summary(principal, day, offer=False)

    async def _log(self, principal: Principal, day: date, status: DayStatus) -> Screen | None:
        """🧘 / 😌 from a reminder (Q26): logs the day only if it is still empty; a day
        logged since shows as stored, with ✏️ Change."""
        if self._rest is None:
            return None
        today, _ = self._days.today(principal)
        try:
            logged = await self._rest.log_from_reminder.execute(principal, day, status)
        except DateInFuture:
            return await self._days.week(principal, today, note="log-date-future")
        except DateTooEarly:
            return await self._days.week(principal, today, note="log-date-too-early")
        practice = self._days.practice
        assert practice is not None  # noqa: S101
        if logged.day is None:  # cleared elsewhere in between
            return await self._days.status(principal, day)
        if logged.already:
            if logged.day.status is DayStatus.PRACTICED:
                stored = logged.day.practices[0] if logged.day.practices else None
                return await practice.summary(
                    principal, day, practice=stored, offer=False, check_ins=logged.day.check_ins
                )
            return self._days.saved_screen(principal, day, logged.day.status)
        if status is DayStatus.PRACTICED:
            lead = practice.count_lead(principal.account.locale, logged.celebrations)
            return await practice.details(principal, day, cut=logged.cut, known=True, lead=lead)
        return self._days.saved_screen(principal, day, status)

    async def _same(self, principal: Principal, day: date) -> Screen:
        today, _ = self._days.today(principal)
        try:
            logged = await self._r.quick_log.execute(principal, day)
        except DateInFuture:
            return await self._days.week(principal, today, note="log-date-future")
        except DateTooEarly:
            return await self._days.week(principal, today, note="log-date-too-early")
        practice = self._days.practice
        assert practice is not None  # noqa: S101
        if logged.day is None:  # cleared elsewhere in between
            return await self._days.status(principal, day)
        if logged.already:
            if logged.day.status is DayStatus.PRACTICED:
                stored = logged.day.practices[0] if logged.day.practices else None
                return await practice.summary(
                    principal, day, practice=stored, offer=False, check_ins=logged.day.check_ins
                )
            return self._days.saved_screen(principal, day, logged.day.status)
        lead = practice.count_lead(principal.account.locale, logged.celebrations)
        if not logged.day.practices:  # nothing to copy yet: the details screen
            return await practice.details(principal, day, cut=logged.cut, known=True, lead=lead)
        note = None
        if logged.copied_from is not None and day - logged.copied_from > COPIED_DATE_AFTER:
            locale = principal.account.locale
            note = self._t.t(
                locale,
                "remind-copied-from",
                date=DateArg(logged.copied_from, with_year=logged.copied_from.year != day.year),
            )
        # Someone answering a reminder has already chosen: no offer (and no settings read).
        return await practice.summary(
            principal,
            day,
            practice=logged.day.practices[0],
            extra=note,
            offer=False,
            cut=logged.cut,
            check_ins=(),  # the day was empty until this tap
            lead=lead,
        )

    async def settings(self, principal: Principal) -> Screen:
        saved, pause = await self._r.settings.get_with_pause(principal)
        return self.settings_screen(principal, saved, pause)

    def settings_screen(
        self,
        principal: Principal,
        settings: NotificationSettings,
        pause: PracticePause | None = None,
    ) -> Screen:
        """`pause`: the rest period covering today (WH-01), read with the settings."""
        account = principal.account
        locale = account.locale
        p = settings.practice
        today, _ = self._days.today(principal)
        place = self._days.home_city(principal)
        lines = [self.status_line(locale, settings, account.timezone, today, place)]
        paused = pause if p.enabled else None
        if paused is not None:
            lines.append(self._t.t(locale, "remind-paused-until", until=DateArg(paused.until)))
        if p.enabled:
            lines.append(self._t.t(locale, "remind-days-follow"))
        if account.timezone is None:
            lines.append(self._t.t(locale, "moon-zone-needed"))
        question = day_off_question(account.day_off.days, account.day_off_dismissed, settings)
        if question is not None:
            reminders = "on" if question.reminders_on else "off"
            lines.append(self._t.t(locale, "day-off-ask", d=question.weekday, reminders=reminders))
        lines.append(self._t.t(locale, "remind-explain"))
        times = [
            InlineKeyboardButton(
                text=("✓ " if p.enabled and at == p.at else "") + f"{at:%H:%M}",
                callback_data=_data(action="time", at=at),
            )
            for at in PRACTICE_TIMES
        ]
        switch = (
            button(self._t, locale, "remind-turn-off", _data(action="switch", on=False))
            if p.enabled
            else button(self._t, locale, "remind-turn-on", _data(action="switch", on=True))
        )
        rows = [
            *(self._question_rows(locale, question.weekday) if question else []),
            times[:3],
            times[3:],
            # Reminders come on the practice days: the one day setting is the day off.
            [button(self._t, locale, "settings-day-off-button", _data(action="day_off_pick"))],
            *([[self._resume_button(locale, paused)]] if paused else []),
            [switch],
            [
                button(
                    self._t, locale, "remind-moon-link", mcb.encode(mcb.MoonCallback("reminders"))
                )
            ],
            [button(self._t, locale, "settings-link", scb.encode(scb.SettingsCallback("view")))],
        ]
        return Screen("\n\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows))

    def _resume_button(self, locale: Locale, pause: PracticePause) -> InlineKeyboardButton:
        data = acb.encode(acb.RestCallback("end_remind", pause.start))
        return button(self._t, locale, "remind-resume", data)

    def _question_rows(self, locale: Locale, weekday: int) -> list[list[InlineKeyboardButton]]:
        """[Yes] [the other weekend day, for a weekend day] / [Other…] [Not now]."""
        yes = _data(action="day_off", days_off=frozenset({weekday}))
        first = [button(self._t, locale, "day-off-ask-yes", yes)]
        if weekday in (6, 7):
            other = 13 - weekday  # Saturday ↔ Sunday
            first.append(
                InlineKeyboardButton(
                    text=self._t.t(locale, "day-off-ask-instead", d=other),
                    callback_data=_data(action="day_off", days_off=frozenset({other})),
                )
            )
        return [
            first,
            [
                button(self._t, locale, "day-off-ask-other", _data(action="day_off_pick")),
                button(self._t, locale, "day-off-ask-later", _data(action="day_off_later")),
            ],
        ]

    def status_line(
        self,
        locale: Locale,
        settings: NotificationSettings,
        zone: str | None,
        today: date,
        place: City | None = None,
    ) -> str:
        return practice_status(self._t, locale, settings, zone, today, place)
