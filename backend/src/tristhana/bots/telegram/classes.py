"""Shala classes in the bot (SC-02, ADR-0034): a member's read-only week (0-3 from the shala's
today), "My schedule" across every shala in my zone (`/schedule`, `/classes` with *I teach*;
SC-03, ADR-0035), and the staff quick actions
on the next 48 h: cancel (after an ask), restore, hold anyway. Silent: no one gets a message
(Q122). Forms live in the Mini App (Q103). Plain text, no `parse_mode`: titles are user text.
"""

import asyncio
from collections.abc import Awaitable, Mapping
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.methods import SendMessage
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from tristhana.application.classes import (
    BadWindow,
    ClassUseCases,
    MyRow,
    MySchedule,
    Only,
    Schedule,
    Teaching,
)
from tristhana.application.policies import NotAllowed, NotFound, Principal
from tristhana.application.ports.i18n import DateArg, TimeArg, Translator
from tristhana.application.ports.storage import Clock
from tristhana.bots.telegram import classes_callbacks as cb
from tristhana.bots.telegram import settings_callbacks, shalas_callbacks
from tristhana.bots.telegram.screens import Reply, Screen, answered, nothing, show, zone_label
from tristhana.domain.accounts import Account
from tristhana.domain.classes import (
    ClassType,
    InvalidClass,
    Occurrence,
    Override,
    OverrideStatus,
    Reason,
)
from tristhana.domain.locale import Locale
from tristhana.domain.moon import Cities, City
from tristhana.domain.teacher_links import shown_name

if TYPE_CHECKING:
    from tristhana.bots.telegram.shalas import ShalaScreens
    from tristhana.bots.telegram.teacher_links import LinkScreens

WEEK = 7
PICK_HOURS = 48
BUDGET = 3800  # characters, under Telegram's 4096 with the note on top
DASH = "\u2013"  # en dash: 06:00-09:30
_CONTEXT = {ClassType.MYSORE: "mysore", ClassType.LED: "led", ClassType.PRIVATE: "private"}
_ONLY: dict[cb.Filter, Only] = {"a": Only.ALL, "t": Only.TEACHERS, "m": Only.MINE}
_FILTER_KEY = {Only.ALL: "all", Only.TEACHERS: "teachers", Only.MINE: "mine"}
MAX_SHIFTS = 3


def type_name(t: Translator, locale: Locale, type: ClassType) -> str:
    """Mysore, Led and 1:1 reuse the practice context words; the rest have their own."""
    context = _CONTEXT.get(type)
    if context is not None:
        return t.t(locale, f"context-{context}")
    return t.t(locale, "class-type", type=type.value)


def _decimal(value: float, locale: Locale) -> str:
    """A half-hour shift: "0.5" / «0,5» (Fluent selects the plural from the string's default)."""
    text = f"{value:g}"
    return text.replace(".", ",") if locale == "ru" else text


def _hm(at: datetime) -> str:
    return f"{at:%H:%M}"


