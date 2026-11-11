"""`/help` and the quick tour (UI-02): a side door, offered under /start and /help. /help
also links to the public guide (UI-05) in the person's language, when its address is set. One
message edited in place; ✓ Done on every step goes back to where the tour was opened.
Static text, so a step costs nothing beyond the middleware's account read."""

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.methods import SendMessage
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from tristhana.application.policies import Principal
from tristhana.application.ports.i18n import Translator
from tristhana.bots.telegram.screens import Reply, Screen, answered, app_button, nothing, show
from tristhana.bots.telegram.start import StartScreens, tour_button
from tristhana.bots.telegram.tour_callbacks import (
    PREFIX,
    STEP_KEYS,
    STEPS,
    Origin,
    TourTap,
    decode,
    done,
    step,
)
from tristhana.domain.accounts import Account
from tristhana.domain.locale import Locale


def register_tour(
    router: Router,
    start: StartScreens,
    translator: Translator,
    miniapp_url: str = "",
    site_url: str = "",
) -> None:
    screens = TourScreens(start, translator, miniapp_url, site_url)

    @router.message(Command("help"))
    async def on_help(message: Message, account: Account) -> SendMessage:  # pyright: ignore[reportUnusedFunction]
        screen = screens.help(account.locale)
        return message.answer(screen.text, reply_markup=screen.markup)

    @router.callback_query(F.data.startswith(f"{PREFIX}:"))
    async def on_tour(callback: CallbackQuery, account: Account) -> Reply | None:  # pyright: ignore[reportUnusedFunction]
        tap = decode(callback.data)
        if tap is None:
            await answered(callback, nothing())
            return None
        screen = await answered(callback, screens.tapped(Principal(account), tap))
        return show(callback, screen)


class TourScreens:
    def __init__(
        self, start: StartScreens, translator: Translator, app: str, site: str = ""
    ) -> None:
        self._start = start
        self._t = translator
        self._app = app
        self._site = site

    def help(self, locale: Locale) -> Screen:
        rows = [[tour_button(self._t, locale, "h")]]
        if self._site:
            # The guide's English pages are at the root, the Russian ones under /ru/.
            path = "/ru/" if locale == "ru" else "/"
            rows.append(
                [InlineKeyboardButton(text=self._t.t(locale, "help-guide"), url=self._site + path)]
            )
        return Screen(self._t.t(locale, "help-text"), InlineKeyboardMarkup(inline_keyboard=rows))

    async def tapped(self, principal: Principal, tap: TourTap) -> Screen:
        locale = principal.account.locale
        if tap.n is not None:
            return self.step(locale, tap.n, tap.origin)
        if tap.origin == "s":
            return await self._start.start(principal)
        return self.help(locale)

    def step(self, locale: Locale, n: int, origin: Origin) -> Screen:
        progress = self._t.t(locale, "tour-progress", n=n, total=STEPS)
        text = f"{progress}\n{self._t.t(locale, STEP_KEYS[n - 1])}"
        return Screen(text, InlineKeyboardMarkup(inline_keyboard=self._rows(locale, n, origin)))

    def _rows(self, locale: Locale, n: int, origin: Origin) -> list[list[InlineKeyboardButton]]:
        def button(key: str, data: str) -> InlineKeyboardButton:
            return InlineKeyboardButton(text=self._t.t(locale, key), callback_data=data)

        back = [button("tour-back", step(n - 1, origin))] if n > 1 else []
        finish = button("tour-done", done(origin))
        if n < STEPS:
            return [[*back, button("tour-next", step(n + 1, origin))], [finish]]
        rows = [[*back, finish]]
        if self._app:
            rows.append([app_button(self._t, locale, self._app)])
        return rows
