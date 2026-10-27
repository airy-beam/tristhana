"""After-practice check-in screens (PR-06): K (mood, energy, effort) and T (body-and-mind
tags). Every tap saves at once and renders from the saved value; nothing is ever asked
twice, and ignoring the screens costs nothing.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from aiogram import F, Router
from aiogram.methods import SendMessage
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from tristhana.application.check_in_patch import CheckInPatch
from tristhana.application.policies import Principal
from tristhana.application.ports.i18n import Translator
from tristhana.application.ports.storage import StorageUnavailable
from tristhana.application.practice import DayNotPracticed
from tristhana.bots.telegram.check_in_callbacks import PREFIX, CheckInCallback, decode, encode
from tristhana.bots.telegram.screens import Reply, Screen, answered, button, show
from tristhana.domain.accounts import Account
from tristhana.domain.check_in import SCALE, CheckIn, CheckInTag
from tristhana.domain.days import DayStatus
from tristhana.domain.locale import Locale

if TYPE_CHECKING:
    from tristhana.bots.telegram.days import DayScreens
    from tristhana.bots.telegram.practice import PracticeScreens
    from tristhana.bots.telegram.runtime import CheckInUseCases


def register_check_in(router: Router, screens: CheckInScreens) -> None:
    @router.callback_query(F.data.startswith(f"{PREFIX}:"))
    async def on_check_in(callback: CallbackQuery, account: Account) -> Reply | None:  # pyright: ignore[reportUnusedFunction]
        cb = decode(callback.data)
        try:
            screen = await answered(callback, screens.handle(Principal(account), cb))
        except StorageUnavailable:  # the account loaded, then the database went away
            text = screens.t.t(account.locale, "error-temporary")
            return SendMessage(chat_id=callback.from_user.id, text=text)
        return show(callback, screen) if screen else None


def data(action: str, day: date, **kw: object) -> str:
    return encode(CheckInCallback(action, day, **kw))  # type: ignore[arg-type]


def mood_row(
    t: Translator, locale: Locale, day: date, current: int | None = None
) -> list[InlineKeyboardButton]:
    return _scale_row(t, locale, day, "mood", "checkin-mood-chip", current)


def _scale_row(
    t: Translator, locale: Locale, day: date, action: str, key: str, current: int | None
) -> list[InlineKeyboardButton]:
    return [
        InlineKeyboardButton(
            text=("✓ " if n == current else "") + t.t(locale, key, n=n),
            callback_data=data(action, day, value=0 if n == current else n),  # ✓ again clears
        )
        for n in SCALE
    ]


def summary_text(t: Translator, locale: Locale, c: CheckIn | None) -> str:
    """E.g. "🙂 · ⚡ energy 4/5 · 🔥 effort 3/5 · Light, Calm"; "" for none."""
    if c is None or c.is_empty():
        return ""
    parts: list[str] = []
    if c.mood is not None:
        parts.append(t.t(locale, "checkin-mood-chip", n=c.mood))
    if c.energy is not None:
        parts.append(t.t(locale, "checkin-summary-energy", n=c.energy))
    if c.effort is not None:
        parts.append(t.t(locale, "checkin-summary-effort", n=c.effort))
    if c.tags:
        tags = (t.t(locale, "checkin-tag", tag=tag.value) for tag in CheckInTag if tag in c.tags)
        parts.append(", ".join(tags))
    return " · ".join(parts)


class CheckInScreens:
    def __init__(
        self,
        check_ins: CheckInUseCases,
        translator: Translator,
        day_screens: DayScreens,
        practice: PracticeScreens,
    ) -> None:
        self._c = check_ins
        self.t = translator
        self._day_screens = day_screens
        self._practice = practice

    async def handle(self, principal: Principal, cb: CheckInCallback | None) -> Screen | None:
        if cb is None:
            return None
        try:
            return await self._handle(principal, cb)
        except DayNotPracticed:  # a stale keyboard, or the status changed in another message
            return await self._day_screens.status(
                principal, cb.day, note="practice-day-not-practiced"
            )

    async def _handle(self, principal: Principal, cb: CheckInCallback) -> Screen:
        day = cb.day
        match cb.action:
            case "open":
                return self.check_in(
                    principal, day, await self._practice.current_check_in(principal, day)
                )
            case "tags":
                return self.tags(
                    principal, day, await self._practice.current_check_in(principal, day)
                )
            case "mood" | "energy" | "effort":
                patch = CheckInPatch.of(**{cb.action: cb.value or None})
                saved = await self._c.save.execute(principal, day, patch)
                return self.check_in(principal, day, saved)
            case "tag":
                assert cb.tag is not None  # noqa: S101 - decoded with a tag
                saved = await self._c.set_tag.execute(principal, day, cb.tag, cb.on)
                return self.tags(principal, day, saved)
            case "done":
                return await self._practice.summary(principal, day, offer=False)
            case "clear":  # V without the mood row: just removed, so don't ask again
                await self._c.clear.execute(principal, day)
                return await self._practice.summary(principal, day, offer=False, mood_row=False)

    # Screen K: the scales.
    def check_in(self, principal: Principal, day: date, c: CheckIn | None) -> Screen:
        locale = principal.account.locale
        c = c or CheckIn()
        lines = self._day_screens.saved_lines(principal, day, DayStatus.PRACTICED)
        summary = summary_text(self.t, locale, c)
        if summary:
            lines.append(summary)
        lines.append(self.t.t(locale, "checkin-explain"))
        rows = [
            mood_row(self.t, locale, day, c.mood),
            _scale_row(self.t, locale, day, "energy", "checkin-energy-chip", c.energy),
            _scale_row(self.t, locale, day, "effort", "checkin-effort-chip", c.effort),
            [button(self.t, locale, "checkin-tags-open", data("tags", day))],
        ]
        last = [button(self.t, locale, "practice-done", data("done", day))]
        if not c.is_empty():
            last.append(button(self.t, locale, "checkin-clear", data("clear", day)))
        rows.append(last)
        return Screen("\n\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows))

    # Screen T: body and mind tags, 2 per row, body first.
    def tags(self, principal: Principal, day: date, c: CheckIn | None) -> Screen:
        locale = principal.account.locale
        chosen = c.tags if c else frozenset[CheckInTag]()
        chips = [
            InlineKeyboardButton(
                text=("✓ " if tag in chosen else "")
                + self.t.t(locale, "checkin-tag", tag=tag.value),
                callback_data=data("tag", day, tag=tag, on=tag not in chosen),
            )
            for tag in CheckInTag
        ]
        rows = [chips[i : i + 2] for i in range(0, len(chips), 2)]
        rows.append([button(self.t, locale, "log-back", data("open", day))])
        return Screen(
            self.t.t(locale, "checkin-tags-pick"), InlineKeyboardMarkup(inline_keyboard=rows)
        )
