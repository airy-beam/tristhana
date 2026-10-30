"""`/settings` (ID-06): language, "🏙 My city" (which sets the zone, MD-04 / ADR-0029), links
to the reminder screens. The name, quiet hours and the daily cap are set in the Mini App."""

from datetime import date, time

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.methods import SendMessage
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    User,
    WebAppInfo,
)

from tristhana.application.policies import Principal
from tristhana.application.ports.i18n import TimeArg, Translator
from tristhana.bots.telegram import data_callbacks as dcb
from tristhana.bots.telegram import moon_callbacks as mcb
from tristhana.bots.telegram import remind_callbacks as rcb
from tristhana.bots.telegram.day_off import day_off_line, day_off_picker
from tristhana.bots.telegram.moon import moon_status
from tristhana.bots.telegram.remind import practice_status
from tristhana.bots.telegram.runtime import SettingsUseCases
from tristhana.bots.telegram.screens import Reply, Screen, answered, button, show
from tristhana.bots.telegram.settings_callbacks import PREFIX, SettingsCallback, decode, encode
from tristhana.domain.accounts import (
    NOT_LISTED,
    NOT_NOW,
    Account,
    ExternalProfile,
    IdentityKey,
    IdentityProvider,
    InvalidTimezone,
    ProfilePatch,
    UnknownCity,
    home_city_of,
)
from tristhana.domain.locale import Locale
from tristhana.domain.moon import City
from tristhana.domain.rest_days import InvalidDayOff

CITY_PAGE = 12  # 2 columns x 6 rows
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
    router: Router,
    settings: SettingsUseCases,
    translator: Translator,
    miniapp_url: str = "",
    my_data: bool = False,
) -> None:
    screens = SettingsScreens(settings, translator, miniapp_url, my_data)

    @router.message(Command("settings"))
    async def on_settings(message: Message, account: Account) -> SendMessage:  # pyright: ignore[reportUnusedFunction]
        screen = await screens.view(Principal(account))
        return message.answer(screen.text, reply_markup=screen.markup)

    @router.callback_query(F.data.startswith(f"{PREFIX}:"))
    async def on_settings_tap(callback: CallbackQuery, account: Account) -> Reply | None:  # pyright: ignore[reportUnusedFunction]
        cb = decode(callback.data)
        if cb is not None and cb.action == "unlisted":  # a reply keyboard needs a new message
            text, markup = await answered(callback, screens.location_prompt(Principal(account)))
            return SendMessage(chat_id=callback.from_user.id, text=text, reply_markup=markup)
        work = screens.handle(Principal(account), cb, client_profile(callback.from_user))
        screen = await answered(callback, work)
        return show(callback, screen) if screen else None

    # A shared location: its zone only (MD-04); live locations, venues and forwards are not
    # answers.
    @router.message(F.location, ~F.venue, F.forward_origin.is_(None))
    async def on_location(message: Message, account: Account) -> SendMessage | None:  # pyright: ignore[reportUnusedFunction]
        location = message.location
        if location is None or location.live_period or message.from_user is None:
            return None
        text = await screens.zone_from_location(
            Principal(account), location.latitude, location.longitude, message.from_user
        )
        return None if text is None else message.answer(text, reply_markup=ReplyKeyboardRemove())


