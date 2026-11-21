"""Draws share cards with Pillow (ST-07, ADR-0040). The only module that imports PIL; it is
loaded on the first card, never at startup, and runs in a worker thread.

It draws only what a card holds, with resolved text (`CardText`): no data access, no moon
computation, no emoji (moon days are drawn rings, the mark is drawn shapes), one brand
palette whatever the Telegram theme (`docs/brand/`). Output is deterministic for a card.
"""

import io
import random
import zlib
from calendar import monthrange
from collections.abc import Generator
from contextlib import contextmanager
from datetime import date, timedelta
from functools import cache
from importlib.resources import files
from math import cos, radians, sin
from typing import Literal

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from tristhana.domain.moon import MoonPhase
from tristhana.domain.share_cards import (
    AsanaCard,
    CardFormat,
    CardTone,
    CountCard,
    MonthCard,
    MoonCard,
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


# ST-10: the moon day card. Everything below is drawn from the card's phase alone: a simplified
# picture (not to scale, no real angles), the same for every date of that phase.
MOON_LIGHT: RGB = (250, 245, 232)
MOON_EDGE: RGB = (222, 210, 186)
MARE: RGB = (196, 186, 166)
NEW_MOON: RGB = (16, 18, 44)
EARTH: RGB = (92, 150, 204)
EARTH_NIGHT: RGB = (36, 52, 102)
_SS = 3  # supersampling for round shapes


def _stars(c: _Canvas, seed: int, keep_out: tuple[tuple[float, float, float], ...]) -> None:
    """A sparse starfield, the same for the same card (seeded), drawn on the background last:
    never within 15 px of anything already drawn (text, bodies), nor inside `keep_out` discs
    (the Moon's orbit, where a star would read as a body). Each star looks only at its own
    neighbourhood: a filter over the whole image took seconds and held the GIL (review)."""
    rng = random.Random(seed)  # noqa: S311 - a picture, not a secret
    alpha = c.layer.getchannel("A")
    d = ImageDraw.Draw(c.base)
    for _ in range(170 if c.story else 110):
        x, y = rng.uniform(0, c.w), rng.uniform(0, c.h)
        r = rng.choice((1.0, 1.2, 1.5, 1.5, 2.0, 2.6))
        a = rng.uniform(0.18, 0.75)
        px, py = int(x), int(y)
        if alpha.crop((px - 15, py - 15, px + 16, py + 16)).getbbox() or any(
            (x - kx) ** 2 + (y - ky) ** 2 < kr**2 for kx, ky, kr in keep_out
        ):
            continue  # the draw still uses the same random numbers: stable for a card
        d.ellipse(_box(x, y, r), fill=_alpha(PAPER, a))
        if r >= 2.6:  # a few brighter ones get a faint cross
            d.line((x - 7, y, x + 7, y), fill=_alpha(PAPER, a * 0.35), width=1)
            d.line((x, y - 7, x, y + 7), fill=_alpha(PAPER, a * 0.35), width=1)


def _glow(c: _Canvas, cx: float, cy: float, r: float, color: RGB, a: float, blur: float) -> None:
    pad = int(blur * 3)
    size = int(2 * r) + 2 * pad
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((pad, pad, pad + 2 * r, pad + 2 * r), fill=round(255 * a))
    mask = mask.filter(ImageFilter.GaussianBlur(blur))
    c.layer.alpha_composite(
        Image.composite(
            Image.new("RGBA", (size, size), (*color, 255)),
            Image.new("RGBA", (size, size), (*color, 0)),
            mask,
        ),
        (int(cx - r - pad), int(cy - r - pad)),
    )


def _disc(r: int, phase: MoonPhase) -> Image.Image:
    """The big moon, drawn supersampled: full = a lit disc with faint maria; new = a dark disc
    with a thin saffron rim."""
    n = 2 * r * _SS
    mask = Image.new("L", (n, n), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, n - 1, n - 1), fill=255)
    if phase is MoonPhase.PURNIMA:
        ramp = Image.radial_gradient("L").resize((n, n))  # pyright: ignore[reportUnknownMemberType]
        ramp = ramp.point([min(255, round(v * 1.25)) for v in range(256)])  # pyright: ignore[reportUnknownMemberType]
        body = ImageOps.colorize(ramp, MOON_LIGHT, MOON_EDGE).convert("RGBA")
        maria = Image.new("L", (n, n), 0)
        md = ImageDraw.Draw(maria)
        for fx, fy, fr, a in (
            (0.36, 0.34, 0.15, 0.55),
            (0.56, 0.30, 0.11, 0.45),
            (0.62, 0.50, 0.13, 0.5),
            (0.42, 0.58, 0.10, 0.4),
            (0.30, 0.50, 0.07, 0.35),
            (0.55, 0.70, 0.06, 0.3),
            (0.72, 0.36, 0.05, 0.3),
        ):
            md.ellipse(_box(fx * n, fy * n, fr * n), fill=round(255 * a * 0.55))
        maria = maria.filter(ImageFilter.GaussianBlur(n * 0.02))
        body.paste(Image.new("RGBA", (n, n), (*MARE, 255)), (0, 0), maria)
    else:
        ramp = Image.radial_gradient("L").resize((n, n))  # pyright: ignore[reportUnknownMemberType]
        body = ImageOps.colorize(ramp, (30, 34, 76), NEW_MOON).convert("RGBA")
        rim = Image.new("L", (n, n), 0)
        width = max(2, round(n * 0.012))
        ImageDraw.Draw(rim).ellipse((0, 0, n - 1, n - 1), outline=200, width=width)
        body.paste(Image.new("RGBA", (n, n), (*SAFFRON, 255)), (0, 0), rim)
    out = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    out.paste(body, (0, 0), mask)
    return out.resize((2 * r, 2 * r), Image.Resampling.LANCZOS)  # pyright: ignore[reportUnknownMemberType]


