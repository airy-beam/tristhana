"""`CardRenderer` with Pillow (ST-07, ADR-0040). Resolves every string here (Fluent
`card.ftl`, Babel month and weekday names, catalog names), then draws in a worker thread.
Pillow itself is imported on the first card only (`draw`), never at startup."""

import asyncio

from tristhana.application.ports.i18n import Translator
from tristhana.domain.locale import Locale
from tristhana.domain.practice import PracticeCatalog
from tristhana.domain.share_cards import (
    AsanaCard,
    Card,
    CardFormat,
    CountCard,
    MonthCard,
    YearCard,
)
from tristhana.infrastructure.cards.text import CardText, resolve


class PillowCardRenderer:
    def __init__(self, translator: Translator, catalog: PracticeCatalog) -> None:
        self._t, self._catalog = translator, catalog

    async def render(self, card: Card, format: CardFormat, locale: Locale) -> bytes:
        text = self.text(card, locale)
        return await asyncio.to_thread(draw_card, card, format, text)

    def text(self, card: Card, locale: Locale) -> CardText:
        return resolve(self._t, self._catalog, card, locale)


def draw_card(card: Card, format: CardFormat, text: CardText) -> bytes:
    from tristhana.infrastructure.cards import draw

    match card:
        case MonthCard():
            return draw.draw_month(card, format, text)
        case YearCard():
            return draw.draw_year(card, format, text)
        case AsanaCard():
            return draw.draw_asana(card, format, text)
        case CountCard():
            return draw.draw_count(card, format, text)