class ScheduleScreens:
    def __init__(
        self,
        classes: ClassUseCases,
        shalas: "ShalaScreens",
        links: "LinkScreens",
        translator: Translator,
        cities: Cities,
        clock: Clock,
    ) -> None:
        self._c = classes
        self._clock = clock
        self._shalas = shalas
        self._links = links
        self._t = translator
        self._cities = cities

    def _day(self, locale: Locale, day: date) -> str:
        return self._t.t(locale, "day-label", rel="other", date=DateArg(day))

    def _zone(self, locale: Locale, s: Schedule, day: date) -> str:
        return zone_label(self._t, locale, s.zone, day, self._cities.find(s.city))

    def _class(self, locale: Locale, o: Occurrence) -> str:
        name = type_name(self._t, locale, o.type)
        return f"{name} {o.title}" if o.title else name

    def _name(self, locale: Locale, staff: Mapping[UUID, str | None], id: UUID | None) -> str:
        found = None if id is None else staff.get(id)
        return shown_name(found) or self._t.t(locale, "link-no-name")

    def _row(
        self,
        principal: Principal,
        s: Schedule,
        o: Occurrence,
    ) -> str:
        """`06:00-09:30 Mysore · Anna` in the shala's zone; a cancelled one with its reason."""
        locale = principal.account.locale
        here = ZoneInfo(s.zone)
        start = o.starts_at.astimezone(here)
        length = datetime.combine(o.on, o.end) - datetime.combine(o.on, o.start)
        if length < timedelta(0):  # ends at midnight
            length += timedelta(days=1)
        text = f"{_hm(start)}{DASH}{_hm(start + length)} {self._class(locale, o)}"
        if o.teacher_id is not None:
            name = self._name(locale, s.staff, o.teacher_id)
            if o.substitute:
                name = self._t.t(locale, "schedule-substitute", name=name)
            text += f" · {name}"
        if o.online:
            text += " 🌐"
            mine = principal.account.timezone
            if mine and o.starts_at.astimezone(ZoneInfo(mine)).utcoffset() != start.utcoffset():
                at = _hm(o.starts_at.astimezone(ZoneInfo(mine)))
                text += " " + self._t.t(locale, "schedule-your-time", time=at)
        if o.moved and o.on != o.key and o.planned is not None:
            moved = self._t.t(
                locale, "schedule-moved", day=self._day(locale, o.key), time=f"{o.planned:%H:%M}"
            )
            text += f" · {moved}"
        return self._marked(locale, o, text)

    def _marked(self, locale: Locale, o: Occurrence, text: str) -> str:
        """The row marks (expert items 1, 3, 4): 🌙 leads a moon cancellation, ❌ a closure or
        a manual cancel; a class held on its moon day ends with ` · 🌙`."""
        if o.cancelled is None:
            if o.moon:
                text += " " + self._t.t(locale, "schedule-held-moon")
            return text
        reason = self._t.t(locale, "schedule-reason", reason=o.cancelled.value)
        lead = "🌙" if o.cancelled is Reason.MOON else "❌"
        text = f"{lead} {text} ({reason})"
        if o.swapped_to is not None:
            target = self._day(locale, o.swapped_to)
            text += " · " + self._t.t(locale, "schedule-swapped-inline", day=target)
        return text

    # The week

    async def week(self, principal: Principal, shala: UUID, n: int, note: str = "") -> Screen:
        try:
            s = await self._c.schedule.execute(principal, shala, None, WEEK, skip=WEEK * n)
        except NotFound:
            return await self._links.overview(principal)
        except BadWindow:
            return await self._shalas.card(principal, shala)
        return self._week(principal, s, n, note)

    def _week(self, principal: Principal, s: Schedule, n: int, note: str) -> Screen:
        locale = principal.account.locale
        first, last = s.days[0].date, s.days[-1].date
        span = f"{self._day(locale, first)} {DASH} {self._day(locale, last)}"
        header = self._zone(locale, s, first)
        here = ZoneInfo(s.zone)
        lines = [
            self._t.t(locale, "schedule-title", shala=s.name, range=span),
            self._t.t(locale, "schedule-zone", zone=header),
        ]
        moved_away: dict[date, list[Occurrence]] = {}
        for o in s.occurrences:
            if o.swapped_from is not None:
                moved_away.setdefault(o.swapped_from, []).append(o)
        for day in s.days:
            marks = [self._day(locale, day.date)]
            if day.moon:
                marks.append(self._t.t(locale, "schedule-moon-day"))
            if day.day_off:
                marks.append(self._t.t(locale, "schedule-day-off"))
            if day.swap_from is not None:
                marks.append(
                    self._t.t(locale, "schedule-swap", day=self._day(locale, day.swap_from))
                )
            label = self._zone(locale, s, day.date)
            if label != header:  # a DST change inside the week
                marks.append(label)
            # Rows go under the shala-local date of their instant: an online class in another
            # zone can fall on a different day here (review fix).
            entries = [
                self._row(principal, s, o)
                for o in s.occurrences
                if o.starts_at.astimezone(here).date() == day.date
            ]
            for at, gone in enumerate(moved_away.get(day.date, [])):
                what = f"{gone.start:%H:%M} {self._class(locale, gone)}"
                reason = gone.swap_reason or Reason.MOON
                entries.insert(
                    at,
                    self._t.t(
                        locale,
                        "schedule-swapped-to",
                        **{"class": what},
                        day=self._day(locale, gone.on),
                        reason=self._t.t(locale, "schedule-reason", reason=reason.value),
                    ),
                )
            if not entries and not (day.moon or day.day_off or day.swap_from):
                continue
            block = [" · ".join(marks), *(f"  {r}" for r in entries)]
            if sum(len(x) + 1 for x in (*lines, *block)) > BUDGET:  # the rest: in the Mini App
                lines.append("…")
                break
            lines += block
        if not s.occurrences:
            lines.append(self._t.t(locale, "schedule-empty"))
        text = "\n".join(lines)
        if note:
            text = f"{note}\n\n{text}"
        nav: list[InlineKeyboardButton] = []
        if n > 0:
            nav.append(self._button(locale, "page-prev", cb.week(s.shala_id, n - 1)))
        if n < cb.WEEKS - 1:
            nav.append(self._button(locale, "page-next", cb.week(s.shala_id, n + 1)))
        rows: list[list[InlineKeyboardButton]] = [nav] if nav else []
        if s.manage:
            rows.append([self._button(locale, "class-cancel-pick", cb.pick(s.shala_id))])
        back = shalas_callbacks.on_shala("c", s.shala_id)
        rows.append([self._button(locale, "log-back", back)])
        return Screen(text, InlineKeyboardMarkup(inline_keyboard=rows))

    # My schedule (SC-03)

    async def my(self, principal: Principal, n: int, only: cb.Filter) -> Screen:
        """Week `n` (0-3) from my today, every shala I'm in, in my zone; memberships, links and
        my moon city are re-read on every tap."""
        s = await self._c.mine.execute(principal, None, WEEK, skip=WEEK * n, only=_ONLY[only])
        return self._my(principal, s, n, only)

    def _my(self, principal: Principal, s: MySchedule, n: int, only: cb.Filter) -> Screen:
        account = principal.account
        locale = account.locale
        if not s.shalas:
            return Screen(
                self._t.t(locale, "my-schedule-none"), InlineKeyboardMarkup(inline_keyboard=[])
            )
        first, last = s.days[0].date, s.days[-1].date
        span = f"{self._day(locale, first)} {DASH} {self._day(locale, last)}"
        home = self._cities.find(account.home_city if s.zone_known else s.shalas[0].city)
        header = zone_label(self._t, locale, s.zone, first, home)
        lines = [self._t.t(locale, "my-schedule-title", range=span)]
        if s.zone_known:
            lines.append(self._t.t(locale, "schedule-zone", zone=header))
        else:
            lines.append(self._t.t(locale, "my-schedule-zone-unknown", zone=header))
        names = {x.id: x.name for x in s.shalas}
        lines += self._shift_lines(locale, s, names)
        shift_days = {x.on for x in s.shifts}
        more = self._t.t(locale, "my-schedule-more")
        here = ZoneInfo(s.zone)
        named = len({r.shala_id for r in s.rows}) > 1
        for day in s.days:
            marks = [self._day(locale, day.date)]
            if day.my_moon:
                marks.append(self._t.t(locale, "my-schedule-my-moon"))
            if day.date in shift_days:
                marks.append("⚠")
            label = zone_label(self._t, locale, s.zone, day.date, home)
            if label != header:  # my own DST change inside the week
                marks.append(f"· {label}")
            entries = [
                self._my_row(locale, s, r, named, home)
                for r in s.rows
                if r.occurrence.starts_at.astimezone(here).date() == day.date
            ]
            if not entries and len(marks) == 1:
                continue
            block = [" ".join(marks), *(f"  {e}" for e in entries)]
            if sum(len(x) + 1 for x in (*lines, *block)) > BUDGET - len(more) - 3:
                lines += ["…", more]  # the full week is in the Mini App
                break
            lines += block
        if not s.rows:
            lines.append(self._t.t(locale, "my-schedule-empty", f=_FILTER_KEY[_ONLY[only]]))
        return Screen("\n".join(lines), self._my_buttons(principal, s, n, only))

    def _shift_lines(self, locale: Locale, s: MySchedule, names: Mapping[UUID, str]) -> list[str]:
        out: list[str] = []
        for shift in s.shifts[:MAX_SHIFTS]:
            rows = [r for r in s.rows if r.zone == shift.zone]
            shalas = list(dict.fromkeys(r.shala_id for r in rows))
            if len(shalas) == 1:
                where = names[shalas[0]]
            else:
                where = zone_label(self._t, locale, shift.zone, shift.on, None).split(" (")[0]
            hours = abs(shift.minutes) / 60
            out.append(
                self._t.t(
                    locale,
                    "schedule-shift",
                    weekday=shift.on.isoweekday(),
                    date=DateArg(shift.on, style="long"),
                    where=where,
                    hours=int(hours) if hours.is_integer() else _decimal(hours, locale),
                    dir="earlier" if shift.minutes > 0 else "later",
                )
            )
        if len(s.shifts) > MAX_SHIFTS:
            out.append("…")
        return out

    def _my_row(
        self, locale: Locale, s: MySchedule, r: MyRow, named: bool, home: City | None
    ) -> str:
        """`06:00-09:30 Mysore · Anna 👤 · Ashtanga Almaty · 17:30 Berlin (UTC+1)` in my zone."""
        o, staff = r.occurrence, s.staff.get(r.shala_id, {})
        mine = ZoneInfo(s.zone)
        start = o.starts_at.astimezone(mine)
        length = datetime.combine(o.on, o.end) - datetime.combine(o.on, o.start)
        if length < timedelta(0):  # ends at midnight
            length += timedelta(days=1)
        text = f"{_hm(start)}{DASH}{_hm(start + length)} {self._class(locale, o)}"
        match r.role:
            case Teaching.COVERED:
                name = self._name(locale, staff, o.teacher_id)
                text += " · " + self._t.t(locale, "my-classes-covered", name=name)
            case Teaching.COVERING if o.planned_teacher is not None:
                name = self._name(locale, staff, o.planned_teacher)
                text += " · " + self._t.t(locale, "my-classes-covering", name=name)
            case Teaching.TEACHING | Teaching.COVERING:
                pass
            case None if o.teacher_id is not None:
                name = self._name(locale, staff, o.teacher_id)
                if o.substitute and o.planned_teacher is not None:
                    planned = self._name(locale, staff, o.planned_teacher)
                    name = self._t.t(locale, "schedule-covering-for", name=name, teacher=planned)
                elif o.substitute:
                    name = self._t.t(locale, "schedule-substitute", name=name)
                if r.my_teacher:
                    name += " " + self._t.t(locale, "my-schedule-teacher-mark")
                text += f" · {name}"
            case None:
                pass
        if o.online:
            text += " 🌐"
        if named:
            text += f" · {next(x.name for x in s.shalas if x.id == r.shala_id)}"
        there = o.starts_at.astimezone(ZoneInfo(r.zone))
        if there.utcoffset() != start.utcoffset():
            # The class's own wall clock with the offset at that instant (a change night too).
            at = TimeArg(there.date(), there.time(), r.zone, self._cities.find(r.city))
            text += " · " + self._t.t(locale, "time-label", time=at)
        if o.moved and o.on != o.key and o.planned is not None:
            moved = self._t.t(
                locale, "schedule-moved", day=self._day(locale, o.key), time=f"{o.planned:%H:%M}"
            )
            text += f" · {moved}"
        if o.swapped_from is not None:
            text += " · " + self._t.t(
                locale, "schedule-swapped-from", day=self._day(locale, o.swapped_from)
            )
        return self._marked(locale, o, text)

    def _my_buttons(
        self, principal: Principal, s: MySchedule, n: int, only: cb.Filter
    ) -> InlineKeyboardMarkup:
        locale = principal.account.locale
        shown: list[cb.Filter] = ["a"]
        if s.has_teachers:
            shown.append("t")
        if s.is_staff:
            shown.append("m")
        if only not in shown:
            shown.append(only)
        filters = [
            InlineKeyboardButton(
                text=self._t.t(locale, "my-schedule-filter", f=_FILTER_KEY[_ONLY[f]])
                + (" ✓" if f == only else ""),
                callback_data=cb.my_week(n, f),
            )
            for f in shown
        ]
        rows: list[list[InlineKeyboardButton]] = [filters]
        nav: list[InlineKeyboardButton] = []
        if n > 0:
            nav.append(self._button(locale, "page-prev", cb.my_week(n - 1, only)))
        if n < cb.WEEKS - 1:
            nav.append(self._button(locale, "page-next", cb.my_week(n + 1, only)))
        if nav:
            rows.append(nav)
        shalas = [
            InlineKeyboardButton(text=x.name, callback_data=cb.week(x.id, 0)) for x in s.shalas
        ]
        rows += [shalas[i : i + 2] for i in range(0, len(shalas), 2)]
        if not s.zone_known:
            city = settings_callbacks.encode(settings_callbacks.SettingsCallback("cities"))
            rows.append([self._button(locale, "settings-city-button", city)])
        return InlineKeyboardMarkup(inline_keyboard=rows)

    def _button(self, locale: Locale, key: str, data: str, **args: str) -> InlineKeyboardButton:
        return InlineKeyboardButton(text=self._t.t(locale, key, **args), callback_data=data)

    # Staff: the next 48 h

    async def _soon(self, principal: Principal, shala: UUID) -> Schedule | Screen:
        try:
            s = await self._c.schedule.execute(principal, shala, None, 4, skip=-1)
        except NotFound:
            return await self._links.overview(principal)
        if not s.manage:
            return self._week(principal, s, 0, "")
        return s

    async def pick(self, principal: Principal, shala: UUID) -> Screen:
        found = await self._soon(principal, shala)
        if isinstance(found, Screen):
            return found
        s, locale = found, principal.account.locale
        now = self._clock.now()
        soon = [
            o
            for o in s.occurrences
            if now <= o.starts_at <= now + timedelta(hours=PICK_HOURS)
        ]  # fmt: skip
        here = ZoneInfo(s.zone)
        rows = [
            [
                InlineKeyboardButton(
                    text=(
                        f"{'❌ ' if o.cancelled else ''}{self._day(locale, o.on)} "
                        f"{_hm(o.starts_at.astimezone(here))} {self._class(locale, o)}"
                    ),
                    callback_data=cb.occurrence("o", s.shala_id, o.class_id, o.key),
                )
            ]
            for o in soon
        ]
        rows.append([self._button(locale, "log-back", cb.week(s.shala_id, 0))])
        key = "class-pick-title" if soon else "class-pick-empty"
        return Screen(self._t.t(locale, key), InlineKeyboardMarkup(inline_keyboard=rows))

    async def _find(self, principal: Principal, tap: cb.Occurrence) -> Schedule | Screen:
        """The window around the occurrence (it may have moved up to 6 days)."""
        try:
            s = await self._c.schedule.execute(
                principal, tap.shala, tap.key - timedelta(days=6), 13
            )
        except NotFound:
            return await self._links.overview(principal)
        except BadWindow:
            return await self.week(principal, tap.shala, 0)
        return s

    async def occurrence(self, principal: Principal, tap: cb.Occurrence) -> Screen:
        locale = principal.account.locale
        found = await self._find(principal, tap)
        if isinstance(found, Screen):
            return found
        s = found
        o = next(
            (x for x in s.occurrences if x.class_id == tap.class_id and x.key == tap.key), None
        )
        if o is None:
            return await self.week(principal, tap.shala, 0, self._t.t(locale, "class-gone"))
        if not s.manage:
            return await self.week(principal, tap.shala, 0)
        day = self._day(locale, o.on)
        here = ZoneInfo(s.zone)
        what = f"{_hm(o.starts_at.astimezone(here))} {self._class(locale, o)}"
        on = (s.shala_id, o.class_id, o.key)
        match o.cancelled:
            case None:
                text = self._t.t(locale, "class-cancel-ask", **{"class": what}, day=day)
                action = self._button(locale, "class-cancel", cb.occurrence("x", *on))
            case Reason.CANCELLED:
                text = f"{day}\n{self._row(principal, s, o)}"
                action = self._button(locale, "class-restore", cb.occurrence("r", *on))
            case _:
                text = f"{day}\n{self._row(principal, s, o)}"
                action = self._button(locale, "class-hold", cb.occurrence("h", *on))
        rows = [[action], [self._button(locale, "log-back", cb.week(s.shala_id, 0))]]
        return Screen(text, InlineKeyboardMarkup(inline_keyboard=rows))

    async def change(self, principal: Principal, tap: cb.Occurrence) -> Screen:
        """x: cancel, r: restore, h: hold anyway; then the week, edited in place."""
        await asyncio.sleep(0)  # let `answered` send the answer before the write
        locale = principal.account.locale
        note = ""
        try:
            if tap.action == "r":
                await self._c.clear.execute(principal, tap.shala, tap.class_id, tap.key)
            else:
                status = OverrideStatus.CANCELLED if tap.action == "x" else OverrideStatus.HELD
                override = Override(on_date=tap.key, status=status)
                await self._c.override.execute(
                    principal, tap.shala, tap.class_id, tap.key, override, keep=True
                )
        except NotFound:
            note = self._t.t(locale, "class-gone")
        except NotAllowed:
            pass
        except InvalidClass:
            note = self._t.t(locale, "class-invalid")
        return await self.week(principal, tap.shala, 0, note)

    async def adopt(self, principal: Principal, shala: UUID) -> Screen:
        try:
            saved = await self._c.adopt.execute(principal, shala)
        except NotFound:
            return await self._links.overview(principal)
        account = saved.account if saved is not None else principal.account
        return await self._shalas.card(Principal(account), shala)

    def work(self, tap: cb.ClassTap, principal: Principal) -> Awaitable[Screen]:
        match tap:
            case cb.Week(shala, n):
                return self.week(principal, shala, n)
            case cb.Pick(shala):
                return self.pick(principal, shala)
            case cb.Occurrence("o", _, _, _):
                return self.occurrence(principal, tap)
            case cb.Occurrence():
                return self.change(principal, tap)
            case cb.AdoptDayOff(shala):
                return self.adopt(principal, shala)
            case cb.MyWeek(n, only):
                return self.my(principal, n, only)


def register_classes(router: Router, screens: ScheduleScreens) -> None:
    @router.message(Command("schedule"))
    async def on_schedule(message: Message, account: Account) -> SendMessage:  # pyright: ignore[reportUnusedFunction]
        screen = await screens.my(Principal(account), 0, "a")
        return message.answer(screen.text, reply_markup=screen.markup)

    @router.message(Command("classes"))
    async def on_classes(message: Message, account: Account) -> SendMessage:  # pyright: ignore[reportUnusedFunction]
        """Q137: My schedule with *I teach*."""
        screen = await screens.my(Principal(account), 0, "m")
        return message.answer(screen.text, reply_markup=screen.markup)

    @router.callback_query(F.data.startswith(f"{cb.PREFIX}:"))
    async def on_class(callback: CallbackQuery, account: Account) -> Reply | None:  # pyright: ignore[reportUnusedFunction]
        tap = cb.decode(callback.data)
        if tap is None:
            await answered(callback, nothing())
            return None
        screen = await answered(callback, screens.work(tap, Principal(account)))
        return show(callback, screen)
