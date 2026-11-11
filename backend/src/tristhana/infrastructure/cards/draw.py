"""Draws share cards with Pillow (ST-07, ADR-0040). The only module that imports PIL; it is
loaded on the first card, never at startup, and runs in a worker thread.

It draws only what a card holds, with resolved text (`CardText`): no data access, no moon
computation, no emoji (moon days are drawn rings, the mark is drawn shapes), one brand
palette whatever the Telegram theme (`docs/brand/`). Output is deterministic for a card.
"""

import io
from calendar import monthrange
from collections.abc import Generator
from contextlib import contextmanager
from datetime import date, timedelta
from functools import cache
from importlib.resources import files
from typing import Literal

from PIL import Image, ImageDraw, ImageFont, ImageOps

from tristhana.domain.share_cards import (
    AsanaCard,
    CardFormat,
    CardTone,
    CountCard,
    MonthCard,
    YearCard,
)
from tristhana.infrastructure.cards.text import CardText

type RGB = tuple[int, int, int]
type RGBA = tuple[int, int, int, int]
type FontName = Literal["serif", "sans", "sans-bold"]

INDIGO_TOP: RGB = (45, 49, 112)  # --indigo2
INDIGO: RGB = (28, 31, 77)  # --indigo
INDIGO_DEEP: RGB = (18, 20, 51)
SAFFRON: RGB = (232, 163, 61)
OCHRE: RGB = (200, 115, 42)
PAPER: RGB = (243, 233, 214)
SOFT: RGB = (233, 227, 242)  # body text on indigo

_FONT_FILES: dict[FontName, str] = {
    "serif": "NotoSerifDisplay-Regular.ttf",
    "sans": "NotoSans-Regular.ttf",
    "sans-bold": "NotoSans-Bold.ttf",
}

WIDTH = 1080
STORY_SAFE = 250  # Telegram draws its own controls over the top and bottom of a story


def font_path(name: FontName) -> str:
    return str(files("tristhana.infrastructure.cards") / "fonts" / _FONT_FILES[name])


