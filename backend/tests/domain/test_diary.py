"""Diary note (PR-07, ADR-0025): normalising free text. Plain text only, up to 2000 code points
after normalising, trimmed, blank means "delete", too long is refused (never cut). Pure.

`tristhana.domain.diary` is imported inside the tests (test-first: the rest of the suite
keeps collecting before the module exists)."""

from typing import Any

import pytest


def _m() -> Any:
    from tristhana.domain import diary

    return diary


def _normalize(text: str) -> str | None:
    return _m().normalize_note(text)


def test_the_limit_is_2000() -> None:
    assert _m().MAX_CHARS == 2000


def test_note_too_long_is_a_value_error() -> None:
    assert issubclass(_m().NoteTooLong, ValueError)


def test_plain_text_comes_back_as_is() -> None:
    assert _normalize("Felt light today. Teacher gave Marichyasana D.") == (
        "Felt light today. Teacher gave Marichyasana D."
    )


def test_crlf_becomes_lf() -> None:
    assert _normalize("line one\r\nline two\r\n\r\nline four") == "line one\nline two\n\nline four"


def test_controls_are_dropped_except_newline_and_tab() -> None:
    # C0 (NUL, BEL, ESC, US) and C1 (NEL, CSI, APC) go; \n and \t stay.
    text = "a\x00b\x07c\x1bd\x1fe\x85f\x9bg\x9fh\ti\nj"

    assert _normalize(text) == "abcdefgh\ti\nj"


def test_ends_are_stripped_and_the_inside_kept() -> None:
    assert _normalize("  \n\t  breath  was   steady \n  \t") == "breath  was   steady"


@pytest.mark.parametrize("blank", ["", " ", "\n\n", " \t \r\n ", "\x00\x01", "\u0085"])
def test_blank_means_delete(blank: str) -> None:
    assert _normalize(blank) is None


@pytest.mark.parametrize("char", ["a", "ж", "🧘", "\t"])
def test_exactly_2000_code_points_fit(char: str) -> None:
    text = "x" + char * 1998 + "y"  # 2000 code points; a tab inside is kept

    assert _normalize(text) == text


@pytest.mark.parametrize("char", ["a", "ж", "🧘"])
def test_2001_code_points_are_refused(char: str) -> None:
    m = _m()

    with pytest.raises(m.NoteTooLong):
        m.normalize_note(char * 2001)


def test_an_emoji_counts_as_one() -> None:
    text = "🧘" * 2000  # 8000 UTF-8 bytes, 4000 UTF-16 units: still 2000 code points

    assert _normalize(text) == text


def test_cyrillic_counts_per_letter() -> None:
    text = "Сегодня практика была лёгкой. " * 66 + "Ура"  # 30 x 66 + 3 = 1983  # noqa: RUF001

    assert _normalize(text) == text.strip()


def test_the_length_is_counted_after_normalising() -> None:
    padded = "  " + "a" * 2000 + "\n\n  "
    crlf = "a\r\n" * 1000  # 3000 code points as sent, 2000 after CRLF → LF, 1999 trimmed
    controls = "a" * 2000 + "\x00" * 50

    assert _normalize(padded) == "a" * 2000
    assert _normalize(crlf) == ("a\n" * 1000).strip()
    assert _normalize(controls) == "a" * 2000


def test_too_long_never_carries_the_text() -> None:
    m = _m()
    secret = "my private words " * 200  # 3400 code points

    with pytest.raises(m.NoteTooLong) as raised:
        m.normalize_note(secret)

    assert "private" not in str(raised.value)
    assert "private" not in repr(raised.value.args)


def test_markup_is_just_text() -> None:
    text = "<b>bold</b> *stars* _under_ [link](http://x) `code`"

    assert _normalize(text) == text


def test_a_diary_note_holds_text_or_none_when_unreadable() -> None:
    m = _m()

    assert m.DiaryNote("hi").text == "hi"
    assert m.DiaryNote(None).text is None
    assert m.DiaryNote("hi") == m.DiaryNote("hi")
    with pytest.raises(AttributeError):
        m.DiaryNote("hi").text = "changed"  # frozen


def test_lone_surrogates_are_dropped() -> None:
    # Valid in JSON ("\\ud800"), but not encodable as UTF-8: it would fail on sealing.
    assert _normalize("a\ud800b\udfffc") == "abc"
    assert _normalize("\ud83e") is None
