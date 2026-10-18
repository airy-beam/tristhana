"""UI locale negotiation from a client language code (Telegram `language_code`, later browsers)."""

from typing import Literal, get_args

type Locale = Literal["en", "ru"]
LOCALES: tuple[Locale, ...] = get_args(Locale.__value__)
DEFAULT_LOCALE: Locale = "en"

# Russian is widely used in these countries; everything else gets English (decision 2026-10-18).
_RUSSIAN_SPEAKING = frozenset({"ru", "be", "kk", "ky"})


def negotiate_locale(language_code: str | None) -> Locale:
    """`ru-RU` → `ru`; unknown or missing codes fall back to English."""
    if not language_code:
        return DEFAULT_LOCALE
    primary = language_code.strip().lower().replace("_", "-").split("-", 1)[0]
    return "ru" if primary in _RUSSIAN_SPEAKING else DEFAULT_LOCALE
