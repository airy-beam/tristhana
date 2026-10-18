"""`Translator` backed by Project Fluent. `fluent.runtime` is imported lazily (cold start)."""

from __future__ import annotations

from functools import cache
from importlib.resources import files
from typing import TYPE_CHECKING

from tristhana.application.ports.i18n import DateArg
from tristhana.domain.locale import Locale

if TYPE_CHECKING:
    from fluent.runtime import FluentBundle

_LOCALES_DIR = files("tristhana.infrastructure.i18n") / "locales"


class FluentTranslator:
    def t(self, locale: Locale, key: str, **args: str | int | DateArg) -> str:
        bundle = _bundle(locale)
        if not bundle.has_message(key):
            raise KeyError(f"no message {key!r} in locale {locale!r}")
        pattern = bundle.get_message(key).value
        if pattern is None:
            raise KeyError(f"message {key!r} in locale {locale!r} has no value")
        values = {
            k: _format_date(v, locale) if isinstance(v, DateArg) else v for k, v in args.items()
        }
        text, errors = bundle.format_pattern(pattern, values)
        if errors:
            raise ValueError(f"{locale}/{key}: {errors}")
        return str(text)


def _format_date(arg: DateArg, locale: Locale) -> str:
    # fluent.runtime's DATETIME ignores weekday/day/month options, so format with Babel.
    from babel.dates import format_skeleton

    return str(format_skeleton("yMMMEd" if arg.with_year else "MMMEd", arg.day, locale=locale))


def message_ids(locale: Locale) -> set[str]:
    """All message ids defined for `locale` (used by the key-parity test)."""
    from fluent.syntax import FluentParser, ast

    ids: set[str] = set()
    for resource in _resources(locale):
        parsed = FluentParser().parse(resource)
        junk = [e for e in parsed.body if isinstance(e, ast.Junk)]
        if junk:
            raise ValueError(f"{locale}: unparsable Fluent entries: {junk}")
        ids.update(e.id.name for e in parsed.body if isinstance(e, ast.Message))
    return ids


def _resources(locale: Locale) -> list[str]:
    folder = _LOCALES_DIR / locale
    return [
        f.read_text(encoding="utf-8")
        for f in sorted(folder.iterdir(), key=lambda p: p.name)
        if f.name.endswith(".ftl")
    ]


@cache
def _bundle(locale: Locale) -> FluentBundle:
    from fluent.runtime import FluentBundle, FluentResource

    # use_isolating=False: Telegram renders the bidi isolation marks as visible boxes.
    bundle = FluentBundle([locale], use_isolating=False)
    for text in _resources(locale):
        bundle.add_resource(FluentResource(text))
    return bundle
