# ruff: noqa: RUF001
"""The ICS serializer (SC-06 spec §3, §7, §8; ADR-0036): `tristhana.api.ics.render(feed) ->
bytes`, a pure function. A byte-exact golden body: CRLF everywhere; the VCALENDAR headers in
the spec's order; per event `UID`, `DTSTAMP` (the link's `created_at`), `DTSTART`/`DTEND` in
UTC `…Z` or `;VALUE=DATE` (moon: `DTEND` the next day, then `TRANSP:TRANSPARENT`), `SUMMARY`,
`DESCRIPTION`, `LOCATION` (a property with no value is left out); 75-octet folding on UTF-8
boundaries (an emoji straddles the fold in a RU title); TEXT escaping of `\\ ; ,` and newlines
in a staff name; a stripped control character; no `SEQUENCE`, `VTIMEZONE`, `RRULE`, `VALARM`.

`icalendar` is a dev-only validator (spec §8): the parse test runs only when it is installed
(`pytest.importorskip`)."""

from dataclasses import replace
from datetime import UTC, date, datetime
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest

from tristhana.api.ics import render
from tristhana.application.calendar_feed import Feed
from tristhana.domain.calendar_feed import FeedEvent

CLASS = UUID("0b0e5c1a-6d8e-4f3e-9a51-000000000001")
LED = UUID("0b0e5c1a-6d8e-4f3e-9a51-000000000002")
STAMP = datetime(2026, 11, 1, 9, 15, 30, 123456, tzinfo=UTC)
RU_TITLE = "Утренний майсор для всех уровней · 🧘 Анна"
# A staff name as typed: a comma, a semicolon, a backslash, a newline and a BEL.
ODD_NAME = "Dana, Jr.; \\o/\nsecond\x07line"
MOON_NOTE_RU = (
    "Даты рассчитаны по городу 📍 Майсур (лунные сутки на восходе). Календарь твоей шалы может"
    " отличаться на день: ориентируйся на своего учителя."
)


def _feed() -> Feed:
    return Feed(
        name="Tristhana: моё расписание",
        stamp=STAMP,
        events=(
            FeedEvent(
                uid=f"{CLASS}-20261109@tristhana",
                summary=RU_TITLE,
                description="Ashtanga Almaty\nClass time: 06:00 Almaty (UTC+5)",
                location="Ashtanga Almaty, Abaya 10; studio \\2",
                start=datetime(2026, 11, 9, 1, 0, tzinfo=UTC),
                end=datetime(2026, 11, 9, 3, 30, tzinfo=UTC),
                all_day=False,
            ),
            FeedEvent(
                uid=f"{LED}-20261113@tristhana",
                summary=f"Led · {ODD_NAME}",
                description="Dana (for Anna)",
                location=None,
                start=datetime(2026, 11, 13, 13, 0, tzinfo=UTC),
                end=datetime(2026, 11, 13, 14, 30, tzinfo=UTC),
                all_day=False,
            ),
            FeedEvent(
                uid="moon-20261124@tristhana",
                summary="🌕 Полнолуние (Пурнима)",
                description=MOON_NOTE_RU,
                location=None,
                start=date(2026, 11, 24),
                end=date(2026, 11, 25),
                all_day=True,
            ),
        ),
    )


GOLDEN_LINES = [
    "BEGIN:VCALENDAR",
    "VERSION:2.0",
    "PRODID:-//Tristhana//SC-06//EN",
    "CALSCALE:GREGORIAN",
    "METHOD:PUBLISH",
    "X-WR-CALNAME:Tristhana: моё расписание",
    "REFRESH-INTERVAL;VALUE=DURATION:PT6H",
    "X-PUBLISHED-TTL:PT6H",
    "BEGIN:VEVENT",
    f"UID:{CLASS}-20261109@tristhana",
    "DTSTAMP:20261101T091530Z",
    "DTSTART:20261109T010000Z",
    "DTEND:20261109T033000Z",
    # 72 octets: the next character, 🧘, is 4 octets and would cross 75.
    "SUMMARY:Утренний майсор для всех уровней · ",
    " 🧘 Анна",
    "DESCRIPTION:Ashtanga Almaty\\nClass time: 06:00 Almaty (UTC+5)",
    "LOCATION:Ashtanga Almaty\\, Abaya 10\\; studio \\\\2",
    "END:VEVENT",
    "BEGIN:VEVENT",
    f"UID:{LED}-20261113@tristhana",
    "DTSTAMP:20261101T091530Z",
    "DTSTART:20261113T130000Z",
    "DTEND:20261113T143000Z",
    "SUMMARY:Led · Dana\\, Jr.\\; \\\\o/\\nsecondline",
    "DESCRIPTION:Dana (for Anna)",
    "END:VEVENT",
    "BEGIN:VEVENT",
    "UID:moon-20261124@tristhana",
    "DTSTAMP:20261101T091530Z",
    "DTSTART;VALUE=DATE:20261124",
    "DTEND;VALUE=DATE:20261125",
    "TRANSP:TRANSPARENT",
    "SUMMARY:🌕 Полнолуние (Пурнима)",
    "DESCRIPTION:Даты рассчитаны по городу 📍 Майсу",  # 75 octets
    " р (лунные сутки на восходе). Календарь тв",
    " оей шалы может отличаться на день: ориен",
    " тируйся на своего учителя.",
    "END:VEVENT",
    "END:VCALENDAR",
]
GOLDEN = ("\r\n".join(GOLDEN_LINES) + "\r\n").encode()


