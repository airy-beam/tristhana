"""Practice-details screens (PR-02 context, PR-03 length, PR-05 duration) after 🧘 Practiced.

The common path is 2 taps (🧘 → 🔁 same as last time). Every tap saves at once and edits
the message in place; picker screens need no DB access (the catalog is in memory).
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from tristhana.application.labels import PracticeLabels
from tristhana.application.policies import Principal
from tristhana.application.ports.i18n import DateArg, TimeArg, Translator
from tristhana.application.ports.practice import SavedPractice
from tristhana.application.practice import DayNotPracticed, NoPreviousPractice
from tristhana.application.practice_patch import PracticePatch
from tristhana.bots.telegram import callbacks as dcb
from tristhana.bots.telegram import check_in as ck
from tristhana.bots.telegram import rest_callbacks as acb
from tristhana.bots.telegram.practice_callbacks import (
    PREFIX,
    PracticeCallback,
    Range,
    decode,
    encode,
)
from tristhana.bots.telegram.remind import offer_row
from tristhana.bots.telegram.runtime import DayUseCases, PracticeUseCases, RemindUseCases
from tristhana.bots.telegram.screens import Reply, Screen, answered, button, show
from tristhana.domain.accounts import Account
from tristhana.domain.check_in import CheckIn, offer_mood_row
from tristhana.domain.days import DayLog, DayStatus
from tristhana.domain.locale import Locale
from tristhana.domain.moon import City
from tristhana.domain.practice import (
    FULL_PRIMARY,
    HALF_PRIMARY,
    SERIES_HALVES,
    SHORT,
    InvalidLength,
    InvalidPractice,
    Practice,
    PracticeContext,
    PracticeLength,
)
from tristhana.domain.progression import Celebration, CelebrationKind, Position, Track
from tristhana.domain.rest_periods import PAUSABLE, RestPeriod

if TYPE_CHECKING:
    from tristhana.bots.telegram.days import DayScreens
    from tristhana.bots.telegram.progression import ProgressionScreens

DURATIONS = ((30, 45, 60, 75), (90, 120, 150, 180))
GRID_PAGE = 16  # 2 columns x 8 rows
_CONTEXT_ROWS = (
    (PracticeContext.MYSORE, PracticeContext.LED),
    (PracticeContext.PRIVATE, PracticeContext.SELF),
)
_STATIC_KEYS = {
    SHORT: "preset-short",
    HALF_PRIMARY: "preset-half-primary",
    FULL_PRIMARY: "preset-full-primary",
}


def register_practice(router: Router, screens: PracticeScreens) -> None:
    @router.callback_query(F.data.startswith(f"{PREFIX}:"))
    async def on_practice(callback: CallbackQuery, account: Account) -> Reply | None:  # pyright: ignore[reportUnusedFunction]
        cb = decode(callback.data)
        screen = await answered(callback, screens.handle(Principal(account), cb))
        return show(callback, screen) if screen else None


def _data(action: str, day: date, **kw: object) -> str:
    return encode(PracticeCallback(action, day, **kw))  # type: ignore[arg-type]


def _found(saved: SavedPractice) -> tuple[CheckIn, ...]:
    return (saved.check_in,) if saved.check_in is not None else ()


def has_details(p: Practice | None) -> bool:
    return p is not None and any(
        v is not None for v in (p.context, p.length, p.duration_min, p.start_time)
    )


class PracticeScreens:
    def __init__(
        self,
        days: DayUseCases,
        practices: PracticeUseCases,
        translator: Translator,
        day_screens: DayScreens,
        remind: RemindUseCases | None = None,
    ) -> None:
        self._days = days
        self._p = practices
        self._t = translator
        self._day_screens = day_screens
        self._remind = remind
        self.labels = PracticeLabels(translator, practices.catalog, Track(practices.catalog))
        self.progression: ProgressionScreens | None = None  # PR-08, set by `register`

    async def handle(self, principal: Principal, cb: PracticeCallback | None) -> Screen | None:
        if cb is None:
            return None
        try:
            return await self._handle(principal, cb)
        except DayNotPracticed:  # a stale keyboard, or the status changed in another message
            return await self._day_screens.status(
                principal, cb.day, note="practice-day-not-practiced"
            )

    async def _handle(self, principal: Principal, cb: PracticeCallback) -> Screen:
        day = cb.day
        try:
            match cb.action:
                case "open":
                    return await self.details(principal, day)
                case "done":
                    return await self.summary(principal, day)
                case "context":
                    return await self._save(principal, day, PracticePatch.of(context=cb.context))
                case "online":
                    return await self._save(principal, day, PracticePatch.of(online=cb.flag))
                case "duration":
                    return await self._save(
                        principal, day, PracticePatch.of(duration_min=cb.number or None)
                    )
                case "length":
                    return await self._set_length(principal, cb)
                case "same":
                    copied = await self._p.copy_last.execute(principal, day)
                    return await self.details(
                        principal, day, practice=copied.practice, check_ins=_found(copied)
                    )
                case "clear":
                    await self._p.clear.execute(principal, day)
                    return await self.details(principal, day)  # re-read: still practiced?
                case "lengths":
                    return await self.lengths(principal, day)
                case "series":
                    return self.series_screen(principal.account.locale, day)
                case "range":
                    return self.range_screen(principal.account.locale, day, cb.number)
                case "grid":
                    assert cb.range is not None  # noqa: S101 - decoded with a range
                    return self.grid(principal.account.locale, day, cb.range, cb.number)
                case "durations":
                    return await self.durations(principal, day)
        except NoPreviousPractice:
            return await self.details(principal, day, note="practice-no-previous")
        except (InvalidLength, InvalidPractice):
            return await self.details(principal, day)  # forged or stale: just reshow

    async def _save(self, principal: Principal, day: date, patch: PracticePatch) -> Screen:
        saved = await self._p.save.execute(principal, day, patch)
        return await self.details(
            principal,
            day,
            practice=saved.practice,
            check_ins=_found(saved),
            hint=saved.new_asana_hint,
        )

    async def _set_length(self, principal: Principal, cb: PracticeCallback) -> Screen:
        assert cb.range is not None  # noqa: S101 - decoded with a range
        length = cb.range.length(self._p.catalog, cb.key)
        if length is None:
            raise InvalidLength("unknown series")
        return await self._save(principal, cb.day, PracticePatch.of(length=length))

    async def _current_day(self, principal: Principal, day: date) -> DayLog:
        """The day with its practice and check-in; raises `DayNotPracticed` when the day
        isn't Practiced. One statement."""
        view = await self._days.get.execute(principal, day, day)
        if not view.days or view.days[0].status is not DayStatus.PRACTICED:
            raise DayNotPracticed(day.isoformat())
        return view.days[0]

    async def _current(self, principal: Principal, day: date) -> Practice | None:
        practices = (await self._current_day(principal, day)).practices
        return practices[0] if practices else None

    async def current_check_in(self, principal: Principal, day: date) -> CheckIn | None:
        check_ins = (await self._current_day(principal, day)).check_ins
        return check_ins[0] if check_ins else None

    async def _check_in_part(
        self,
        principal: Principal,
        day: date,
        check_ins: tuple[CheckIn, ...] | None,
        mood_row: bool = True,
    ) -> tuple[list[str], list[list[InlineKeyboardButton]]]:
        """PR-06: the one-tap mood row (today or yesterday, setting on, no check-in yet),
        otherwise [✨ Check-in] plus the summary of one. `check_ins` None = not read (every
        caller passes it; the read is a fallback). `mood_row` False: never ask here (another
        question is on the screen, or the check-in was just removed)."""
        account = principal.account
        locale = account.locale
        if check_ins is None:
            check_ins = (await self._current_day(principal, day)).check_ins
        existing = check_ins[0] if check_ins else None
        today, _ = self._days.get.today(principal)
        if mood_row and offer_mood_row(day, today, existing, account.offer_check_in):
            return [self._t.t(locale, "checkin-prompt")], [ck.mood_row(self._t, locale, day)]
        lines = [ck.summary_text(self._t, locale, existing)] if existing else []
        return lines, [[self._button(locale, "checkin-edit", ck.data("open", day))]]

    # Screen P: what was saved + one-tap details.
    async def details(
        self,
        principal: Principal,
        day: date,
        practice: Practice | None = None,
        note: str | None = None,
        cut: RestPeriod | None = None,
        kept: RestPeriod | None = None,
        known: bool = False,
        check_ins: tuple[CheckIn, ...] | None = None,
        hint: Position | None = None,
        lead: list[str] | None = None,
    ) -> Screen:
        """`cut`: a rest period this 🧘 just cut (WH-01): a gentle line and "Keep the
        pause"; `kept`: it was just restored. `known`: `practice` is the stored value even
        when None, on a day just logged (no read, no check-in yet). `check_ins` None = not
        read yet. `hint`: ask "New asana? 🎉" about this stop (PR-08, only on the reply to a
        length tap); `lead`: lines on top (a celebration after "Yes, new", or a practice
        count reached by this 🧘, GM-01)."""
        if known:
            check_ins = check_ins or ()
        elif practice is None:
            logged = await self._current_day(principal, day)
            practice = logged.practices[0] if logged.practices else None
            check_ins = logged.check_ins
        locale = principal.account.locale
        lines = self._day_screens.saved_lines(principal, day, DayStatus.PRACTICED)
        if note:
            lines.insert(0, self._t.t(locale, note))
        rows: list[list[InlineKeyboardButton]] = []
        keep = self.keep_row(principal, day, cut)
        if keep:
            lines.insert(0, self.cut_line(principal, day, cut))  # type: ignore[arg-type]
            rows.append(keep)
        lines[:0] = lead or []  # a 🎉 goes on top (GM-01 spec §5)
        if kept is not None:
            label = self._t.t(locale, f"status-{kept.kind.value}")
            lines.insert(0, self._t.t(locale, "pause-kept", label=label, until=DateArg(kept.end)))
        if has_details(practice):
            lines.append(
                self.summary_text(locale, day, practice, self._days.get.home_city(principal))
            )
        else:
            lines.append(self._t.t(locale, "practice-details-prompt"))
        asking = False
        if hint is not None and self.progression is not None:
            asking = True
            question, answers = self.progression.ask_new(locale, day, hint)
            lines.append(question)
            rows.append(answers)
        if not has_details(practice):  # only then is "same as last time" offered
            last = (await self._p.presets.execute(principal, day)).last
            if last is not None and has_details(last):
                lines.append(
                    self._t.t(
                        locale,
                        "practice-last-time",
                        summary=self.summary_text(
                            locale, day, last, self._days.get.home_city(principal)
                        ),
                    )
                )
                rows.append([self._button(locale, "practice-same-as-last", _data("same", day))])
        current = practice.context if practice else None
        for pair in _CONTEXT_ROWS:
            rows.append(
                [
                    self._button(
                        locale,
                        f"context-{c.value}",
                        _data("context", day, context=c),
                        mark=c is current,
                    )
                    for c in pair
                ]
            )
        extras: list[InlineKeyboardButton] = []
        if current is not None and current is not PracticeContext.SELF:
            online = bool(practice and practice.online)
            extras.append(
                self._button(
                    locale, "practice-online", _data("online", day, flag=not online), mark=online
                )
            )
        extras.append(self._button(locale, "practice-duration", _data("durations", day)))
        rows.append(extras)
        rows.append([self._button(locale, "practice-length", _data("lengths", day))])
        # One question at a time: with "New asana?", the check-in is just ✨.
        check_in_lines, check_in_rows = await self._check_in_part(
            principal, day, check_ins, not asking
        )
        lines += check_in_lines
        rows += check_in_rows
        last_row = [self._button(locale, "practice-done", _data("done", day))]
        if has_details(practice):
            last_row.append(self._button(locale, "practice-clear", _data("clear", day)))
        rows.append(last_row)
        rows += self._day_screens.app_rows(principal)
        return Screen("\n\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows))

    def keep_row(
        self, principal: Principal, day: date, cut: RestPeriod | None
    ) -> list[InlineKeyboardButton] | None:
        """[⏸ Keep the pause] while the cut period still had days after `day` and isn't
        over yet; the callback carries the period itself (stateless)."""
        today, _ = self._days.get.today(principal)
        if cut is None or cut.kind not in PAUSABLE or cut.end <= day or cut.end < today:
            return None  # also an unreadable seal (plain rest): nothing to keep
        data = acb.encode(acb.RestCallback("keep", cut.start, cut.kind, end=cut.end, practiced=day))
        return [self._button(principal.account.locale, "pause-keep", data)]

    def cut_line(self, principal: Principal, day: date, cut: RestPeriod) -> str:
        locale = principal.account.locale
        today, _ = self._days.get.today(principal)
        rel = "today" if day == today else "yesterday" if day == today - timedelta(1) else "other"
        label = self._t.t(locale, f"status-{cut.kind.value}")
        return self._t.t(locale, "pause-cut", label=label, until=DateArg(cut.end), rel=rel)

    # Screen V: done, a compact summary (+ the one-time practice-reminder offer, PR-10).
    def count_lead(self, locale: Locale, celebrations: tuple[Celebration, ...]) -> list[str]:
        """The 🎉 line for a practice count a day write reached (GM-01 part 2)."""
        return [
            self._t.t(locale, "celebrate-practice-count", count=c.count)
            for c in celebrations
            if c.kind is CelebrationKind.PRACTICE_COUNT and c.count is not None
        ]

    async def summary(
        self,
        principal: Principal,
        day: date,
        practice: Practice | None = None,
        extra: str | None = None,
        offer: bool = True,
        cut: RestPeriod | None = None,
        check_ins: tuple[CheckIn, ...] | None = None,
        mood_row: bool = True,
        lead: list[str] | None = None,
    ) -> Screen:
        """`check_ins` None = not read yet. `mood_row` False: [✨ Check-in] only. `lead`:
        lines on top (a practice count reached, GM-01)."""
        if practice is None:
            logged = await self._current_day(principal, day)
            practice = logged.practices[0] if logged.practices else None
            check_ins = logged.check_ins
        locale = principal.account.locale
        lines = self._day_screens.saved_lines(principal, day, DayStatus.PRACTICED)
        keep = self.keep_row(principal, day, cut)
        if keep:
            lines.insert(0, self.cut_line(principal, day, cut))  # type: ignore[arg-type]
        lines[:0] = lead or []  # a 🎉 goes on top (GM-01 spec §5)
        if has_details(practice):
            lines.append(
                self.summary_text(locale, day, practice, self._days.get.home_city(principal))
            )
        if extra:
            lines.append(extra)
        today, _ = self._days.get.today(principal)
        rows = [
            [
                self._button(locale, "practice-details", _data("open", day)),
                self._button(locale, "log-change", dcb.encode(dcb.DayCallback("open", day))),
                self._button(locale, "log-another-day", dcb.encode(dcb.DayCallback("week", today))),
            ]
        ]
        if keep:
            rows.insert(0, keep)
        reminder_offer = False
        if offer and day == today and self._remind is not None:
            settings = await self._remind.settings.get(principal)
            reminder_offer = settings.practice.on is None  # never chosen: offered once
        # One question at a time: with the reminder offer, the check-in is just ✨.
        check_in_lines, check_in_rows = await self._check_in_part(
            principal, day, check_ins, mood_row and not reminder_offer
        )
        lines += check_in_lines
        rows += check_in_rows
        if reminder_offer:
            lines.append(self._t.t(locale, "remind-offer"))
            rows.append(offer_row(self._t, locale, day))
        return Screen("\n\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows))

    # Screen L: presets, recent lengths, "Other…".
    async def lengths(self, principal: Principal, day: date) -> Screen:
        locale = principal.account.locale
        presets = await self._p.presets.execute(principal, day)
        rows: list[list[InlineKeyboardButton]] = [
            [self._length_button(locale, day, SHORT)],
            [
                self._length_button(locale, day, HALF_PRIMARY),
                self._length_button(locale, day, FULL_PRIMARY),
            ],
        ]
        mine = [length for kind, length in presets.presets if kind == "mine"]
        rows[:0] = [[self._length_button(locale, day, length, mine=True)] for length in mine]
        for kind, length in presets.presets:
            if kind == "recent":
                rows.append([self._length_button(locale, day, length)])
        rows.append([self._button(locale, "preset-other", _data("series", day))])
        if self.progression is not None:
            rows.append([self._button(locale, "progression-open", self.progression.open_data)])
        rows.append([self._button(locale, "log-back", _data("open", day))])
        return Screen(self._t.t(locale, "length-pick"), InlineKeyboardMarkup(inline_keyboard=rows))

    def _length_button(
        self, locale: Locale, day: date, length: PracticeLength, mine: bool = False
    ) -> InlineKeyboardButton:
        key = _STATIC_KEYS.get(length)
        text = self._t.t(locale, key) if key else self.length_text(locale, length)
        if mine:
            text = self._t.t(locale, "preset-mine", length=text)
        rng = Range.of(self._p.catalog, length)
        assert rng is not None  # noqa: S101 - presets are validated lengths
        return InlineKeyboardButton(
            text=text, callback_data=_data("length", day, range=rng, key=length.end)
        )

    # Screen O: which series did the practice end with?
    def series_screen(self, locale: Locale, day: date) -> Screen:
        buttons: list[InlineKeyboardButton] = []
        for s in self._p.catalog.series:
            data = (
                _data("grid", day, range=Range(s.number, s.number), number=0)
                if s.number == 1
                else _data("range", day, number=s.number)
            )
            buttons.append(
                InlineKeyboardButton(text=self._series(locale, s.number), callback_data=data)
            )
        rows: list[list[InlineKeyboardButton]] = [
            buttons[i : i + 2] for i in range(0, len(buttons), 2)
        ]
        rows.append([self._button(locale, "log-back", _data("lengths", day))])
        return Screen(
            self._t.t(locale, "length-pick-series"), InlineKeyboardMarkup(inline_keyboard=rows)
        )

    # Screen S: only this series, or with the previous one (whole, or one half of it).
    def range_screen(self, locale: Locale, day: date, last: int) -> Screen:
        options = [Range(last, last), Range(last - 1, last)]
        previous = self._p.catalog.by_number(last - 1)
        if previous is not None and previous.slug in SERIES_HALVES:
            options += [Range(last - 1, last, "first_half"), Range(last - 1, last, "second_half")]
        rows = [
            [
                InlineKeyboardButton(
                    text=self._range_text(locale, r, only=True),
                    callback_data=_data("grid", day, range=r, number=0),
                )
            ]
            for r in options
        ]
        rows.append([self._button(locale, "log-back", _data("series", day))])
        return Screen(
            self._t.t(locale, "length-pick-range"), InlineKeyboardMarkup(inline_keyboard=rows)
        )

    # Screen G: the last asana of the last series (stop points only), paged.
    def grid(self, locale: Locale, day: date, rng: Range, page: int) -> Screen:
        series = self._p.catalog.by_number(rng.last)
        if series is None:
            return self.series_screen(locale, day)
        stops = series.stops
        pages = max(1, -(-len(stops) // GRID_PAGE))
        page = min(page, pages - 1)
        shown = stops[page * GRID_PAGE : (page + 1) * GRID_PAGE]
        rows = [
            [self._button(locale, "length-full-series", _data("length", day, range=rng, key=None))]
        ]
        buttons = [
            InlineKeyboardButton(
                text=s.label(locale), callback_data=_data("length", day, range=rng, key=s.key)
            )
            for s in shown
        ]
        rows += [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
        paging: list[InlineKeyboardButton] = []
        if page > 0:
            paging.append(
                InlineKeyboardButton(
                    text=self._t.t(locale, "page-prev"),
                    callback_data=_data("grid", day, range=rng, number=page - 1),
                )
            )
        if page < pages - 1:
            paging.append(
                InlineKeyboardButton(
                    text=self._t.t(locale, "page-next"),
                    callback_data=_data("grid", day, range=rng, number=page + 1),
                )
            )
        if paging:
            rows.append(paging)
        back = _data("series", day) if rng.last == 1 else _data("range", day, number=rng.last)
        rows.append([self._button(locale, "log-back", back)])
        text = self._t.t(
            locale, "length-pick-asana", series=self._series(locale, rng.last, lower=True)
        )
        return Screen(text, InlineKeyboardMarkup(inline_keyboard=rows))

    # Screen D: duration chips.
    async def durations(self, principal: Principal, day: date) -> Screen:
        practice = await self._current(principal, day)
        locale = principal.account.locale
        current = practice.duration_min if practice else None
        rows = [
            [
                InlineKeyboardButton(
                    text=("✓ " if m == current else "") + self._t.t(locale, "duration-min", min=m),
                    callback_data=_data("duration", day, number=m),
                )
                for m in row
            ]
            for row in DURATIONS
        ]
        rows.append(
            [
                self._button(locale, "duration-none", _data("duration", day, number=0)),
                self._button(locale, "log-back", _data("open", day)),
            ]
        )
        return Screen(
            self._t.t(locale, "duration-pick"), InlineKeyboardMarkup(inline_keyboard=rows)
        )

    # Text helpers.
    def summary_text(
        self, locale: Locale, day: date, p: Practice | None, place: City | None = None
    ) -> str:
        """E.g. "Mysore · Primary + intermediate → Pasasana · 90 min · 06:30 Almaty (UTC+5)"."""
        if p is None:
            return ""
        parts: list[str] = []
        if p.context is not None:
            parts.append(self._t.t(locale, f"context-{p.context.value}"))
            if p.online:
                parts.append(self._t.t(locale, "practice-online-suffix"))
        if p.length is not None:
            parts.append(self.length_text(locale, p.length))
        if p.duration_min:
            parts.append(self._t.t(locale, "duration-min", min=p.duration_min))
        if p.start_time is not None and p.timezone:
            parts.append(
                self._t.t(locale, "time-label", time=TimeArg(day, p.start_time, p.timezone, place))
            )
        return " · ".join(parts)

    def length_text(self, locale: Locale, length: PracticeLength) -> str:
        return self.labels.length(locale, length)

    def _range_text(self, locale: Locale, rng: Range, only: bool = False) -> str:
        return self.labels.range_text(locale, rng.first, rng.last, rng.first_part, only)

    def _series(self, locale: Locale, n: int, lower: bool = False) -> str:
        return self.labels.series(locale, n, lower)

    def _button(
        self, locale: Locale, key: str, data: str, mark: bool = False
    ) -> InlineKeyboardButton:
        return button(self._t, locale, key, data, mark)