@cache
def font(name: FontName, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(font_path(name), size)


def _alpha(color: RGB, a: float) -> RGBA:
    return (*color, round(255 * a))


class _Canvas:
    def __init__(self, fmt: CardFormat) -> None:
        self.w, self.h = fmt.size
        self.story = fmt is CardFormat.STORY
        self.pad = 88 if self.story else 64
        self.top = STORY_SAFE if self.story else 64
        self.bottom = self.h - (STORY_SAFE if self.story else 56)
        self.base = _background(self.w, self.h).copy()
        self.layer = Image.new("RGBA", (self.w, self.h), (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.layer)

    @property
    def limit(self) -> int:
        """The lowest y the body may reach: above the footer line."""
        return self.bottom - (64 if self.story else 48)

    @property
    def inner(self) -> int:
        return self.w - 2 * self.pad

    def png(self) -> bytes:
        out = Image.alpha_composite(self.base, self.layer).convert("RGB")
        buf = io.BytesIO()
        out.save(buf, "PNG", compress_level=3)
        return buf.getvalue()

    def fit(self, text: str, name: FontName, size: int, width: int) -> ImageFont.FreeTypeFont:
        """The largest size ≤ `size` at which `text` fits on one line."""
        while size > 18 and self.d.textlength(text, font=font(name, size)) > width:
            size -= 2
        return font(name, size)

    def wrap(self, text: str, f: ImageFont.FreeTypeFont, width: int) -> list[str]:
        lines: list[str] = []
        for word in text.split(" "):  # never at a no-break space (RU "в" + month)
            if lines and self.d.textlength(f"{lines[-1]} {word}", font=f) <= width:
                lines[-1] = f"{lines[-1]} {word}"
            else:
                lines.append(word)
        return lines or [""]

    def text(
        self,
        y: int,
        text: str,
        f: ImageFont.FreeTypeFont,
        fill: RGB | RGBA,
        *,
        width: int | None = None,
        center: bool = False,
        spacing: float = 1.12,
        max_lines: int = 3,
    ) -> int:
        """Draws wrapped text from `y`; returns the y below it."""
        width = width or self.inner
        size = int(f.size)
        lines = self.wrap(text, f, width)
        while len(lines) > max_lines and size > 24:
            size -= 4
            f = font(_name_of(f), size)
            lines = self.wrap(text, f, width)
        step = round(size * spacing)
        for line in lines:
            x = (self.w - self.d.textlength(line, font=f)) / 2 if center else self.pad
            self.d.text((x, y), line, font=f, fill=fill)
            y += step
        return y

    def mark(self, x: int, y: int, size: int) -> None:
        """The brand mark: a crescent over three points (asana, breath, drishti)."""
        s = size / 640
        ring = Image.new("L", (size, size), 0)
        md = ImageDraw.Draw(ring)
        md.ellipse(_box(320 * s, 176 * s, 54 * s), fill=255)
        md.ellipse(_box(342 * s, 162 * s, 48 * s), fill=0)
        self.layer.paste(Image.new("RGBA", (size, size), (*PAPER, 255)), (x, y), ring)
        line = _alpha(PAPER, 0.22)
        width = max(2, round(5 * s * 1.6))
        pts = [(320 * s, 318 * s), (226 * s, 480 * s), (414 * s, 480 * s)]
        pts = [(x + px, y + py) for px, py in pts]
        self.d.line([pts[0], pts[1], pts[2], pts[0]], fill=line, width=width)
        for (px, py), color in zip(pts, (PAPER, SAFFRON, OCHRE), strict=True):
            self.d.ellipse(_box(px, py, 40 * s * 1.3), fill=color)

    def header(self) -> int:
        size = 76 if self.story else 64
        self.mark(self.pad - 10, self.top - 10, size)
        f = font("serif", 44 if self.story else 38)
        self.d.text(
            (self.pad + size + 10, self.top + size / 2 - 6),
            "Tristhana",
            font=f,
            fill=PAPER,
            anchor="lm",
        )
        return self.top + size + (40 if self.story else 24)

    @contextmanager
    def centered(self, top: int) -> Generator[None]:
        """Draws the block in the body into its own layer, then centres it vertically
        between `top` and the footer."""
        layer, d = self.layer, self.d
        self.layer = Image.new("RGBA", (self.w, self.h), (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.layer)
        try:
            yield
        finally:
            block, self.layer, self.d = self.layer, layer, d
            box = block.getbbox()
            if box is not None:
                room = self.bottom - 60 - top
                offset = top + (room - (box[3] - box[1])) // 2 - box[1]
                self.layer.alpha_composite(
                    block.crop((0, box[1], self.w, box[3])), (0, offset + box[1])
                )

    def footer(self, text: str) -> None:
        f = font("sans", 30 if self.story else 26)
        self.d.text((self.w / 2, self.bottom), text, font=f, fill=_alpha(SOFT, 0.8), anchor="ms")


def _name_of(f: ImageFont.FreeTypeFont) -> FontName:
    path = str(f.path)
    for name, file in _FONT_FILES.items():
        if path.endswith(file):
            return name
    return "sans"


def _box(cx: float, cy: float, r: float) -> tuple[float, float, float, float]:
    return (cx - r, cy - r, cx + r, cy + r)


@cache
def _background(w: int, h: int) -> Image.Image:
    ramp = Image.linear_gradient("L").resize((w, h))  # pyright: ignore[reportUnknownMemberType]
    return ImageOps.colorize(ramp, INDIGO_TOP, INDIGO_DEEP, INDIGO, midpoint=140).convert("RGBA")


def _cell(
    c: _Canvas,
    x: float,
    y: float,
    size: float,
    tone: CardTone | None,
    moon: bool,
    label: str | None = None,
) -> None:
    """One day: saffron = practice, faint = no practice, outline = not yet; a ring = moon."""
    box = (x, y, x + size, y + size)
    radius = max(3, round(size * 0.18))
    if tone is CardTone.PRACTICE:
        c.d.rounded_rectangle(box, radius, fill=SAFFRON)
    elif tone is CardTone.NO_PRACTICE:
        c.d.rounded_rectangle(box, radius, fill=_alpha(PAPER, 0.10))
    else:
        c.d.rounded_rectangle(
            box, radius, outline=_alpha(PAPER, 0.16), width=max(1, round(size / 40))
        )
    if label is not None:
        ink = INDIGO if tone is CardTone.PRACTICE else _alpha(SOFT, 0.55)
        f = font("sans", max(14, round(size * 0.3)))
        c.d.text((x + size / 2, y + size / 2), label, font=f, fill=ink, anchor="mm")
    if moon:
        inset = size * 0.12
        ring = INDIGO if tone is CardTone.PRACTICE else PAPER
        c.d.ellipse(
            (x + inset, y + inset, x + size - inset, y + size - inset),
            outline=ring,
            width=max(2, round(size / 22)),
        )


def _legend(c: _Canvas, y: int, text: CardText, size: int) -> int:
    f = font("sans", size)
    sw = round(size * 0.9)
    parts = ((CardTone.PRACTICE, False, text.legend_practice), (None, True, text.legend_moon))
    widths = [sw + 14 + c.d.textlength(t, font=f) for _, _, t in parts]
    gap = 48
    x = (c.w - sum(widths) - gap) / 2
    for (tone, moon, label), width in zip(parts, widths, strict=True):
        _cell(c, x, y, sw, tone if tone else CardTone.NO_PRACTICE, moon)
        c.d.text((x + sw + 14, y + sw / 2), label, font=f, fill=SOFT, anchor="lm")
        x += width + gap
    return y + sw


def draw_month(card: MonthCard, fmt: CardFormat, text: CardText) -> bytes:
    c = _Canvas(fmt)
    y = c.header()
    title = font("sans-bold", 36 if c.story else 30)
    c.d.text((c.pad, y), text.title.upper(), font=title, fill=SAFFRON)
    y += 60 if c.story else 46
    y = c.text(y, text.headline, font("serif", 84 if c.story else 56), PAPER, max_lines=2)
    y += 36 if c.story else 16

    body = 36 if c.story else 26
    lines = text.lines if c.story else (" · ".join(text.lines),) if text.lines else ()
    legend = 30 if c.story else 24
    after_grid = 24 if c.story else 10
    after_legend = 44 if c.story else 18
    below = after_grid + round(legend * 0.9) + after_legend + len(lines) * round(body * 1.45)
    weekday_row = 46 if c.story else 34
    first, days = date(card.year, card.month, 1), monthrange(card.year, card.month)[1]
    lead = first.weekday()
    rows = (lead + days + 6) // 7
    gap = 16 if c.story else 10
    room = c.limit - below - y - weekday_row  # the grid fits between headline and legend
    cell = min((c.inner - 6 * gap) // 7, room // rows - gap)
    grid_w = 7 * cell + 6 * gap
    x0 = (c.w - grid_w) / 2
    wf = font("sans-bold", 26 if c.story else 22)
    for i, wd in enumerate(text.weekdays):
        at = (x0 + i * (cell + gap) + cell / 2, y)
        c.d.text(at, wd, font=wf, fill=_alpha(SOFT, 0.6), anchor="mt")
    y += weekday_row
    for day in range(1, days + 1):
        row, col = divmod(lead + day - 1, 7)
        tone = card.tones[day - 1] if day <= len(card.tones) else None
        x, top = x0 + col * (cell + gap), y + row * (cell + gap)
        _cell(c, x, top, cell, tone, day in card.moon_days, str(day))
    y += rows * (cell + gap) + after_grid
    y = _legend(c, y, text, legend) + after_legend
    for line in lines:
        f = c.fit(line, "sans", body, c.inner)
        c.d.text((c.w / 2, y), line, font=f, fill=SOFT, anchor="mt")
        y += round(body * 1.45)
    c.footer(text.footer)
    return c.png()


def draw_year(card: YearCard, fmt: CardFormat, text: CardText) -> bytes:
    c = _Canvas(fmt)
    y = c.header()
    y = c.text(y, text.headline, font("serif", 80 if c.story else 54), PAPER, max_lines=2)
    y += 30 if c.story else 14
    cols = 3 if c.story else 4
    grid_rows = 12 // cols
    gap = 5 if c.story else 4
    label_h = 44 if c.story else 32
    row_gap = 18 if c.story else 10
    legend = 30 if c.story else 22
    below = (10 if c.story else 0) + round(legend * 0.9)
    room = c.limit - below - y  # the twelve months fit between headline and legend
    by_height = ((room - (grid_rows - 1) * row_gap) // grid_rows - label_h) // 6 - gap
    by_width = ((c.inner - (cols - 1) * 28) // cols - 6 * gap) // 7
    cell = min(34 if c.story else 26, by_height, by_width)
    month_w = 7 * cell + 6 * gap
    col_gap = (c.inner - cols * month_w) // (cols - 1)
    month_h = label_h + 6 * (cell + gap)
    lf = font("sans-bold", 26 if c.story else 20)
    start = date(card.year, 1, 1)
    for m in range(12):
        row, col = divmod(m, cols)
        mx = c.pad + col * (month_w + col_gap)
        my = y + row * (month_h + row_gap)
        c.d.text((mx, my), text.months[m], font=lf, fill=_alpha(SOFT, 0.75))
        first = date(card.year, m + 1, 1)
        lead = first.weekday()
        for day in range(monthrange(card.year, m + 1)[1]):
            when = first + timedelta(days=day)
            index = (when - start).days
            tone = card.tones[index] if index < len(card.tones) else None
            r, k = divmod(lead + day, 7)
            x, top = mx + k * (cell + gap), my + label_h + r * (cell + gap)
            _cell(c, x, top, cell, tone, when in card.moon_days)
    y += grid_rows * (month_h + row_gap) - row_gap
    _legend(c, y + (10 if c.story else 0), text, legend)
    c.footer(text.footer)
    return c.png()


def draw_asana(card: AsanaCard, fmt: CardFormat, text: CardText) -> bytes:
    c = _Canvas(fmt)
    _moon_glow(c)
    top = c.header()
    with c.centered(top):
        y = 0
        if text.title:
            kf = font("sans-bold", 34 if c.story else 28)
            tw = c.d.textlength(text.title.upper(), font=kf)
            ph = 64 if c.story else 54
            c.d.rounded_rectangle((c.pad, y, c.pad + tw + 56, y + ph), ph // 2, fill=SAFFRON)
            at = (c.pad + 28, y + ph / 2)
            c.d.text(at, text.title.upper(), font=kf, fill=INDIGO, anchor="lm")
            y += ph + (44 if c.story else 28)
        y = c.text(y, text.headline, font("serif", 104 if c.story else 76), PAPER, max_lines=3)
        y += 28 if c.story else 14
        if text.subline:
            y = c.text(y, text.subline, font("serif", 60 if c.story else 44), SAFFRON)
            y += 16
        size = 38 if c.story else 30
        for i, line in enumerate(text.lines):
            f = c.fit(line, "sans", size, c.inner)
            c.d.text((c.pad, y), line, font=f, fill=_alpha(SOFT, 0.7) if i == 0 else SOFT)
            y += round(int(f.size) * 1.55)
    c.footer(text.footer)
    return c.png()


def draw_count(card: CountCard, fmt: CardFormat, text: CardText) -> bytes:
    c = _Canvas(fmt)
    _moon_glow(c)
    top = c.header()
    with c.centered(top):
        nf = c.fit(text.number, "serif", 380 if c.story else 300, c.inner)
        c.d.text((c.w / 2, 0), text.number, font=nf, fill=SAFFRON, anchor="mt")
        y = round(int(nf.size) * 1.05)
        c.text(y, text.headline, font("serif", 72 if c.story else 56), PAPER, center=True)
    c.footer(text.footer)
    return c.png()


def _moon_glow(c: _Canvas) -> None:
    """The faint full moon of the promo images, top right."""
    r = 300 if c.story else 220
    cx, cy = c.w + 60, c.top + (180 if c.story else 60)
    c.d.ellipse(_box(cx, cy, r), fill=_alpha(PAPER, 0.06))


def has_glyphs(name: FontName, text: str) -> bool:
    """Whether the font draws every character (not the .notdef box): for the coverage test."""
    f = font(name, 48)

    def shape(ch: str) -> bytes:
        image = Image.new("L", (120, 120), 0)
        ImageDraw.Draw(image).text((10, 10), ch, font=f, fill=255)
        return image.tobytes()

    missing = shape("\U0010fffd")
    return all(ch.isspace() or shape(ch) != missing for ch in set(text))
