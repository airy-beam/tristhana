"""`/settings` (ID-06): language, time zone by city, links to the reminder screens. The
name, quiet hours and the daily cap are set in the Mini App."""

from datetime import date, time

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.methods import SendMessage
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    User,
    WebAppInfo,
)

from tristhana.application.policies import Principal
from tristhana.application.ports.i18n import TimeArg, Translator
from tristhana.bots.telegram import moon_callbacks as mcb
from tristhana.bots.telegram import remind_callbacks as rcb
from tristhana.bots.telegram.day_off import day_off_line, day_off_picker
from tristhana.bots.telegram.moon import moon_status
from tristhana.bots.telegram.remind import practice_status
from tristhana.bots.telegram.runtime import SettingsUseCases
from tristhana.bots.telegram.screens import Reply, Screen, answered, button, show
from tristhana.bots.telegram.settings_callbacks import PREFIX, SettingsCallback, decode, encode
from tristhana.domain.accounts import (
    Account,
    ExternalProfile,
    IdentityKey,
    IdentityProvider,
    InvalidTimezone,
    ProfilePatch,
)
from tristhana.domain.locale import Locale
from tristhana.domain.moon import City
from tristhana.domain.rest_days import InvalidDayOff

ZONE_PAGE = 12  # 2 columns x 6 rows
_LANGUAGES: tuple[tuple[Locale | None, str], ...] = (
    (None, "language-auto"),
    ("en", "language-en"),
    ("ru", "language-ru"),
)


def _data(**kw: object) -> str:
    return encode(SettingsCallback(**kw))  # type: ignore[arg-type]


def client_profile(user: User) -> ExternalProfile:
    """What Telegram says about the person now (for "As in Telegram")."""
    key = IdentityKey(IdentityProvider.TELEGRAM, str(user.id))
    return ExternalProfile(key, display_name=user.first_name, language_code=user.language_code)


def register_settings(
    router: Router, settings: SettingsUseCases, translator: Translator, miniapp_url: str = ""
) -> None:
    screens = SettingsScreens(settings, translator, miniapp_url)

    @router.message(Command("settings"))
    async def on_settings(message: Message, account: Account) -> SendMessage:  # pyright: ignore[reportUnusedFunction]
        screen = await screens.view(Principal(account))
        return message.answer(screen.text, reply_markup=screen.markup)

    @router.callback_query(F.data.startswith(f"{PREFIX}:"))
    async def on_settings_tap(callback: CallbackQuery, account: Account) -> Reply | None:  # pyright: ignore[reportUnusedFunction]
        cb = decode(callback.data)
        work = screens.handle(Principal(account), cb, client_profile(callback.from_user))
        screen = await answered(callback, work)
        return show(callback, screen) if screen else None