def _big_moon(c: _Canvas, cx: int, cy: int, r: int, phase: MoonPhase) -> None:
    if phase is MoonPhase.PURNIMA:
        _glow(c, cx, cy, r * 1.25, PAPER, 0.16, r * 0.35)
        _glow(c, cx, cy, r * 1.04, MOON_LIGHT, 0.35, r * 0.12)
    else:
        _glow(c, cx, cy, r * 1.06, SAFFRON, 0.22, r * 0.10)
    c.layer.alpha_composite(_disc(r, phase), (cx - r, cy - r))


def _body(c: _Canvas, cx: float, cy: float, r: float, lit: RGB, dark: RGB) -> None:
    """A small sphere lit from the left (where the Sun is): left half lit."""
    n = int(2 * r * _SS)
    im = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse((0, 0, n - 1, n - 1), fill=(*dark, 255))
    d.pieslice((0, 0, n - 1, n - 1), 90, 270, fill=(*lit, 255))
    im = im.resize((int(2 * r), int(2 * r)), Image.Resampling.LANCZOS)  # pyright: ignore[reportUnknownMemberType]
    c.layer.alpha_composite(im, (int(cx - r), int(cy - r)))


def _diagram_scale(c: _Canvas) -> float:
    return 1.0 if c.story else 0.8


def _diagram_height(c: _Canvas) -> int:
    """The height `_diagram` takes, from its top to below its labels."""
    s = _diagram_scale(c)
    return round(2 * _ORBIT * s + 10 + 14 * s + round(28 * s) * 1.3)


_ORBIT = 96  # the Moon's orbit radius in the diagram, at scale 1


def _diagram(
    c: _Canvas, y: int, phase: MoonPhase, labels: tuple[str, ...]
) -> tuple[int, tuple[float, float, float]]:
    """Sun, Earth and Moon on one line in the right order: at full moon the Earth is between
    the Sun and the Moon, at new moon the Moon is between them. Each is lit on the Sun side.
    Not to scale. Returns the y below the labels and the orbit's disc (centre x, y, radius)."""
    s = _diagram_scale(c)
    sun_r, earth_r, moon_r, orbit = 40 * s, 23 * s, 12 * s, _ORBIT * s
    cy = y + orbit + 10
    sun_x = c.pad + sun_r + 24 * s
    earth_x = c.w - c.pad - orbit - moon_r - 12
    moon_x = earth_x + orbit if phase is MoonPhase.PURNIMA else earth_x - orbit
    c.d.line((sun_x + sun_r + 26 * s, cy, c.w - c.pad, cy), fill=_alpha(SAFFRON, 0.22), width=2)
    for i in range(0, 72, 2):  # the Moon's orbit, dotted
        c.d.arc(_box(earth_x, cy, orbit), i * 5, i * 5 + 5, fill=_alpha(PAPER, 0.35), width=2)
    _glow(c, sun_x, cy, sun_r * 1.5, SAFFRON, 0.45, sun_r * 0.5)
    for i in range(12):  # short rays
        a = radians(i * 30)
        r0, r1 = sun_r + 8 * s, sun_r + 20 * s
        c.d.line(
            (sun_x + r0 * cos(a), cy + r0 * sin(a), sun_x + r1 * cos(a), cy + r1 * sin(a)),
            fill=_alpha(SAFFRON, 0.8),
            width=max(2, round(3 * s)),
        )
    c.d.ellipse(_box(sun_x, cy, sun_r), fill=SAFFRON)
    _body(c, earth_x, cy, earth_r, EARTH, EARTH_NIGHT)
    _body(c, moon_x, cy, moon_r, MOON_LIGHT, (70, 72, 100))
    f = font("sans", round(28 * s))
    ly = round(cy + orbit + 14 * s)  # below the orbit
    ink = _alpha(SOFT, 0.72)
    for x, label in zip((sun_x, earth_x, moon_x), labels, strict=False):
        c.d.text((x, ly), label, font=f, fill=ink, anchor="mt")
    return ly + round(int(f.size) * 1.3), (earth_x, cy, orbit + moon_r + 6)


