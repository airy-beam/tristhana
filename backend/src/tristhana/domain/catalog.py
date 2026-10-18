"""Asana catalog: asanas, variants, series and shared blocks. Seeded from data/seed/*.yaml.

Items are identified by natural keys (`asana` or `asana-variant`), never by position (ADR-0010).
"""

import re
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from itertools import groupby


class SequenceKind(StrEnum):
    SERIES = "series"
    BLOCK = "block"


class SequenceStatus(StrEnum):
    CONFIRMED = "confirmed"
    PENDING = "pending"  # content will be provided (Advanced C)
    PLACEHOLDER = "placeholder"  # no reliable source yet (Advanced D)


BLOCK_SLUGS = frozenset({"opening", "standing", "backbending", "finishing"})
SERIES_NUMBERS = frozenset(range(1, 7))
STOP_BLOCK = "standing"  # "standing only" practice ends at its last item


@dataclass(frozen=True, slots=True)
class AsanaNames:
    latin: str  # simple Latin, the primary display ("Marichyasana")
    iast: str | None  # metadata ("Marīcyāsana"); None for non-asana entries (drop-backs)
    ru: str  # Cyrillic transliteration ("Маричиасана")


@dataclass(frozen=True, slots=True)
class Meaning:
    en: str
    ru: str


@dataclass(frozen=True, slots=True)
class Asana:
    slug: str
    names: AsanaNames
    meaning: Meaning
    variants: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SequenceItem:
    asana: str
    variant: str | None = None
    stop: bool = False  # a practice can end here
    optional: bool = False  # not part of the implied practice unless enabled
    milestone: bool = False  # a teacher "gives" it (progression, PR-08)

    @property
    def key(self) -> str:
        return f"{self.asana}-{self.variant}" if self.variant else self.asana


@dataclass(frozen=True, slots=True)
class SequenceNames:
    en: str
    ru: str


@dataclass(frozen=True, slots=True)
class Sequence:
    slug: str
    kind: SequenceKind
    status: SequenceStatus
    names: SequenceNames
    items: tuple[SequenceItem, ...]
    number: int | None = None  # series only, 1-6
    traditional_name: AsanaNames | None = None  # series only ("Yoga Chikitsa")


@dataclass(frozen=True, slots=True)
class Catalog:
    asanas: tuple[Asana, ...]
    sequences: tuple[Sequence, ...]
    reviewed_by: str | None = None
    reviewed_on: date | None = None


@dataclass(frozen=True, slots=True)
class CatalogIssue:
    where: str
    message: str

    def __str__(self) -> str:
        return f"{self.where}: {self.message}"


def groups(sequence: Sequence) -> list[tuple[SequenceItem, ...]]:
    """Picker groups: runs of consecutive items of the same asana (e.g. Janu Sirsasana A-C)."""
    return [tuple(run) for _, run in groupby(sequence.items, key=lambda i: i.asana)]


_SLUG = re.compile(r"[a-z]+(-[a-z]+)*")
_VARIANT = re.compile(r"[a-z]")
_LATIN = re.compile(r"[A-Za-z]+([ -][A-Za-z]+)*")
# Cyrillic U+0410-U+044F (excludes ё). Variant letters are added at display time, not stored.
_RU = re.compile(r"[\u0410-\u044f]+([ -][\u0410-\u044f]+)*")
_IAST = re.compile(
    r"[A-Za-zĀāĪīŪūṚṛṜṝḶḷḸḹṄṅÑñṬṭḌḍṆṇŚśṢṣṂṃḤḥ]+([ -][A-Za-zĀāĪīŪūṚṛṜṝḶḷḸḹṄṅÑñṬṭḌḍṆṇŚśṢṣṂṃḤḥ]+)*"
)
_CYRILLIC = re.compile(r"[\u0401\u0410-\u044f\u0451]")


def validate_catalog(catalog: Catalog) -> list[CatalogIssue]:
    """All integrity problems in the catalog (empty when valid)."""
    return list(_issues(catalog))


def _issues(catalog: Catalog) -> Iterator[CatalogIssue]:
    yield from _asana_issues(catalog.asanas)
    if catalog.reviewed_by is not None:
        yield from _text_issues("catalog", "reviewed_by", catalog.reviewed_by)

    asanas = {a.slug: a for a in catalog.asanas}
    used: set[str] = set()
    for seq in catalog.sequences:
        yield from _sequence_issues(seq, asanas)
        used.update(i.key for i in seq.items)
        used.update(i.asana for i in seq.items)

    for a in catalog.asanas:
        for key in [a.slug, *(f"{a.slug}-{v}" for v in a.variants)]:
            if key not in used:
                yield CatalogIssue(f"asana {a.slug}", f"'{key}' is not used by any sequence")

    numbers = sorted(
        s.number for s in catalog.sequences if s.kind is SequenceKind.SERIES and s.number
    )
    if numbers != sorted(SERIES_NUMBERS):
        yield CatalogIssue(
            "catalog", f"series numbers must be exactly 1-6 once each, got {numbers}"
        )
    blocks = sorted(s.slug for s in catalog.sequences if s.kind is SequenceKind.BLOCK)
    if blocks != sorted(BLOCK_SLUGS):
        yield CatalogIssue("catalog", f"blocks must be exactly {sorted(BLOCK_SLUGS)}, got {blocks}")
    for slug, n in Counter(s.slug for s in catalog.sequences).items():
        if n > 1:
            yield CatalogIssue("catalog", f"duplicate sequence slug '{slug}'")


