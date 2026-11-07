"""`/start` (UI-01): one message that greets and asks about today right away. The same for
new and returning people (stateless), so it doubles as a home screen.

    o1:l:en / o1:l:ru   switch the language (an explicit choice, ID-06)
"""

from typing import TYPE_CHECKING

from aiogram import F, Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.methods import SendMessage
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from tristhana.application.policies import Principal
from tristhana.application.ports.i18n import Translator
from tristhana.bots.telegram.days import DayScreens
from tristhana.bots.telegram.runtime import SettingsUseCases
from tristhana.bots.telegram.screens import Reply, Screen, answered, app_button, nothing, show
from tristhana.bots.telegram.settings import client_profile
from tristhana.bots.telegram.tour_callbacks import Origin, step
from tristhana.domain.accounts import Account, ExternalProfile, ProfilePatch
from tristhana.domain.locale import LOCALES, Locale
from tristhana.domain.teacher_links import parse_invite

if TYPE_CHECKING:
    from tristhana.bots.telegram.teacher_links import LinkScreens

PREFIX = "o1"


def decode(data: str | None) -> Locale | None:
    """The language to switch to, or None for anything malformed or from another version."""
    parts = (data or "").split(":")
    if len(parts) == 3 and parts[:2] == [PREFIX, "l"] and parts[2] in LOCALES:
        return parts[2]  # type: ignore[return-value]
    return None


def encode(locale: Locale) -> str:
    return f"{PREFIX}:l:{locale}"


def register_start(
    router: Router, screens: "StartScreens", invites: "LinkScreens | None" = None
) -> None:
    # Only `t_<code>` (ID-04) means anything; no payload is ever logged.
    @router.message(CommandStart())
    async def on_start(  # pyright: ignore[reportUnusedFunction]
        message: Message, account: Account, command: CommandObject
    ) -> SendMessage:
        principal = Principal(account)
        code = parse_invite(command.args)
        if code is not None and invites is not None:
            screen = await invites.invited(principal, code)
        else:
            screen = await screens.start(principal)
        return message.answer(screen.text, reply_markup=screen.markup)

    @router.callback_query(F.data.startswith(f"{PREFIX}:"))
    async def on_language(callback: CallbackQuery, account: Account) -> Reply | None:  # pyright: ignore[reportUnusedFunction]
        locale = decode(callback.data)
        if locale is None:
            await answered(callback, nothing())
            return None
        work = screens.switch(Principal(account), locale, client_profile(callback.from_user))
        screen = await answered(callback, work)
        return show(callback, screen)


def tour_button(t: Translator, locale: Locale, origin: Origin) -> InlineKeyboardButton:
    """Opens the quick tour (UI-02) on its first step."""
    return InlineKeyboardButton(text=t.t(locale, "tour-open"), callback_data=step(1, origin))


class StartScreens:
    def __init__(
        self, days: DayScreens, settings: SettingsUseCases, translator: Translator, app: str
    ) -> None:
        self._days = days
        self._s = settings
        self._t = translator
        self._app = app

    async def start(
        self,
        principal: Principal,
        lead: str | None = None,
        lead_row: list[InlineKeyboardButton] | None = None,
    ) -> Screen:
        """Greeting + "how was today?" + today's status grid (✓ on today's status). An
        answered invite (ID-04) puts its line and button on top."""
        locale = principal.account.locale
        today, _ = self._days.today(principal)
        picker, auto = await self._days.today_picker(principal)
        text = "\n\n".join(
            [
                *([lead] if lead else []),
                self._t.t(locale, "start-greeting"),
                *([auto] if auto else []),  # today shows as auto-rest (PR-09)
                self._t.t(locale, "start-prompt", day=self._days.day(locale, today, today)),
            ]
        )
        other: Locale = next(code for code in LOCALES if code != locale)  # type: ignore[assignment]  # two languages today
        last: list[InlineKeyboardButton] = [
            InlineKeyboardButton(
                text=self._t.t(
                    locale, "start-switch-language", language=self._t.t(other, f"language-{other}")
                ),
                callback_data=encode(other),
            )
        ]
        if self._app:
            last.append(app_button(self._t, locale, self._app))
        rows = [
            *([lead_row] if lead_row else []),
            *picker.markup.inline_keyboard,
            last,
            [tour_button(self._t, locale, "s")],
        ]
        return Screen(text, InlineKeyboardMarkup(inline_keyboard=rows))

    async def switch(self, principal: Principal, locale: Locale, client: ExternalProfile) -> Screen:
        account = await self._s.profile.execute(principal, ProfilePatch(locale=locale), client)
        return await self.start(Principal(account))  # the same message, in the new language