def _pill(c: _Canvas, left: float | None, y: int, text: str, size: int) -> int:
    """A saffron kicker; centred when `left` is None. Returns the y below it."""
    kf = font("sans-bold", size)
    label = text.upper()
    ph = round(size * 1.85)
    w = c.d.textlength(label, font=kf) + 2 * round(size * 0.8)
    x = (c.w - w) / 2 if left is None else left
    c.d.rounded_rectangle((x, y, x + w, y + ph), ph // 2, fill=SAFFRON)
    c.d.text((x + w / 2, y + ph / 2), label, font=kf, fill=INDIGO, anchor="mm")
    return y + ph


def draw_moon(card: MoonCard, fmt: CardFormat, text: CardText) -> bytes:
    """ST-10. The story shows every note; the square only the first (the rest-day line)."""
    c = _Canvas(fmt)
    seed = card.date.toordinal() * 7919 + zlib.crc32(card.city.slug.encode())
    if c.story:
        r, cx = 165, c.w // 2
        y = _pill(c, None, c.header(), text.title, 30)
        cy = y + 44 + r
        _big_moon(c, cx, cy, r, card.phase)
        y = cy + r + 48
        y = c.text(y, text.headline, font("serif", 100), PAPER, center=True, max_lines=1)
        y = c.text(y, text.subline, font("serif", 50), SAFFRON, center=True, max_lines=1)
        y = c.text(y + 4, text.iast, font("sans", 30), _alpha(SOFT, 0.6), center=True)
        y += 22
        for i, line in enumerate(text.lines):
            f = c.fit(line, "sans", 40 if i == 0 else 34, c.inner)
            y = c.text(y, line, f, PAPER if i == 0 else SOFT, center=True, spacing=1.4)
        y, orbit = _diagram(c, y + 4, card.phase, text.diagram)
        y += 4
        step = round(28 * 1.38)
        # The notes come most important first; any that would reach the footer are left out.
        for note in text.notes[: max(0, (c.limit - y) // step)]:
            f = c.fit(note, "sans", 28, c.inner)
            y = c.text(y, note, f, _alpha(SOFT, 0.72), center=True, spacing=1.38, max_lines=1)
    else:
        r = 170
        cx, cy = c.pad + r + 6, c.header() + 40 + r
        _big_moon(c, cx, cy, r, card.phase)
        col = cx + r + 64
        width = c.w - c.pad - col
        y = _pill(c, col, cy - r + 4, text.title, 24) + 22
        hf = c.fit(text.headline, "serif", 76, width)
        c.d.text((col, y), text.headline, font=hf, fill=PAPER)
        y += round(int(hf.size) * 1.22)
        sf = c.fit(text.subline, "serif", 42, width)
        c.d.text((col, y), text.subline, font=sf, fill=SAFFRON)
        y += round(int(sf.size) * 1.3)
        af = c.fit(text.iast, "sans", 26, width)
        c.d.text((col, y), text.iast, font=af, fill=_alpha(SOFT, 0.6))
        y += 58
        for i, line in enumerate(text.lines):
            f = font("sans", 30 if i == 0 else 27)
            for part in c.wrap(line, f, width):
                c.d.text((col, y), part, font=f, fill=PAPER if i == 0 else SOFT)
                y += round(int(f.size) * 1.3)
            y += 8
        # The diagram and the rest-day line share the room left above the footer.
        top = max(cy + r, y) + 16
        block = _diagram_height(c) + 14 + 40  # the diagram, then one note
        y = top + max(0, (c.limit - top - block) // 2)
        y, orbit = _diagram(c, y, card.phase, text.diagram)
        y += 14
        if text.notes and y + 28 <= c.limit:
            f = c.fit(text.notes[0], "sans", 28, c.inner)
            c.text(y, text.notes[0], f, _alpha(SOFT, 0.72), center=True, max_lines=1)
    c.footer(text.footer)
    _stars(c, seed, (orbit,))
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