def _physical(body: bytes) -> list[bytes]:
    assert body.endswith(b"\r\n")
    return body[:-2].split(b"\r\n")


def _logical(body: bytes) -> list[str]:
    return body.decode().replace("\r\n ", "").split("\r\n")[:-1]


def _value(body: bytes, name: str) -> list[str]:
    return [line.split(":", 1)[1] for line in _logical(body) if line.split(":", 1)[0] == name]


def _event(summary: str, **kw: object) -> FeedEvent:
    values: dict[str, object] = {
        "uid": f"{CLASS}-20261109@tristhana",
        "summary": summary,
        "description": None,
        "location": None,
        "start": datetime(2026, 11, 9, 1, 0, tzinfo=UTC),
        "end": datetime(2026, 11, 9, 3, 30, tzinfo=UTC),
        "all_day": False,
    }
    values.update(kw)
    return FeedEvent(**values)  # type: ignore[arg-type]


def _one(event: FeedEvent) -> bytes:
    return render(Feed(name="Tristhana: my schedule", stamp=STAMP, events=(event,)))


# The golden body


def test_the_golden_body_byte_for_byte() -> None:
    assert render(_feed()) == GOLDEN


def test_the_golden_fixture_obeys_its_own_rules() -> None:
    """Pins the fixture: CRLF only, every physical line ≤ 75 octets and valid UTF-8."""
    for line in _physical(GOLDEN):
        assert b"\n" not in line
        assert b"\r" not in line
        assert len(line) <= 75, line
        line.decode()  # no split sequence


def test_same_feed_same_bytes() -> None:
    assert render(_feed()) == render(_feed())


def test_dtstamp_is_the_link_creation_not_now() -> None:
    later = replace(_feed(), stamp=datetime(2027, 1, 2, 3, 4, 5, tzinfo=UTC))

    assert set(_value(render(_feed()), "DTSTAMP")) == {"20261101T091530Z"}
    assert set(_value(render(later), "DTSTAMP")) == {"20270102T030405Z"}


# Line endings and folding


def test_every_line_ends_with_crlf() -> None:
    body = render(_feed())

    assert body.count(b"\n") == body.count(b"\r\n")
    assert body.count(b"\r") == body.count(b"\r\n")


@pytest.mark.parametrize("pad", range(0, 80))
@pytest.mark.parametrize("tail", ["🧘🌕📍" * 12, "Майсор Пурнима " * 8, "a·b—c✓" * 15])
def test_folding_never_splits_a_character(pad: int, tail: str) -> None:
    """A deterministic sweep: the multi-octet characters land on every offset of the fold."""
    summary = "x" * pad + tail

    body = _one(_event(summary))

    for line in _physical(body):
        assert len(line) <= 75, line
        line.decode()  # raises on a split UTF-8 sequence
    assert _value(body, "SUMMARY") == [summary]


def test_a_fold_fills_the_line_greedily() -> None:
    """Continuation lines are one space plus up to 74 octets; a fold happens only when the
    next character would not fit."""
    summary = "a" * 200

    lines = [ln.decode() for ln in _physical(_one(_event(summary)))]

    start = next(i for i, ln in enumerate(lines) if ln.startswith("SUMMARY:"))
    assert lines[start] == "SUMMARY:" + "a" * 67
    assert lines[start + 1] == " " + "a" * 74
    assert lines[start + 2] == " " + "a" * 59


