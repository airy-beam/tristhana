"""Draw the moon day card examples for the public guides (ST-10), with the real card renderer.

    cd backend && uv run python ../tools/cards/render_guide_examples.py

Writes `site/src/assets/cards/<en|ru>/moon-day.webp`: the square card of Mysuru's full moon
on 24 Nov 2026, from the stored-calendar dates and the sunrise the app computes. These are
examples, not screenshots, so `npm run shots` doesn't touch them; re-run this after the card's
look changes.
"""

import asyncio
import io
from datetime import date, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from PIL import Image

from tristhana.domain.moon import MoonDay, MoonDayKind, MoonPhase
from tristhana.domain.share_cards import CardFormat, MoonCard
from tristhana.infrastructure.cards.pillow_renderer import PillowCardRenderer
from tristhana.infrastructure.i18n.fluent import FluentTranslator
from tristhana.infrastructure.seed.cities_yaml import load_cities
from tristhana.infrastructure.seed.practice_catalog import load_practice_catalog
from tristhana.moon import sunrise_at

ROOT = Path(__file__).resolve().parents[2]
SEED = ROOT / "data" / "seed"
OUT = ROOT / "site" / "src" / "assets" / "cards"
WIDTH = 720  # the guide shows it at phone width; keeps each file well under 120 KB


async def main() -> None:
    cities = load_cities(SEED / "cities.yaml")
    mysuru = cities.find("mysuru")
    if mysuru is None:
        raise SystemExit("mysuru is not in data/seed/cities.yaml")
    day = date(2026, 11, 24)
    # To the nearest minute, as the app shows it (application/share_cards.py).
    rise = (sunrise_at(mysuru.location, day) + timedelta(seconds=30)).astimezone(
        ZoneInfo(mysuru.location.tz)
    )
    card = MoonCard(
        day,
        MoonPhase.PURNIMA,
        False,
        mysuru,
        rise.time().replace(second=0, microsecond=0),
        MoonDay(date(2026, 12, 8), MoonDayKind.AMAVASYA),
    )
    renderer = PillowCardRenderer(FluentTranslator(), load_practice_catalog(SEED).catalog)
    for locale in ("en", "ru"):
        png = await renderer.render(card, CardFormat.SQUARE, locale)
        image = Image.open(io.BytesIO(png)).resize((WIDTH, WIDTH), Image.Resampling.LANCZOS)
        target = OUT / locale / "moon-day.webp"
        target.parent.mkdir(parents=True, exist_ok=True)
        image.save(target, "WEBP", quality=82, method=6)
        print(target.relative_to(ROOT), f"{target.stat().st_size // 1024} KB")


if __name__ == "__main__":
    asyncio.run(main())
