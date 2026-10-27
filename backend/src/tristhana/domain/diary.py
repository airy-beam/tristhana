"""Diary note (PR-07, ADR-0025): one private free-text note per local day, any status.

Plain text only. Notes are never parsed or interpreted: no keyword detection, inferences or
advice (spec §1).
"""

import re
from dataclasses import dataclass

MAX_CHARS = 2000  # code points, after normalising

# C0 and C1 controls except \t and \n (CR is handled first: CRLF → LF), and lone surrogates
# (valid JSON, but not encodable as UTF-8).
_CONTROLS = re.compile("[\x00-\x08\x0b-\x1f\x7f-\x9f\ud800-\udfff]")


class NoteTooLong(ValueError):
    """Carries the length only, never the text."""


@dataclass(frozen=True, slots=True)
class DiaryNote:
    text: str | None  # None = a note exists but its seal can't be opened (lost key)


def normalize_note(text: str) -> str | None:
    """The note as stored; None = blank (delete it). Raises `NoteTooLong` past 2000 code
    points (refused, never cut)."""
    cleaned = _CONTROLS.sub("", text.replace("\r\n", "\n")).strip()
    if not cleaned:
        return None
    if len(cleaned) > MAX_CHARS:
        raise NoteTooLong(len(cleaned))
    return cleaned