def test_a_short_line_is_not_folded() -> None:
    body = _one(_event("Mysore · Anna"))

    assert b"SUMMARY:Mysore \xc2\xb7 Anna\r\n" in body
    assert not any(ln.startswith(b" ") for ln in _physical(body))


# Escaping and stripping


@pytest.mark.parametrize(
    ("raw", "escaped"),
    [
        ("a,b", "a\\,b"),
        ("a;b", "a\\;b"),
        ("a\\b", "a\\\\b"),
        ("a\nb", "a\\nb"),
        ("a\r\nb", "a\\nb"),
        ("a\x00b\x07c\x1bd\x7fe", "abcde"),
        ("\\,;\n", "\\\\\\,\\;\\n"),
        ("Tristhana: моё расписание", "Tristhana: моё расписание"),  # a colon stays
    ],
)
def test_text_values_are_escaped(raw: str, escaped: str) -> None:
    body = _one(_event(raw, description=raw, location=raw))

    for name in ("SUMMARY", "DESCRIPTION", "LOCATION"):
        [value] = _value(body, name)
        assert value == escaped, name


def test_the_calendar_name_is_escaped_too() -> None:
    body = render(Feed(name="A, b; c\\d", stamp=STAMP, events=()))

    assert _value(body, "X-WR-CALNAME") == ["A\\, b\\; c\\\\d"]


# Instants and dates


def test_an_instant_in_another_zone_is_written_in_utc() -> None:
    almaty = ZoneInfo("Asia/Almaty")
    event = _event(
        "Mysore",
        start=datetime(2026, 11, 9, 6, 0, tzinfo=almaty),
        end=datetime(2026, 11, 9, 8, 30, tzinfo=almaty),
    )

    body = _one(event)

    assert _value(body, "DTSTART") == ["20261109T010000Z"]
    assert _value(body, "DTEND") == ["20261109T033000Z"]


@pytest.mark.parametrize(
    ("start", "expected"),
    [
        (datetime(2026, 10, 23, 4, 30, tzinfo=UTC), "20261023T043000Z"),  # 06:30 CEST
        (datetime(2026, 10, 26, 5, 30, tzinfo=UTC), "20261026T053000Z"),  # 06:30 CET
    ],
    ids=["berlin-summer", "berlin-winter"],
)
def test_a_dst_zone_class_is_its_utc_instant(start: datetime, expected: str) -> None:
    body = _one(_event("Mysore · Anna", start=start, end=start))

    assert _value(body, "DTSTART") == [expected]
    assert b"TZID" not in body


def test_an_all_day_event_is_a_date_with_the_next_day_as_end() -> None:
    lines = _logical(render(_feed()))

    assert "DTSTART;VALUE=DATE:20261124" in lines
    assert "DTEND;VALUE=DATE:20261125" in lines
    assert "TRANSP:TRANSPARENT" in lines
    assert lines.count("TRANSP:TRANSPARENT") == 1  # classes block time as usual


def test_what_the_body_never_has() -> None:
    body = render(_feed())

    for word in (b"VTIMEZONE", b"TZID", b"RRULE", b"EXDATE", b"SEQUENCE", b"VALARM", b"STATUS"):
        assert word not in body, word


def test_an_empty_feed_is_a_valid_calendar() -> None:
    body = render(Feed(name="Tristhana: my schedule", stamp=STAMP, events=()))

    assert _logical(body) == [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Tristhana//SC-06//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:Tristhana: my schedule",
        "REFRESH-INTERVAL;VALUE=DURATION:PT6H",
        "X-PUBLISHED-TTL:PT6H",
        "END:VCALENDAR",
    ]


# A dev-only validator


def test_icalendar_parses_the_golden_body() -> None:
    icalendar = pytest.importorskip("icalendar")

    calendar = icalendar.Calendar.from_ical(render(_feed()))

    events = list(calendar.walk("VEVENT"))
    assert [str(e["UID"]) for e in events] == [
        f"{CLASS}-20261109@tristhana",
        f"{LED}-20261113@tristhana",
        "moon-20261124@tristhana",
    ]
    assert str(events[0]["SUMMARY"]) == RU_TITLE
    assert str(events[1]["SUMMARY"]) == "Led · Dana, Jr.; \\o/\nsecondline"
    assert events[0].decoded("DTSTART") == datetime(2026, 11, 9, 1, 0, tzinfo=UTC)
    assert events[2].decoded("DTSTART") == date(2026, 11, 24)
    assert str(events[2]["DESCRIPTION"]) == MOON_NOTE_RU
