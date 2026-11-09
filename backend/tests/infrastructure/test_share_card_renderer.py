"""The Pillow card renderer (ST-07, ADR-0040): exact sizes, real PNGs under 400 KB,
deterministic bytes, glyph coverage for every catalog name and card string, and card copy
that never addresses the reader (strangers see it) or uses competitive words."""

import asyncio
import re
from datetime import date
from functools import cache
from importlib.resources import files
from pathlib import Path

import pytest

from tristhana.domain.practice import PracticeCatalog
from tristhana.domain.share_cards import (
    AsanaCard,
    AsanaVariant,
    Card,
    CardFormat,
    CardTone,
    CountCard,
    MonthCard,
    YearCard,
)
from tristhana.infrastructure.cards.pillow_renderer import PillowCardRenderer
from tristhana.infrastructure.i18n.fluent import FluentTranslator
from tristhana.infrastructure.seed.practice_catalog import load_practice_catalog

SEED = Path(__file__).resolve().parents[3] / "data" / "seed"
P, N = CardTone.PRACTICE, CardTone.NO_PRACTICE
PNG = b"\x89PNG\r\n\x1a\n"


@cache
def catalog() -> PracticeCatalog:
    return load_practice_catalog(SEED).catalog


def renderer() -> PillowCardRenderer:
    return PillowCardRenderer(FluentTranslator(), catalog())


CARDS: dict[str, Card] = {
    "month": MonthCard(2026, 10, (P, N) * 15 + (P,), frozenset({6, 21}), 16, (1, 2), 1120, False),
    "month-current": MonthCard(2026, 11, (P,) * 9, frozenset({5, 20}), 9, (), None, True),
    "year": YearCard(2026, (P, P, N) * 104 + (P,), frozenset({date(2026, 3, 3)}), 209, False),
    "year-done": YearCard(2024, (P, N) * 183, frozenset(), 183, True),
    "asana": AsanaCard(AsanaVariant.NEW_ASANA, "primary", "supta-kurmasana", 2026, 10),
    "begins": AsanaCard(AsanaVariant.SERIES_BEGINS, "intermediate", None, 2026, 10),
    "full": AsanaCard(AsanaVariant.SERIES_COMPLETE, "primary", None, 2026, 10),
    "advanced-a": AsanaCard(AsanaVariant.NEW_ASANA, "advanced-a", "raja-kapotasana", 2026, 10),
    "advanced-a-full": AsanaCard(AsanaVariant.SERIES_COMPLETE, "advanced-a", None, 2026, 10),
    "count": CountCard(1000),
    # RU groups 1 214 with a no-break space: never split inside the number.
    "year-1214": YearCard(2026, (P,) * 313, frozenset(), 1214, False),
}


@pytest.mark.parametrize("fmt", list(CardFormat))
@pytest.mark.parametrize("locale", ["en", "ru"])
@pytest.mark.parametrize("name", list(CARDS))
def test_renders_a_png_of_the_exact_size(name: str, locale: str, fmt: CardFormat) -> None:
    from PIL import Image

    png = asyncio.run(renderer().render(CARDS[name], fmt, locale))  # type: ignore[arg-type]
    assert png.startswith(PNG)
    assert len(png) < 400_000
    import io

    with Image.open(io.BytesIO(png)) as image:
        assert image.size == fmt.size
        assert image.mode == "RGB"


def test_same_card_same_bytes() -> None:
    r = renderer()
    a = asyncio.run(r.render(CARDS["month"], CardFormat.STORY, "ru"))
    b = asyncio.run(r.render(CARDS["month"], CardFormat.STORY, "ru"))
    assert a == b


def test_advanced_series_have_no_traditional_name() -> None:
    text = renderer().text(CARDS["advanced-a-full"], "en")
    assert (text.headline, text.subline) == ("Full Advanced A", "Third series")
    assert "Sthira" not in " ".join((text.subline, *text.lines))
    ru = renderer().text(CARDS["advanced-a-full"], "ru")
    assert (ru.headline, ru.subline) == ("Третья серия целиком", "Advanced A")
    full = renderer().text(CARDS["full"], "ru")
    assert (full.headline, full.subline) == ("Первая серия целиком", "Йога Чикитса")
    assert full.lines[0] == "Yoga Cikitsā"


def test_card_text() -> None:
    r = renderer()
    month = r.text(CARDS["month"], "ru")
    assert month.title == "Октябрь 2026"
    assert month.headline.replace("\xa0", " ") == "16 дней практики в октябре"
    assert "\xa0" in month.headline  # "в" never ends a line
    assert month.lines == ("Первая серия · Вторая серия", "18 ч 40 мин на коврике")
    assert len(month.weekdays) == 7
    assert r.text(CARDS["year"], "en").headline == "2026 so far: 209 practices"
    assert r.text(CARDS["year-done"], "ru").headline == "183 практики за 2024 год"
    asana = r.text(CARDS["asana"], "ru")
    assert asana.title == "Новая асана"
    assert asana.lines == ("Supta Kūrmāsana", "Первая серия", "Октябрь 2026")
    count = r.text(CARDS["count"], "ru")
    assert count.number == "1\xa0000"
    assert count.headline == "практик на коврике"
    assert r.text(CARDS["count"], "en").number == "1,000"


