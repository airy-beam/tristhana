"""Class attendance in the bot (SC-05, ADR-0039): "🙋 I was there…" for any member and the
staff "📋 Attendance…" roster. A mark is presence only: no tap here logs a day, and no one
gets a message (Q189). Taps are answered first and edited in place: claims, removals and
toggles patch the tapped message's own keyboard and counts line from the write's result, with
no re-read. Plain text, no `parse_mode`: names and titles are user text.
"""

import asyncio
from collections.abc import Awaitable
from datetime import date, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from tristhana.application.attendance import (
    AttendanceUseCases,
    AttendList,
    AttendRow,
    Roster,
)
from tristhana.application.classes import type_name
from tristhana.application.policies import NotAllowed, NotFound, Principal
from tristhana.application.ports.i18n import DateArg, Translator
from tristhana.bots.telegram import attendance_callbacks as cb
from tristhana.bots.telegram import callbacks as day_callbacks
from tristhana.bots.telegram import classes_callbacks
from tristhana.bots.telegram.screens import Reply, Screen, answered, nothing, show, zone_label
from tristhana.domain.accounts import Account
from tristhana.domain.attendance import (
    BOT_PAGE,
    AttendanceState,
    Counts,
    InvalidAttendance,
    NotAttendable,
)
from tristhana.domain.classes import Occurrence
from tristhana.domain.locale import Locale
from tristhana.domain.moon import Cities
from tristhana.domain.teacher_links import shown_name

DASH = "\u2013"
EMPTY, CLAIMED, CONFIRMED = "◻️", "🙋", "✅"
_MARK = {None: EMPTY, AttendanceState.CLAIMED: CLAIMED, AttendanceState.CONFIRMED: CONFIRMED}
_COUNTS_LINE = 2  # the roster's third line: title, shala, counts (each one line: `_one_line`)


def _one_line(text: str) -> str:
    """User text (a class title, a shala name) on one line, so the counts line keeps its index."""
    return " ".join(text.split())


def _mark_of(text: str) -> str | None:
    for mark in (EMPTY, CLAIMED, CONFIRMED):
        if text.startswith(mark + " "):
            return mark
    return None