class SettingsScreens:
    def __init__(self, s: SettingsUseCases, translator: Translator, miniapp_url: str) -> None:
        self._s = s
        self._t = translator
        self._app = miniapp_url

    async def handle(
        self, principal: Principal, cb: SettingsCallback | None, client: ExternalProfile
    ) -> Screen | None:
        if cb is None:
            return None
        match cb.action:
            case "view":
                return await self.view(principal)
            case "zones":
                return self.zones(principal, cb.page)
            case "language":
                account = await self._s.profile.execute(
                    principal, ProfilePatch(locale=cb.locale), client
                )
                return await self.view(Principal(account))  # in the new language at once
            case "zone":
                city = self._s.cities.get(cb.slug)
                if city is None:
                    return await self.view(principal)
                try:
                    account = await self._s.profile.execute(
                        principal, ProfilePatch(timezone=city.location.tz), client
                    )
                except InvalidTimezone:
                    return await self.view(principal)
                return await self.view(Principal(account))
            case "day_off_pick":
                return self.day_off(principal)
            case "day_off":
                try:
                    saved = await self._s.day_off.execute(principal, cb.days_off)
                except InvalidDayOff:  # forged
                    return self.day_off(principal)
                return self.day_off(Principal(saved.account))  # pick a second one, or go back

    def day_off(self, principal: Principal) -> Screen:
        locale = principal.account.locale
        return day_off_picker(
            self._t,
            locale,
            principal.account.day_off.days,
            lambda days: _data(action="day_off", days_off=days),
            _data(action="day_off_pick"),
            button(self._t, locale, "settings-link", _data(action="view")),
        )

    async def view(self, principal: Principal) -> Screen:
        account = principal.account
        locale = account.locale
        settings = await self._s.settings.get(principal)
        today, _ = self._s.today(principal)
        zone = account.timezone
        city = self._s.cities.get(account.moon_location) or self._s.cities.default
        language = self._t.t(
            locale, "language-auto" if not account.locale_custom else f"language-{locale}"
        )
        lines = [
            self._t.t(locale, "settings-title"),
            self._t.t(locale, "settings-language-line", language=language),
            self._t.t(locale, "settings-zone-line", zone=self._zone_label(locale, zone, today))
            if zone
            else self._t.t(locale, "settings-zone-unset-line"),
            self._t.t(locale, "settings-moon-line", city=city.name(locale)),
            day_off_line(self._t, locale, account.day_off.days),
            moon_status(self._t, locale, settings, zone, today),
            practice_status(self._t, locale, settings, zone, today),
            self._t.t(locale, "settings-quiet-off-line", n=settings.daily_cap)
            if settings.quiet.start == settings.quiet.end  # start == end: no quiet hours
            else self._t.t(
                locale,
                "settings-quiet-line",
                start=f"{settings.quiet.start:%H:%M}",
                end=f"{settings.quiet.end:%H:%M}",
                n=settings.daily_cap,
            ),
        ]
        current = None if not account.locale_custom else locale
        rows = [
            [
                InlineKeyboardButton(
                    text=("✓ " if code == current else "") + self._t.t(locale, key),
                    callback_data=_data(action="language", locale=code),
                )
                for code, key in _LANGUAGES
            ],
            [
                button(self._t, locale, "settings-zone-button", _data(action="zones", page=0)),
                button(self._t, locale, "settings-day-off-button", _data(action="day_off_pick")),
            ],
            [
                button(self._t, locale, "settings-moon-link", mcb.encode(mcb.MoonCallback("view"))),
                button(
                    self._t, locale, "moon-reminders", mcb.encode(mcb.MoonCallback("reminders"))
                ),
            ],
            [
                button(
                    self._t, locale, "remind-practice-link", rcb.encode(rcb.RemindCallback("view"))
                )
            ],
        ]
        if self._app:
            rows.append(
                [
                    InlineKeyboardButton(
                        text=self._t.t(locale, "settings-open-app"),
                        web_app=WebAppInfo(url=self._app),
                    )
                ]
            )
        return Screen("\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows))

    def _zone_label(self, locale: Locale, zone: str, today: date) -> str:
        """The zone with its offset today: "Almaty (UTC+5)" (the time label minus the time)."""
        label = self._t.t(locale, "time-label", time=TimeArg(today, time(12), zone))
        return label.split(" ", 1)[1] if " " in label else label

    def _zone_city(self, principal: Principal) -> City | None:
        """The city to mark for the account's zone (only the zone is stored): the followed
        moon-day city when it shares the zone, else the city the zone is named after
        (Europe/Moscow → Moscow, not Krasnaya Polyana), else the first listed city in it."""
        zone = principal.account.timezone
        followed = self._s.cities.get(principal.account.moon_location) or self._s.cities.default
        if followed.location.tz == zone:
            return followed
        in_zone = [c for c in self._s.cities.all if c.location.tz == zone]
        named = (zone or "").rsplit("/", 1)[-1].replace("_", " ")
        return next((c for c in in_zone if c.name_en == named), in_zone[0] if in_zone else None)

    def zones(self, principal: Principal, page: int) -> Screen:
        locale = principal.account.locale
        # Every moon-day city, so Moscow, Kazan and Sochi are all there (one zone, three cities).
        cities = sorted(self._s.cities.all, key=lambda c: c.name(locale))
        pages = max(1, -(-len(cities) // ZONE_PAGE))
        page = min(page, pages - 1)
        shown = cities[page * ZONE_PAGE : (page + 1) * ZONE_PAGE]
        marked = self._zone_city(principal)
        buttons = [
            InlineKeyboardButton(
                text=("✓ " if c is marked else "") + c.name(locale),
                callback_data=_data(action="zone", slug=c.slug),
            )
            for c in shown
        ]
        rows = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
        paging: list[InlineKeyboardButton] = []
        if page > 0:
            paging.append(
                button(self._t, locale, "page-prev", _data(action="zones", page=page - 1))
            )
        if page < pages - 1:
            paging.append(
                button(self._t, locale, "page-next", _data(action="zones", page=page + 1))
            )
        if paging:
            rows.append(paging)
        rows.append([button(self._t, locale, "log-back", _data(action="view"))])
        return Screen(
            self._t.t(locale, "settings-pick-zone"), InlineKeyboardMarkup(inline_keyboard=rows)
        )