class SettingsScreens:
    def __init__(
        self, s: SettingsUseCases, translator: Translator, miniapp_url: str, my_data: bool = False
    ) -> None:
        self._s = s
        self._t = translator
        self._app = miniapp_url
        self._my_data = my_data  # ST-09: the "📦 My data" row

    async def handle(
        self, principal: Principal, cb: SettingsCallback | None, client: ExternalProfile
    ) -> Screen | None:
        if cb is None:
            return None
        match cb.action:
            case "view":
                return await self.view(principal)
            case "cities":
                return self.cities(principal, cb.page)
            case "language":
                account = await self._s.profile.execute(
                    principal, ProfilePatch(locale=cb.locale), client
                )
                return await self.view(Principal(account))  # in the new language at once
            case "city":
                return await self._profile(principal, ProfilePatch(home_city=cb.slug), client)
            case "utc":
                patch = ProfilePatch(timezone="UTC", home_city=None)
                return await self._profile(principal, patch, client)
            case "not_now":  # the nudge is answered (unless a city was chosen since)
                return await self._profile(principal, ProfilePatch(home_city=NOT_NOW), client)
            case "unlisted":  # sent as a new message by the handler
                return None
            case "day_off_pick":
                return self.day_off(principal)
            case "day_off":
                try:
                    saved = await self._s.day_off.execute(principal, cb.days_off)
                except InvalidDayOff:  # forged
                    return self.day_off(principal)
                return self.day_off(Principal(saved.account))  # pick a second one, or go back
            case "hide_ladies":  # WH-01: one account setting for the bot and the app
                account = await self._s.profile.execute(
                    principal, ProfilePatch(hide_ladies=cb.hide), client
                )
                return await self.view(Principal(account))
            case "offer_check_in":  # PR-06: one account setting for the bot and the app
                account = await self._s.profile.execute(
                    principal, ProfilePatch(offer_check_in=cb.offer), client
                )
                return await self.view(Principal(account))

    async def _profile(
        self, principal: Principal, patch: ProfilePatch, client: ExternalProfile
    ) -> Screen:
        try:
            account = await self._s.profile.execute(principal, patch, client)
        except (UnknownCity, InvalidTimezone):  # stale or forged
            return await self.view(principal)
        return await self.view(Principal(account))

    async def location_prompt(self, principal: Principal) -> tuple[str, ReplyKeyboardMarkup]:
        """ "My city isn't listed": ask for a location once (the zone comes from it)."""
        locale = principal.account.locale
        share = KeyboardButton(
            text=self._t.t(locale, "settings-share-location-button"), request_location=True
        )
        markup = ReplyKeyboardMarkup(
            keyboard=[[share]], resize_keyboard=True, one_time_keyboard=True
        )
        return self._t.t(locale, "settings-share-location"), markup

    async def zone_from_location(
        self, principal: Principal, lat: float, lon: float, user: User
    ) -> str | None:
        """The reply to a shared location; None when this bot doesn't take locations."""
        if self._s.zone_from_location is None:
            return None
        locale = principal.account.locale
        saved = await self._s.zone_from_location.execute(principal, lat, lon, client_profile(user))
        if saved is None or saved.timezone is None:
            return self._t.t(locale, "settings-location-unknown")
        today, _ = self._s.today(Principal(saved))
        zone = self._zone_label(saved.locale, saved.timezone, today, None)
        return self._t.t(saved.locale, "settings-location-zone", zone=zone)

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
        home = home_city_of(account, self._s.cities)
        city = self._s.cities.get(account.moon_location) or self._s.cities.default
        language = self._t.t(
            locale, "language-auto" if not account.locale_custom else f"language-{locale}"
        )
        lines = [
            self._t.t(locale, "settings-title"),
            self._t.t(locale, "settings-language-line", language=language),
            self._city_line(account, home, today),
            self._t.t(locale, "settings-moon-line", city=city.name(locale)),
            day_off_line(self._t, locale, account.day_off.days),
            self._t.t(locale, "settings-ladies-line", shown="no" if account.hide_ladies else "yes"),
            self._t.t(
                locale, "settings-checkin-line", offered="yes" if account.offer_check_in else "no"
            ),
            moon_status(self._t, locale, settings, zone, today, home),
            practice_status(self._t, locale, settings, zone, today, home),
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
                button(self._t, locale, "settings-city-button", _data(action="cities", page=0)),
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
            [
                button(
                    self._t,
                    locale,
                    "settings-ladies-show" if account.hide_ladies else "settings-ladies-hide",
                    _data(action="hide_ladies", hide=not account.hide_ladies),
                )
            ],
            [
                button(
                    self._t,
                    locale,
                    "settings-checkin-off" if account.offer_check_in else "settings-checkin-on",
                    _data(action="offer_check_in", offer=not account.offer_check_in),
                )
            ],
        ]
        if not account.home_city_chosen:  # the one-time nudge: any answer ends it
            lines.insert(3, self._t.t(locale, "settings-city-nudge"))
            rows.insert(
                2, [button(self._t, locale, "settings-city-not-now", _data(action="not_now"))]
            )
        if self._my_data:
            rows.append(
                [
                    button(
                        self._t,
                        locale,
                        "settings-data-button",
                        dcb.encode(dcb.DataCallback("open")),
                    )
                ]
            )
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

    def _city_line(self, account: Account, home: City | None, today: date) -> str:
        locale, zone = account.locale, account.timezone
        if zone is None:
            return self._t.t(locale, "settings-city-no-zone-line")
        label = self._zone_label(locale, zone, today, home)
        if home is not None:
            return self._t.t(locale, "settings-city-line", zone=label)
        key = (
            "settings-city-unlisted-line"
            if account.home_city_chosen
            else "settings-city-unset-line"
        )
        return self._t.t(locale, key, zone=label)

    def _zone_label(self, locale: Locale, zone: str, today: date, home: City | None) -> str:
        """The zone with its offset today: "Astana (UTC+5)" (the time label minus the time)."""
        label = self._t.t(locale, "time-label", time=TimeArg(today, time(12), zone, home))
        return label.split(" ", 1)[1] if " " in label else label

    def cities(self, principal: Principal, page: int) -> Screen:
        account = principal.account
        locale = account.locale
        # Every listed city: Moscow, Kazan and Sochi share a zone, but each one is its own.
        cities = sorted(self._s.cities.all, key=lambda c: c.name(locale))
        pages = max(1, -(-len(cities) // CITY_PAGE))
        page = min(page, pages - 1)
        shown = cities[page * CITY_PAGE : (page + 1) * CITY_PAGE]
        home = home_city_of(account, self._s.cities)
        buttons = [
            InlineKeyboardButton(
                text=("✓ " if home is not None and c.slug == home.slug else "") + c.name(locale),
                callback_data=_data(action="city", slug=c.slug),
            )
            for c in shown
        ]
        rows = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
        paging: list[InlineKeyboardButton] = []
        if page > 0:
            paging.append(
                button(self._t, locale, "page-prev", _data(action="cities", page=page - 1))
            )
        if page < pages - 1:
            paging.append(
                button(self._t, locale, "page-next", _data(action="cities", page=page + 1))
            )
        if paging:
            rows.append(paging)
        utc = account.timezone == "UTC"
        rows.append(
            [
                button(
                    self._t,
                    locale,
                    "settings-city-unlisted",
                    _data(action="unlisted"),
                    mark=account.home_city == NOT_LISTED and not utc,
                ),
                button(self._t, locale, "settings-city-utc", _data(action="utc"), mark=utc),
            ]
        )
        rows.append([button(self._t, locale, "log-back", _data(action="view"))])
        return Screen(
            self._t.t(locale, "settings-pick-city"), InlineKeyboardMarkup(inline_keyboard=rows)
        )