class AttendanceScreens:
    def __init__(
        self, attendance: AttendanceUseCases, translator: Translator, cities: Cities
    ) -> None:
        self._a = attendance
        self._t = translator
        self._cities = cities

    def _button(self, locale: Locale, key: str, data: str, **args: object) -> InlineKeyboardButton:
        return InlineKeyboardButton(text=self._t.t(locale, key, **args), callback_data=data)  # type: ignore[arg-type]

    def _class(self, locale: Locale, o: Occurrence) -> str:
        name = type_name(self._t, locale, o.type)
        return f"{name} {_one_line(o.title)}" if o.title else name

    def _day(self, locale: Locale, day: date) -> str:
        return self._t.t(locale, "day-label", rel="other", date=DateArg(day))

    def _back(self, locale: Locale) -> InlineKeyboardButton:
        return self._button(locale, "log-back", classes_callbacks.my_week(0, "a"))

    def _label(self, locale: Locale, r: AttendRow, zone: str) -> str:
        """`Mon 9 Nov 06:00 Mysore · Ashtanga Almaty`, in my zone."""
        o = r.row.occurrence
        at = o.starts_at.astimezone(ZoneInfo(zone))
        return (
            f"{self._day(locale, at.date())} {at:%H:%M} {self._class(locale, o)}"
            f" · {_one_line(r.shala_name)}"
        )

    def _zone_line(self, locale: Locale, found: AttendList) -> str:
        """The times' zone, as on My schedule: `Times: 07:00 Almaty (UTC+5)`-style label."""
        city = self._cities.find(found.city)
        where = zone_label(self._t, locale, found.zone, found.today, city)
        key = "schedule-zone" if found.zone_known else "my-schedule-zone-unknown"
        return self._t.t(locale, key, zone=where)

    # A member: "🙋 I was there…"

    async def my_list(self, principal: Principal, note: str = "") -> Screen:
        locale = principal.account.locale
        found = await self._a.listing.execute(principal)
        rows: list[list[InlineKeyboardButton]] = []
        for r in found.rows:
            o, state = r.row.occurrence, r.row.attendance
            action: cb.Mine = "i" if state is None else "u"
            text = f"{_MARK[state]} {self._label(locale, r, found.zone)}"
            rows.append(
                [InlineKeyboardButton(text=text, callback_data=cb.mark(action, o.class_id, o.key))]
            )
        rows.append([self._back(locale)])
        key = "attend-me-title" if found.rows else "attend-me-none"
        text = self._t.t(locale, key)
        if found.rows:
            text += "\n" + self._zone_line(locale, found)
        if note:
            text = f"{note}\n\n{text}"
        return Screen(text, InlineKeyboardMarkup(inline_keyboard=rows))

    async def mine(
        self,
        principal: Principal,
        tap: cb.MyMark,
        markup: InlineKeyboardMarkup | None,
    ) -> Screen:
        """Claim or remove, then the tapped button is patched in place (no re-read)."""
        await asyncio.sleep(0)  # let `answered` send the answer before the write
        locale = principal.account.locale
        tapped = cb.mark(tap.action, tap.class_id, tap.key)
        button = _find(markup, tapped)
        if markup is None or button is None:
            return await self._mine_fallback(principal, tap)
        label = button.text.split(" ", 1)[1] if _mark_of(button.text) else button.text
        if tap.action == "u":
            await self._a.remove.execute(principal, tap.class_id, tap.key)
            patched = _patch(
                markup, tapped, f"{EMPTY} {label}", cb.mark("i", tap.class_id, tap.key)
            )
            text = self._t.t(locale, "attend-removed", what=label)
            return Screen(text, _without_log_day(patched))
        try:
            mark = await self._a.claim.execute(principal, tap.class_id, tap.key)
        except NotAttendable:
            return await self.my_list(principal, self._t.t(locale, "attend-not-open"))
        except NotFound:
            return await self.my_list(principal)
        patched = _patch(
            markup, tapped, f"{_MARK[mark.state]} {label}", cb.mark("u", tap.class_id, tap.key)
        )
        patched = _without_log_day(patched)
        if mark.log_day:  # Q196: not after Conference or Chanting
            open_day = day_callbacks.encode(day_callbacks.DayCallback("open", mark.day))
            log = self._button(locale, "attend-log-day", open_day)
            rows = [*patched.inline_keyboard[:-1], [log], patched.inline_keyboard[-1]]
            patched = InlineKeyboardMarkup(inline_keyboard=rows)
        text = self._t.t(locale, "attend-claimed", state=mark.state.value, what=label)
        return Screen(text, patched)

    async def _mine_fallback(self, principal: Principal, tap: cb.MyMark) -> Screen:
        """An old message with no keyboard to patch: write, then show the list."""
        try:
            if tap.action == "u":
                await self._a.remove.execute(principal, tap.class_id, tap.key)
            else:
                await self._a.claim.execute(principal, tap.class_id, tap.key)
        except (NotAttendable, NotFound):
            pass
        return await self.my_list(principal)

    # Staff: "📋 Attendance…"

    async def pick(self, principal: Principal) -> Screen:
        locale = principal.account.locale
        found = await self._a.listing.execute(principal, staff=True)
        rows: list[list[InlineKeyboardButton]] = []
        for r in found.rows:
            o, c = r.row.occurrence, r.row.counts or Counts(0, 0)
            counts = self._t.t(
                locale, "attend-row-counts", confirmed=c.confirmed, claimed=c.claimed
            )
            text = f"{self._label(locale, r, found.zone)} · {counts}"
            rows.append(
                [InlineKeyboardButton(text=text, callback_data=cb.roster("r", o.class_id, o.key))]
            )
        rows.append([self._back(locale)])
        key = "attend-staff-pick" if found.rows else "attend-staff-none"
        text = self._t.t(locale, key)
        if found.rows:
            text += "\n" + self._zone_line(locale, found)
        return Screen(text, InlineKeyboardMarkup(inline_keyboard=rows))

    async def roster(self, principal: Principal, class_id: UUID, key: date, page: int) -> Screen:
        locale = principal.account.locale
        try:
            r = await self._a.roster.execute(
                principal, class_id, key, offset=page * BOT_PAGE, limit=BOT_PAGE
            )
        except (NotFound, NotAllowed):
            return await self.pick(principal)
        return self._roster(locale, r, page)

    def _counts(self, locale: Locale, c: Counts) -> str:
        return self._t.t(locale, "attend-roster-counts", confirmed=c.confirmed, claimed=c.claimed)

    def _roster(self, locale: Locale, r: Roster, page: int) -> Screen:
        o = r.occurrence
        start = o.starts_at.astimezone(ZoneInfo(r.zone))
        end = start + (datetime.combine(o.on, o.end) - datetime.combine(o.on, o.start))
        if end < start:
            end += timedelta(days=1)
        where = zone_label(self._t, locale, r.zone, o.on, self._cities.find(r.city))
        title = self._t.t(
            locale,
            "attend-roster-title",
            **{"class": self._class(locale, o)},
            day=self._day(locale, o.on),
            time=f"{start:%H:%M}{DASH}{end:%H:%M} {where}",
        )
        lines = [title, _one_line(r.shala_name), self._counts(locale, r.counts)]
        if not r.attendable:
            lines.append(self._t.t(locale, "attend-not-open"))
        elif r.people:
            lines.append(self._t.t(locale, "attend-roster-hint"))
        if not r.people and page == 0:
            lines.append(self._t.t(locale, "attend-empty"))
        buttons: list[InlineKeyboardButton] = []
        for p in r.people:
            name = shown_name(p.name) or self._t.t(locale, "link-no-name")
            if p.staff:
                name += " " + self._t.t(locale, "attend-staff-tag")
            text = f"{_MARK[p.state]} {name}"
            if not r.attendable:
                data = cb.roster("r", o.class_id, o.key, page)
            else:
                action: cb.Toggle = "n" if p.state is AttendanceState.CONFIRMED else "y"
                data = cb.person(action, o.class_id, o.key, p.account_id, page)
            buttons.append(InlineKeyboardButton(text=text, callback_data=data))
        rows = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
        if r.attendable and r.counts.claimed:
            rows.append([self._confirm_all(locale, o.class_id, o.key, page, r.counts.claimed)])
        nav: list[InlineKeyboardButton] = []
        if page > 0:
            nav.append(
                self._button(locale, "page-prev", cb.roster("r", o.class_id, o.key, page - 1))
            )
        if r.more and page < cb.MAX_PAGE:
            nav.append(
                self._button(locale, "page-next", cb.roster("r", o.class_id, o.key, page + 1))
            )
        rows.append([*nav, self._button(locale, "log-back", cb.staff_pick())])
        return Screen("\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows))

    def _confirm_all(
        self, locale: Locale, class_id: UUID, key: date, page: int, n: int
    ) -> InlineKeyboardButton:
        return self._button(locale, "attend-confirm-all", cb.roster("a", class_id, key, page), n=n)

    async def toggle(
        self,
        principal: Principal,
        tap: cb.Person | cb.Roster,
        message: Message | None,
    ) -> Screen:
        """Mark or unmark one person, or confirm every claim; then the tapped message is
        patched from the write's counts. A closed occurrence or a stale tap re-renders."""
        await asyncio.sleep(0)
        locale = principal.account.locale
        present = [tap.account_id] if isinstance(tap, cb.Person) and tap.action == "y" else []
        removed = [tap.account_id] if isinstance(tap, cb.Person) and tap.action == "n" else []
        try:
            counts = await self._a.mark.execute(
                principal,
                tap.class_id,
                tap.key,
                present,
                removed,
                confirm_claims=isinstance(tap, cb.Roster),
            )
        except (NotAttendable, InvalidAttendance):
            return await self.roster(principal, tap.class_id, tap.key, tap.page)
        except (NotFound, NotAllowed):
            return await self.pick(principal)
        markup = None if message is None else message.reply_markup
        lines = [] if message is None or message.text is None else message.text.split("\n")
        if markup is None or len(lines) <= _COUNTS_LINE:
            return await self.roster(principal, tap.class_id, tap.key, tap.page)
        lines[_COUNTS_LINE] = self._counts(locale, counts)
        if isinstance(tap, cb.Person):
            patched = self._flip(markup, tap)
        else:
            patched = self._confirm_page(markup, tap)
        patched = self._with_confirm_all(locale, patched, tap, counts.claimed)
        return Screen("\n".join(lines), patched)

    def _flip(self, markup: InlineKeyboardMarkup, tap: cb.Person) -> InlineKeyboardMarkup:
        data = cb.person(tap.action, tap.class_id, tap.key, tap.account_id, tap.page)
        button = _find(markup, data)
        if button is None:
            return markup
        rest = button.text.split(" ", 1)[1] if _mark_of(button.text) else button.text
        if tap.action == "y":
            text, other = f"{CONFIRMED} {rest}", "n"
        else:
            text, other = f"{EMPTY} {rest}", "y"
        new = cb.person(other, tap.class_id, tap.key, tap.account_id, tap.page)  # type: ignore[arg-type]
        return _patch(markup, data, text, new)

    def _confirm_page(self, markup: InlineKeyboardMarkup, tap: cb.Roster) -> InlineKeyboardMarkup:
        """Every 🙋 button on the page becomes ✅ (its tap now unmarks)."""
        rows: list[list[InlineKeyboardButton]] = []
        for row in markup.inline_keyboard:
            out: list[InlineKeyboardButton] = []
            for b in row:
                found = cb.decode(b.callback_data)
                if isinstance(found, cb.Person) and _mark_of(b.text) == CLAIMED:
                    data = cb.person("n", found.class_id, found.key, found.account_id, found.page)
                    b = InlineKeyboardButton(
                        text=CONFIRMED + b.text[len(CLAIMED) :], callback_data=data
                    )
                out.append(b)
            rows.append(out)
        return InlineKeyboardMarkup(inline_keyboard=rows)

    def _with_confirm_all(
        self, locale: Locale, markup: InlineKeyboardMarkup, tap: cb.Person | cb.Roster, n: int
    ) -> InlineKeyboardMarkup:
        """The "Confirm all 🙋 (n)" row follows the counts: replaced, or gone at 0."""
        confirm = f"{cb.PREFIX}:a:"
        rows = [
            row
            for row in markup.inline_keyboard
            if not any((b.callback_data or "").startswith(confirm) for b in row)
        ]
        if n:
            at = len(rows) - 1  # before the nav/back row
            rows.insert(at, [self._confirm_all(locale, tap.class_id, tap.key, tap.page, n)])
        return InlineKeyboardMarkup(inline_keyboard=rows)

    def work(
        self, tap: cb.AttendanceTap, principal: Principal, message: Message | None
    ) -> Awaitable[Screen]:
        match tap:
            case cb.MyList():
                return self.my_list(principal)
            case cb.StaffPick():
                return self.pick(principal)
            case cb.MyMark():
                return self.mine(principal, tap, None if message is None else message.reply_markup)
            case cb.Roster("r", class_id, key, page):
                return self.roster(principal, class_id, key, page)
            case cb.Roster() | cb.Person():
                return self.toggle(principal, tap, message)


def _find(markup: InlineKeyboardMarkup | None, data: str) -> InlineKeyboardButton | None:
    if markup is None:
        return None
    for row in markup.inline_keyboard:
        for b in row:
            if b.callback_data == data:
                return b
    return None


def _patch(markup: InlineKeyboardMarkup, data: str, text: str, new: str) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(text=text, callback_data=new) if b.callback_data == data else b
            for b in row
        ]
        for row in markup.inline_keyboard
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _without_log_day(markup: InlineKeyboardMarkup) -> InlineKeyboardMarkup:
    """Drops an earlier "🧘 Log this day" row (a day-card button)."""
    rows = [
        row
        for row in markup.inline_keyboard
        if not any((b.callback_data or "").startswith(f"{day_callbacks.PREFIX}:") for b in row)
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def entry_buttons(t: Translator, locale: Locale, staff: bool) -> list[InlineKeyboardButton]:
    """My schedule's row: "🙋 I was there…" for any member, "📋 Attendance…" for staff."""
    out = [InlineKeyboardButton(text=t.t(locale, "attend-me-open"), callback_data=cb.my_list())]
    if staff:
        out.append(
            InlineKeyboardButton(
                text=t.t(locale, "attend-staff-open"), callback_data=cb.staff_pick()
            )
        )
    return out


def staff_button(t: Translator, locale: Locale) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text=t.t(locale, "attend-staff-open"), callback_data=cb.staff_pick()
    )


def register_attendance(router: Router, screens: AttendanceScreens) -> None:
    @router.callback_query(F.data.startswith(f"{cb.PREFIX}:"))
    async def on_attendance(callback: CallbackQuery, account: Account) -> Reply | None:  # pyright: ignore[reportUnusedFunction]
        tap = cb.decode(callback.data)
        if tap is None:
            await answered(callback, nothing())
            return None
        message = callback.message if isinstance(callback.message, Message) else None
        screen = await answered(callback, screens.work(tap, Principal(account), message))
        return show(callback, screen)
