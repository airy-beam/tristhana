"""Progression screens (PR-08): G "🧘 My asanas" (/asanas, a button on the length screen L),
the pickers, and the celebrations (GM-01 part 1) on the reply to the person's own tap. The
"New asana? 🎉" question on P lives in `practice.py`; its answers come here.

Set and change never celebrate; a new asana celebrates only the first time past everything
held before. Every tap answers first and edits in place (ADR-0008).
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.methods import SendMessage
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from tristhana.application.policies import Principal
from tristhana.application.ports.i18n import Translator
from tristhana.application.ports.progression import ProgressionView
from tristhana.application.ports.storage import StorageUnavailable
from tristhana.application.progression import ChangeResult, NotLatest, ProgressionChanged
from tristhana.bots.telegram.practice import GRID_PAGE
from tristhana.bots.telegram.progression_callbacks import (
    PREFIX,
    ProgressionCallback,
    decode,
    encode,
    position,
)
from tristhana.bots.telegram.screens import Reply, Screen, answered, button, show
from tristhana.domain.accounts import Account
from tristhana.domain.locale import Locale
from tristhana.domain.progression import (
    STANDING_ONLY,
    Celebration,
    CelebrationKind,
    InvalidProgression,
    NotForward,
    Position,
    Progression,
    ProgressionNotSet,
    position_length,
    shows_traditional,
)

if TYPE_CHECKING:
    from tristhana.bots.telegram.days import DayScreens
    from tristhana.bots.telegram.practice import PracticeScreens
    from tristhana.bots.telegram.runtime import ProgressionUseCases


def data(action: str, **kw: object) -> str:
    return encode(ProgressionCallback(action, **kw))  # type: ignore[arg-type]


def register_progression(router: Router, screens: ProgressionScreens) -> None:
    @router.message(Command("asanas"))
    async def on_asanas(message: Message, account: Account) -> SendMessage:  # pyright: ignore[reportUnusedFunction]
        try:
            screen = await screens.open(Principal(account))
        except StorageUnavailable:
            return message.answer(screens.t.t(account.locale, "error-temporary"))
        return message.answer(screen.text, reply_markup=screen.markup)

    @router.callback_query(F.data.startswith(f"{PREFIX}:"))
    async def on_progression(callback: CallbackQuery, account: Account) -> Reply | None:  # pyright: ignore[reportUnusedFunction]
        cb = decode(callback.data)
        try:
            screen = await answered(callback, screens.handle(Principal(account), cb))
        except StorageUnavailable:  # the account loaded, then the database went away
            text = screens.t.t(account.locale, "error-temporary")
            return SendMessage(chat_id=callback.from_user.id, text=text)
        return show(callback, screen) if screen else None


class ProgressionScreens:
    def __init__(
        self,
        progression: ProgressionUseCases,
        translator: Translator,
        day_screens: DayScreens,
        practice: PracticeScreens,
    ) -> None:
        self._g = progression
        self.t = translator
        self._day_screens = day_screens
        self._practice = practice
        self._track = progression.track
        self.open_data = data("open")

    async def handle(self, principal: Principal, cb: ProgressionCallback | None) -> Screen | None:
        if cb is None:
            return None
        locale = principal.account.locale
        catalog = self._track.catalog
        try:
            match cb.action:
                case "open":
                    return await self.open(principal)
                case "give":
                    target = position(catalog, cb.number, cb.key)
                    if target is None:
                        return None
                    return await self._give(principal, target, cb.day)
                case "set":
                    target = position(catalog, cb.number, cb.key)
                    if target is None:
                        return None
                    result = await self._g.set.execute(principal, target)
                    return await self.open(principal, [self._saved_line(locale, target)], result)
                case "item":
                    assert cb.key is not None  # noqa: S101 - decoded with a key
                    result = await self._g.item.execute(principal, cb.key, bool(cb.number))
                    lines = self.celebration_lines(locale, result.celebrations)
                    return await self.open(principal, lines, result)
                case "undo":
                    view = await self._g.undo.execute(principal, cb.number)
                    lines = [self.t.t(locale, "progression-undone")]
                    return await self.open(principal, lines, view=view)
                case "not_new":
                    target = position(catalog, cb.number, cb.key)
                    if target is None or cb.day is None:
                        return None
                    await self._g.dismiss.execute(principal, target)
                    return await self._practice.details(principal, cb.day)
                case "series":
                    return self.series_picker(locale)
                case "change":
                    return await self.change_screen(principal)
                case "grid":
                    return await self.grid(principal, cb.mode, cb.number, cb.page)
        except NotForward:  # a stale keyboard or a double tap
            return await self.open(principal, [self.t.t(locale, "progression-already")])
        except (ProgressionNotSet, ProgressionChanged, InvalidProgression, NotLatest):
            return await self.open(principal)  # stale or forged: show the current state

    async def _give(self, principal: Principal, target: Position, day: date | None) -> Screen:
        locale = principal.account.locale
        if day is None:
            result = await self._g.give.execute(principal, target)
            return await self.open(principal, self._given_lines(locale, result), result)
        try:
            result = await self._g.give.execute(principal, target, on=day)
        except NotForward:
            return await self._practice.details(principal, day)
        lines = self._given_lines(locale, result)
        return await self._practice.details(principal, day, lead=lines)

    def _given_lines(self, locale: Locale, result: ChangeResult) -> list[str]:
        if result.celebrations:
            return self.celebration_lines(locale, result.celebrations)
        after = result.event.after if result.event else None
        return [self.t.t(locale, "progression-back", asana=self.stop_label(locale, after))]

    # Screen G.
    async def open(
        self,
        principal: Principal,
        lead: list[str] | None = None,
        result: ChangeResult | None = None,
        view: ProgressionView | None = None,
    ) -> Screen:
        """`result`: the change just made (its view is current, so no read; an Undo button
        for its event). `view`: a state already read (after an undo); unset, only the
        suggestion is read."""
        locale = principal.account.locale
        suggested = None
        if result is not None:
            view = result.view
        if view is None:
            found = await self._g.get.execute(principal)
            view, suggested = found.view, found.suggested
        elif view.progression is None and result is None:
            suggested = await self._g.get.suggest(principal)
        progression = view.progression
        lines = [self.t.t(locale, "progression-title"), *(lead or [])]
        rows: list[list[InlineKeyboardButton]] = []
        if progression is None:
            lines.append(self.t.t(locale, "progression-unset"))
            if suggested is not None:
                text = self.t.t(
                    locale, "progression-suggest", length=self.position_text(locale, suggested)
                )
                rows.append([self._set_button(text, suggested)])
            rows.append([self._button(locale, "progression-choose", data("series", mode="s"))])
            standing = self.t.t(locale, "progression-standing-only")
            rows.append([self._set_button(standing, STANDING_ONLY)])
        else:
            lines += self._state_lines(locale, progression)
            rows += self._state_rows(locale, progression)
        if result is not None and result.event is not None:
            undo = data("undo", number=result.event.id)
            rows.insert(0, [self._button(locale, "progression-undo", undo)])
        rows += self._day_screens.app_rows(principal)
        return Screen("\n\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows))

    def _state_lines(self, locale: Locale, progression: Progression) -> list[str]:
        length = self.position_text(locale, progression.position)
        lines = [self.t.t(locale, "progression-current", length=length)]
        given = [i for i in self._track.items if i.key in progression.items]
        if given:
            items = ", ".join(self.item_label(locale, i.key) for i in given)
            lines.append(self.t.t(locale, "progression-items", items=items))
        return lines

    def _state_rows(
        self, locale: Locale, progression: Progression
    ) -> list[list[InlineKeyboardButton]]:
        rows: list[list[InlineKeyboardButton]] = []
        nxt = self._track.next(progression.position)
        if nxt is not None:
            text = self.t.t(locale, "progression-new", asana=self.stop_label(locale, nxt))
            rows.append([self._give_button(text, nxt)])
        if len(self._track.after(progression.position)) > 1:
            more = data("grid", mode="g", number=0, page=0)
            rows.append([self._button(locale, "progression-new-other", more)])
        items = [
            InlineKeyboardButton(
                text=self.t.t(locale, "progression-item-new", item=self.item_label(locale, i.key)),
                callback_data=data("item", key=i.key, number=1),
            )
            for i in self._track.items
            if i.key not in progression.items
        ]
        rows += [items[i : i + 2] for i in range(0, len(items), 2)]
        rows.append([self._button(locale, "progression-change", data("change"))])
        return rows

    # ✏️ Change: the series picker, standing only, and item toggles.
    async def change_screen(self, principal: Principal) -> Screen:
        locale = principal.account.locale
        found = await self._g.get.execute(principal)
        progression = found.view.progression
        screen = self.series_picker(locale)
        rows = list(screen.markup.inline_keyboard[:-1])
        if progression is not None:
            for i in self._track.items:
                given = i.key in progression.items
                text = ("✓ " if given else "") + self.item_label(locale, i.key)
                toggle = data("item", key=i.key, number=0 if given else 1)
                rows.append([InlineKeyboardButton(text=text, callback_data=toggle)])
        rows.append([self._button(locale, "log-back", data("open"))])
        text = self.t.t(locale, "progression-change-explain")
        return Screen(text, InlineKeyboardMarkup(inline_keyboard=rows))

    def series_picker(self, locale: Locale) -> Screen:
        buttons = [
            InlineKeyboardButton(
                text=self.t.t(
                    locale,
                    "progression-series-button",
                    series=self.t.t(locale, "series-name", n=s.number),
                ),
                callback_data=data("grid", mode="s", number=s.number, page=0),
            )
            for s in self._track.catalog.series
        ]
        rows = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
        standing = self.t.t(locale, "progression-standing-only")
        rows.append([self._set_button(standing, STANDING_ONLY)])
        rows.append([self._button(locale, "log-back", data("open"))])
        text = self.t.t(locale, "progression-pick-series")
        return Screen(text, InlineKeyboardMarkup(inline_keyboard=rows))

    async def grid(self, principal: Principal, mode: str, number: int, page: int) -> Screen:
        """Set mode: every stop of series `number`. Give mode: the later stops."""
        locale = principal.account.locale
        if mode == "s":
            series = self._track.catalog.by_number(number)
            if series is None:
                return self.series_picker(locale)
            stops = [Position(series.slug, s.key) for s in series.stops]
            text = self.t.t(
                locale, "progression-pick-asana", series=self.t.t(locale, "series-lower", n=number)
            )
            back = data("series", mode="s")
        else:
            found = await self._g.get.execute(principal)
            if found.view.progression is None:
                return await self.open(principal)
            stops = list(self._track.after(found.view.progression.position))
            text, back = self.t.t(locale, "progression-pick-new"), data("open")
        pages = max(1, -(-len(stops) // GRID_PAGE))
        page = min(page, pages - 1)
        shown = stops[page * GRID_PAGE : (page + 1) * GRID_PAGE]
        make = self._set_button if mode == "s" else self._give_button
        buttons = [make(self.stop_label(locale, p), p) for p in shown]
        rows = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
        paging: list[InlineKeyboardButton] = []
        if page > 0:
            prev = data("grid", mode=mode, number=number, page=page - 1)
            paging.append(
                InlineKeyboardButton(text=self.t.t(locale, "page-prev"), callback_data=prev)
            )
        if page < pages - 1:
            nxt = data("grid", mode=mode, number=number, page=page + 1)
            paging.append(
                InlineKeyboardButton(text=self.t.t(locale, "page-next"), callback_data=nxt)
            )
        if paging:
            rows.append(paging)
        rows.append([self._button(locale, "log-back", back)])
        return Screen(text, InlineKeyboardMarkup(inline_keyboard=rows))

    # Text helpers (also used by P).
    def celebration_lines(self, locale: Locale, found: tuple[Celebration, ...]) -> list[str]:
        lines: list[str] = []
        for c in found:
            match c.kind:
                case CelebrationKind.NEW_ASANA:
                    asana = self.stop_label(locale, Position(c.series, c.key))
                    if c.first is not None:
                        first = self.stop_label(locale, c.first)
                        lines.append(
                            self.t.t(locale, "celebrate-new-asanas", **{"from": first}, asana=asana)
                        )
                    else:
                        lines.append(self.t.t(locale, "celebrate-new-asana", asana=asana))
                case CelebrationKind.SERIES_COMPLETE | CelebrationKind.SERIES_BEGINS:
                    series = self._track.catalog.get(c.series or "")
                    if series is None:
                        continue
                    traditional = "none"
                    if shows_traditional(series) and series.traditional is not None:
                        names = series.traditional
                        traditional = names.ru if locale == "ru" else names.latin
                    key = (
                        "celebrate-series-complete"
                        if c.kind is CelebrationKind.SERIES_COMPLETE
                        else "celebrate-series-begins"
                    )
                    lines.append(
                        self.t.t(
                            locale,
                            key,
                            series=self.t.t(locale, "series-name", n=series.number),
                            traditional=traditional,
                        )
                    )
                case CelebrationKind.ITEM:
                    label = self.item_label(locale, c.key or "")
                    lines.append(self.t.t(locale, "celebrate-item", item=label))
        return lines

    def position_text(self, locale: Locale, p: Position) -> str:
        length = position_length(self._track, p)
        if length is not None:
            return self._practice.length_text(locale, length)
        if p == STANDING_ONLY:
            return self.t.t(locale, "progression-standing-only")
        return self.stop_label(locale, p)  # stale: still readable

    def item_label(self, locale: Locale, key: str) -> str:
        return self._practice.labels.item(locale, key)

    def stop_label(self, locale: Locale, p: Position | None) -> str:
        if p is None:
            return ""
        return self._practice.labels.stop(locale, p.series or "", p.key or "")

    def _saved_line(self, locale: Locale, target: Position) -> str:
        if target == STANDING_ONLY:
            return self.t.t(locale, "progression-saved-standing")
        return self.t.t(locale, "progression-saved", asana=self.stop_label(locale, target))

    def ask_new(
        self, locale: Locale, day: date, target: Position
    ) -> tuple[str, list[InlineKeyboardButton]]:
        """P's question after a length tap past the last asana, with its two answers."""
        series = self._track.series(target)
        number = series.number if series else 0
        text = self.t.t(locale, "progression-ask-new", asana=self.stop_label(locale, target))
        yes = data("give", number=number, key=target.key, day=day)
        no = data("not_new", number=number, key=target.key, day=day)
        return text, [
            self._button(locale, "progression-ask-yes", yes),
            self._button(locale, "progression-ask-no", no),
        ]

    def _set_button(self, text: str, p: Position) -> InlineKeyboardButton:
        series = self._track.series(p)
        return InlineKeyboardButton(
            text=text, callback_data=data("set", number=series.number if series else 0, key=p.key)
        )

    def _give_button(self, text: str, p: Position) -> InlineKeyboardButton:
        series = self._track.series(p)
        return InlineKeyboardButton(
            text=text, callback_data=data("give", number=series.number if series else 0, key=p.key)
        )

    def _button(self, locale: Locale, key: str, payload: str) -> InlineKeyboardButton:
        return button(self.t, locale, key, payload)
