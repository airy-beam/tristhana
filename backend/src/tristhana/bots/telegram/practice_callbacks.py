"""Callback data for the practice-details screens (PR-02), versioned `p1:`; dates absolute.

    p1:o:20261018              details screen P          p1:v:20261018   done → summary V
    p1:c:20261018:m            context (m l i s)         p1:n:20261018:1 online on (0 off)
    p1:s:20261018              same as last time         p1:x:20261018   remove details
    p1:m:20261018              length screen L           p1:a:20261018   series screen O
    p1:d:20261018              duration screen D         p1:t:20261018:90 duration (0 none)
    p1:r:20261018:2            range screen S, last series 2
    p1:g:20261018:12a:1        asana grid, range "12a", page 1
    p1:l:20261018:12a:pasasana set the length (range "00" = short; no key = full last series)

A range is "<first series number><last series number>", plus "a"/"b" when the first series
is only its first/second half. Asana keys are natural keys (ADR-0010), never positions.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Literal

from tristhana.domain.days import MIN_LOG_DATE
from tristhana.domain.practice import (
    SHORT,
    FirstPart,
    PracticeCatalog,
    PracticeContext,
    PracticeLength,
)

PREFIX = "p1"
type Action = Literal[
    "open", "done", "context", "online", "same", "clear", "lengths", "series", "durations",
    "range", "grid", "length", "duration",
]  # fmt: skip

_SIMPLE: dict[str, Action] = {
    "o": "open", "v": "done", "s": "same", "x": "clear", "m": "lengths", "a": "series",
    "d": "durations",
}  # fmt: skip
_LETTER = {a: k for k, a in _SIMPLE.items()} | {
    "context": "c", "online": "n", "range": "r", "grid": "g", "length": "l", "duration": "t",
}  # fmt: skip
_CONTEXTS = {
    "m": PracticeContext.MYSORE,
    "l": PracticeContext.LED,
    "i": PracticeContext.PRIVATE,
    "s": PracticeContext.SELF,
}
_CONTEXT_CODES = {v: k for k, v in _CONTEXTS.items()}
_PARTS: dict[str, FirstPart] = {"a": "first_half", "b": "second_half"}
_PART_CODES = {v: k for k, v in _PARTS.items()}
_LATEST = date.max - timedelta(days=31)


@dataclass(frozen=True, slots=True)
class Range:
    first: int  # 0 = short practice
    last: int
    first_part: FirstPart | None = None

    def code(self) -> str:
        return f"{self.first}{self.last}{_PART_CODES[self.first_part] if self.first_part else ''}"

    def length(self, catalog: PracticeCatalog, end: str | None) -> PracticeLength | None:
        if self.first == 0:
            return SHORT
        slugs: list[str] = []
        for n in range(self.first, self.last + 1):
            series = catalog.by_number(n)
            if series is None:
                return None
            slugs.append(series.slug)
        return PracticeLength(tuple(slugs), end, self.first_part)

    @classmethod
    def of(cls, catalog: PracticeCatalog, length: PracticeLength) -> "Range | None":
        if not length.series:
            return cls(0, 0)
        first, last = catalog.get(length.series[0]), catalog.get(length.series[-1])
        if first is None or last is None:
            return None
        return cls(first.number, last.number, length.first_part)

    @classmethod
    def parse(cls, code: str) -> "Range | None":
        part = _PARTS.get(code[2:]) if len(code) == 3 else None
        if len(code) not in (2, 3) or not code[:2].isdigit() or (len(code) == 3 and part is None):
            return None
        first, last = int(code[0]), int(code[1])
        if (first == 0) != (last == 0) or first > last or (first == 0 and part):
            return None
        return cls(first, last, part)


@dataclass(frozen=True, slots=True)
class PracticeCallback:
    action: Action
    day: date
    context: PracticeContext | None = None
    flag: bool = False  # online on/off
    number: int = 0  # duration minutes, series number, grid page
    range: Range | None = None
    key: str | None = None  # asana key for "length"


def encode(cb: PracticeCallback) -> str:
    base = f"{PREFIX}:{_LETTER[cb.action]}:{cb.day:%Y%m%d}"
    match cb.action:
        case "context":
            assert cb.context is not None  # noqa: S101
            return f"{base}:{_CONTEXT_CODES[cb.context]}"
        case "online":
            return f"{base}:{int(cb.flag)}"
        case "duration" | "range":
            return f"{base}:{cb.number}"
        case "grid":
            assert cb.range is not None  # noqa: S101
            return f"{base}:{cb.range.code()}:{cb.number}"
        case "length":
            assert cb.range is not None  # noqa: S101
            return f"{base}:{cb.range.code()}:{cb.key or ''}"
        case _:
            return base


def decode(data: str | None) -> PracticeCallback | None:
    """None for anything malformed (old or forged keyboards stay harmless)."""
    parts = (data or "").split(":")
    if len(parts) < 3 or parts[0] != PREFIX:
        return None
    try:
        day = datetime.strptime(parts[2], "%Y%m%d").date()
    except ValueError:
        return None
    if not MIN_LOG_DATE <= day <= _LATEST:
        return None
    letter, rest = parts[1], parts[3:]
    if letter in _SIMPLE and not rest:
        return PracticeCallback(_SIMPLE[letter], day)
    match letter, rest:
        case "c", [code] if code in _CONTEXTS:
            return PracticeCallback("context", day, context=_CONTEXTS[code])
        case "n", ["0" | "1" as flag]:
            return PracticeCallback("online", day, flag=flag == "1")
        case "t", [minutes] if minutes.isdigit() and int(minutes) <= 600:
            return PracticeCallback("duration", day, number=int(minutes))
        case "r", [n] if n.isdigit() and 2 <= int(n) <= 6:
            return PracticeCallback("range", day, number=int(n))
        case "g", [code, page] if page.isdigit() and int(page) < 20 and Range.parse(code):
            return PracticeCallback("grid", day, number=int(page), range=Range.parse(code))
        case "l", [code, key] if Range.parse(code) and len(key) <= 64:
            return PracticeCallback("length", day, range=Range.parse(code), key=key or None)
        case _:
            return None
