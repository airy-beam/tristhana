"""Rest-period taps (WH-01 part 2, ADR-0023): the day count for a pause, "Other…" / Back,
"Keep the pause", and ending a pause early (from a day screen or `/remind`).

Every tap answers the callback first and edits the message in place. Other… / Back are a
pure render; starting or keeping a pause is one statement; ending early also re-reads
today's picker. A stale or forged tap changes nothing and shows nothing new.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery

from tristhana.application.policies import Principal
from tristhana.application.ports.i18n import DateArg, Translator
from tristhana.application.practice import DayNotPracticed
from tristhana.bots.telegram.days import DayScreens
from tristhana.bots.telegram.remind import RemindScreens
from tristhana.bots.telegram.rest_callbacks import PREFIX, RestCallback, decode
from tristhana.bots.telegram.runtime import RemindUseCases, RestUseCases
from tristhana.bots.telegram.screens import Reply, Screen, answered, show
from tristhana.domain.accounts import Account
from tristhana.domain.days import DateInFuture
from tristhana.domain.rest_periods import InvalidRestPeriod, RestPeriod


def register_rest(
    router: Router,
    rest: RestUseCases,
    remind: RemindUseCases,
    days: DayScreens,
    remind_screens: RemindScreens,
    translator: Translator,
) -> None:
    screens = RestScreens(rest, remind, days, remind_screens, translator)

    @router.callback_query(F.data.startswith(f"{PREFIX}:"))
    async def on_rest(callback: CallbackQuery, account: Account) -> Reply | None:  # pyright: ignore[reportUnusedFunction]
        cb = decode(callback.data)
        screen = await answered(callback, screens.handle(Principal(account), cb))
        return show(callback, screen) if screen else None


class RestScreens:
    def __init__(
        self,
        rest: RestUseCases,
        remind: RemindUseCases,
        days: DayScreens,
        remind_screens: RemindScreens,
        translator: Translator,
    ) -> None:
        self._rest = rest
        self._remind = remind
        self._days = days
        self._remind_screens = remind_screens
        self._t = translator

    async def handle(self, principal: Principal, cb: RestCallback | None) -> Screen | None:
        if cb is None:
            return None
        try:
            match cb.action:
                case "more" | "back":
                    assert cb.kind is not None  # noqa: S101 - decoded with a kind
                    more = cb.action == "more"
                    return self._days.question(principal, cb.day, cb.kind, cb.reminders_on, more)
                case "start":
                    return await self._start(principal, cb)
                case "keep":
                    return await self._keep(principal, cb)
                case "end":
                    return await self._end(principal, cb)
                case "end_remind":
                    await self._rest.end.execute(principal, cb.day)
                    return await self._remind_screens.settings(principal)
        except (InvalidRestPeriod, DateInFuture):
            return None  # stale (e.g. two days later) or forged: nothing changes

    async def _start(self, principal: Principal, cb: RestCallback) -> Screen:
        assert cb.kind is not None  # noqa: S101
        # One statement: the pause, and whether practice reminders are on (the wording).
        placed = await self._rest.start.execute(principal, cb.day, cb.days, cb.kind)
        return self._days.period_saved(
            principal, cb.day, cb.kind, placed.period, placed.practice_on
        )

    async def _keep(self, principal: Principal, cb: RestCallback) -> Screen | None:
        assert cb.kind is not None  # noqa: S101
        assert cb.end is not None  # noqa: S101
        assert cb.practiced is not None  # noqa: S101
        kept = await self._rest.restore.execute(principal, RestPeriod(cb.day, cb.end, cb.kind))
        if kept is None:
            return None  # over already, or no cut happened: nothing to keep
        practice = self._days.practice
        assert practice is not None  # noqa: S101 - wired by days.register
        # The day that cut it (carried in the callback) gets its details screen back,
        # without the undo.
        try:
            return await practice.details(principal, cb.practiced, kept=kept)
        except DayNotPracticed:  # changed since: today's picker with the line
            return await self._days.ended(principal, self._kept_line(principal, kept))

    def _kept_line(self, principal: Principal, kept: RestPeriod) -> str:
        locale = principal.account.locale
        label = self._days.label(locale, kept.kind)
        return self._t.t(locale, "pause-kept", label=label, until=DateArg(kept.end))

    async def _end(self, principal: Principal, cb: RestCallback) -> Screen:
        locale = principal.account.locale
        # One statement; it names the kind even when the period went entirely.
        ended = await self._rest.end.execute(principal, cb.day)
        lead = None
        if cb.reminders_on or ended.kind is not None:
            label = self._days.label(locale, ended.kind) if ended.kind is not None else ""
            lead = self._t.t(
                locale, "pause-ended", label=label, reminders="on" if cb.reminders_on else "off"
            )
        return await self._days.ended(principal, lead)