def _text_issues(where: str, field: str, text: str) -> Iterator[CatalogIssue]:
    if not text.strip() or text != text.strip() or "\n" in text:
        yield CatalogIssue(where, f"{field} must be non-empty, trimmed and single-line")


def _asana_issues(asanas: tuple[Asana, ...]) -> Iterator[CatalogIssue]:
    slugs = Counter(a.slug for a in asanas)
    for slug, n in slugs.items():
        if n > 1:
            yield CatalogIssue("catalog", f"duplicate asana slug '{slug}'")

    for a in asanas:
        where = f"asana {a.slug}"
        if not _SLUG.fullmatch(a.slug):
            yield CatalogIssue(where, "slug must be ASCII kebab-case")
        for v, n in Counter(a.variants).items():
            if not _VARIANT.fullmatch(v):
                yield CatalogIssue(where, f"variant code '{v}' must be one lowercase letter")
            if n > 1:
                yield CatalogIssue(where, f"duplicate variant '{v}'")
            if f"{a.slug}-{v}" in slugs:
                yield CatalogIssue(where, f"variant key '{a.slug}-{v}' collides with an asana slug")
        yield from _name_issues(where, "names", a.names)
        yield from _text_issues(where, "meaning.en", a.meaning.en)
        yield from _text_issues(where, "meaning.ru", a.meaning.ru)
        if not _CYRILLIC.search(a.meaning.ru):
            yield CatalogIssue(where, "meaning.ru must be Cyrillic text")


def _name_issues(where: str, field: str, names: AsanaNames) -> Iterator[CatalogIssue]:
    if not _LATIN.fullmatch(names.latin):
        yield CatalogIssue(where, f"{field}.latin {names.latin!r}: ASCII letters, spaces, hyphens")
    if not _RU.fullmatch(names.ru):
        yield CatalogIssue(
            where, f"{field}.ru {names.ru!r}: Cyrillic letters (no ё), spaces, hyphens"
        )
    if names.iast is not None and not _IAST.fullmatch(names.iast):
        yield CatalogIssue(where, f"{field}.iast {names.iast!r}: IAST letters only (ṃ, not ṁ)")


def _sequence_issues(seq: Sequence, asanas: dict[str, Asana]) -> Iterator[CatalogIssue]:
    where = seq.slug
    yield from _text_issues(where, "names.en", seq.names.en)
    yield from _text_issues(where, "names.ru", seq.names.ru)
    for item in seq.items:
        asana = asanas.get(item.asana)
        if asana is None:
            yield CatalogIssue(where, f"unknown asana '{item.asana}'")
        elif item.variant is not None and item.variant not in asana.variants:
            yield CatalogIssue(where, f"unknown variant '{item.variant}' of '{item.asana}'")
        if item.optional and item.stop:
            yield CatalogIssue(where, f"{item.key}: an optional item cannot be a stop point")
        if item.milestone and not item.optional:
            yield CatalogIssue(where, f"{item.key}: a milestone must be optional")
    for key, n in Counter(i.key for i in seq.items).items():
        if n > 1:
            yield CatalogIssue(where, f"item '{key}' appears twice")

    if seq.kind is SequenceKind.SERIES:
        yield from _series_issues(seq)
    else:
        yield from _block_issues(seq)


def _series_issues(seq: Sequence) -> Iterator[CatalogIssue]:
    if seq.number not in SERIES_NUMBERS:
        yield CatalogIssue(seq.slug, f"series number must be 1-6, got {seq.number}")
    if seq.traditional_name is not None:
        yield from _name_issues(seq.slug, "traditional_name", seq.traditional_name)
    if seq.status is SequenceStatus.CONFIRMED and not seq.items:
        yield CatalogIssue(seq.slug, "confirmed series must have items")
    if seq.status is not SequenceStatus.CONFIRMED and seq.items:
        yield CatalogIssue(seq.slug, f"{seq.status} series must be empty")
    required = [i for i in seq.items if not i.optional]
    if seq.items and (not required or not required[-1].stop):
        yield CatalogIssue(seq.slug, "must end on a stop point")


def _block_issues(seq: Sequence) -> Iterator[CatalogIssue]:
    if seq.number is not None or seq.traditional_name is not None:
        yield CatalogIssue(seq.slug, "blocks have no number or traditional name")
    if seq.status is not SequenceStatus.CONFIRMED or not seq.items:
        yield CatalogIssue(seq.slug, "blocks must be confirmed and non-empty")
    stops = [i for i in seq.items if i.stop]
    if seq.slug == STOP_BLOCK:
        if len(stops) != 1 or not seq.items or seq.items[-1] is not stops[0]:
            yield CatalogIssue(seq.slug, "must have exactly one stop point, on its last item")
    elif stops:
        yield CatalogIssue(seq.slug, "blocks other than standing have no stop points")