def _catalog_names() -> set[str]:
    names: set[str] = set()
    for series in catalog().series:
        for stop in series.stops:
            names |= {stop.label("en"), stop.label("ru"), stop.names.iast or ""}
        if series.traditional is not None:
            t = series.traditional
            names |= {t.latin, t.ru, t.iast or ""}
    return names - {""}


def _card_strings() -> set[str]:
    out: set[str] = set()
    t = FluentTranslator()
    r = renderer()
    for locale in ("en", "ru"):
        for card in CARDS.values():
            text = r.text(card, locale)  # type: ignore[arg-type]
            out |= {text.title, text.headline, text.subline, text.number, text.footer}
            out |= {*text.lines, *text.weekdays, *text.months}
            out |= {text.legend_practice, text.legend_moon, text.title.upper()}
        for n in range(1, 7):
            for key in ("card-series-name", "card-series-begins", "card-series-complete"):
                out.add(t.t(locale, key, n=n))  # type: ignore[arg-type]
    return out - {""}


@pytest.mark.parametrize("font", ["serif", "sans"])
def test_fonts_cover_every_catalog_name(font: str) -> None:
    from tristhana.infrastructure.cards.draw import has_glyphs

    missing = [n for n in sorted(_catalog_names()) if not has_glyphs(font, n)]  # type: ignore[arg-type]
    assert missing == []


@pytest.mark.parametrize("font", ["serif", "sans", "sans-bold"])
def test_fonts_cover_every_card_string(font: str) -> None:
    from tristhana.infrastructure.cards.draw import has_glyphs

    missing = [s for s in sorted(_card_strings()) if not has_glyphs(font, s)]  # type: ignore[arg-type]
    assert missing == []


def test_glyph_check_notices_a_missing_glyph() -> None:
    from tristhana.infrastructure.cards.draw import has_glyphs

    assert not has_glyphs("serif", "\U0001f319")  # 🌙: cards draw no emoji


# Public text (ashtanga-expert, ST-07 review): it never speaks to the reader, and it keeps
# the PR-08 / GM-01 rule against competitive or guilty words.
_NOT_ON_CARDS = re.compile(
    r"\byou\b|\byour|\bты\b|\bтво|\bпока\b|given|unlock|разблок|streak|level|уровень|"  # noqa: RUF001
    r"achieve|достижен|goal|цель|rank|finally|наконец|only|только|daily|ежедневн|"
    r"complete|заверш|record|рекорд",
    re.IGNORECASE,
)


@pytest.mark.parametrize("locale", ["en", "ru"])
def test_card_copy_never_addresses_the_reader(locale: str) -> None:
    source = (files("tristhana.infrastructure.i18n") / "locales" / locale / "card.ftl").read_text(
        encoding="utf-8"
    )
    lines = [line for line in source.splitlines() if line.strip() and not line.startswith("#")]
    values = [line.split("=", 1)[1] if re.match(r"^[a-z-]+ =", line) else line for line in lines]
    assert not [v for v in values if _NOT_ON_CARDS.search(v)]


def test_renderer_module_does_not_import_pillow_at_import_time() -> None:
    import subprocess
    import sys

    code = "import sys, tristhana.infrastructure.cards.pillow_renderer; print('PIL' in sys.modules)"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)  # noqa: S603
    assert out.stdout.strip() == "False"


# The expert's review found the year grid running into the footer when the headline wrapped:
# the grids now shrink to fit. No saffron (a practice cell or the legend) may reach the footer.
_WORST: dict[str, Card] = {
    # August 2026 starts on a Saturday: six weeks. Every day practised, series and time lines.
    "month-six-weeks": MonthCard(
        2026, 8, (P,) * 31, frozenset({9, 23}), 31, (1, 2, 3), 6000, False
    ),
    "year-full": YearCard(2026, (P,) * 365, frozenset({date(2026, 12, 31)}), 365, True),
}


@pytest.mark.parametrize("fmt", list(CardFormat))
@pytest.mark.parametrize("locale", ["en", "ru"])
@pytest.mark.parametrize("name", list(_WORST))
def test_grids_stay_clear_of_the_footer(name: str, locale: str, fmt: CardFormat) -> None:
    import io

    from PIL import Image

    png = asyncio.run(renderer().render(_WORST[name], fmt, locale))  # type: ignore[arg-type]
    footer_top = fmt.size[1] - (250 if fmt is CardFormat.STORY else 56) - 40
    with Image.open(io.BytesIO(png)) as image:
        rgb = image.convert("RGB")
        width = fmt.size[0]
        assert not _has_saffron(rgb.crop((0, footer_top, width, fmt.size[1])).tobytes())
        # …and the grid did draw its last week, above the footer.
        assert _has_saffron(rgb.crop((0, 0, width, footer_top)).tobytes())


def _has_saffron(rgb: bytes) -> bool:
    """Any pixel of the practice tone (#E8A33D, anti-aliasing aside) in raw RGB bytes."""
    return any(
        rgb[i] > 200 and 130 < rgb[i + 1] < 190 and rgb[i + 2] < 100 for i in range(0, len(rgb), 3)
    )


def test_a_grouped_number_is_never_split() -> None:
    from tristhana.infrastructure.cards.draw import (
        _Canvas,  # pyright: ignore[reportPrivateUsage]
        font,
    )

    headline = renderer().text(CARDS["year-1214"], "ru").headline
    lines = _Canvas(CardFormat.STORY).wrap(headline, font("serif", 80), 904)
    assert any("1\xa0214" in line for line in lines), lines
