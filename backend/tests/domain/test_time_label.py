"""ADR-0044: a displayed time always names its place; the UTC offset shows only outside the
viewer's own IANA zone. Pure (`zoneinfo` only): the city name is the formatter's business.
The Mini App's `timeLabel.test.ts` holds the same cases, one for one."""

from datetime import date, time

import pytest

from tristhana.domain.time_label import ZONE_ALIASES, offset_shown, offset_text

DAY = date(2026, 11, 16)
AT = time(7)


def test_no_offset_in_the_viewers_own_zone() -> None:
    assert offset_shown("Asia/Almaty", "Asia/Almaty") is False


def test_another_zone_shows_the_offset() -> None:
    assert offset_shown("Europe/Berlin", "Asia/Almaty") is True


def test_another_zone_with_the_same_offset_still_shows_it() -> None:
    """Names are compared, not clocks: Almaty and Tashkent are both UTC+5 today."""
    assert offset_text("Asia/Almaty", DAY, AT) == offset_text("Asia/Tashkent", DAY, AT)
    assert offset_shown("Asia/Tashkent", "Asia/Almaty") is True


def test_an_unknown_viewer_zone_shows_the_offset() -> None:
    assert offset_shown("Asia/Almaty", None) is True


@pytest.mark.parametrize("viewer", [None, "UTC", "Asia/Almaty"])
def test_utc_never_gets_an_offset(viewer: str | None) -> None:
    """`07:00 UTC` already says it."""
    assert offset_shown("UTC", viewer) is False


def test_a_utc_viewer_sees_the_offset_of_a_place() -> None:
    assert offset_shown("Asia/Almaty", "UTC") is True


@pytest.mark.parametrize(
    ("zone", "day", "text"),
    [
        ("Asia/Almaty", DAY, "UTC+5"),
        ("Asia/Kolkata", DAY, "UTC+5:30"),  # a half-hour zone
        ("Asia/Kathmandu", DAY, "UTC+5:45"),
        ("America/New_York", date(2026, 1, 15), "UTC-5"),
        ("America/St_Johns", date(2026, 1, 15), "UTC-3:30"),
        ("Europe/London", date(2026, 1, 15), "UTC+0"),
        ("Europe/Berlin", date(2026, 3, 28), "UTC+1"),  # the day before the change
        ("Europe/Berlin", date(2026, 3, 29), "UTC+2"),  # 07:00 on the daylight-saving date
        ("Europe/Berlin", date(2026, 10, 25), "UTC+1"),
    ],
)
def test_the_offset_is_the_one_on_that_date(zone: str, day: date, text: str) -> None:
    assert offset_text(zone, day, AT) == text


def test_the_offset_is_the_one_at_that_time_on_a_change_night() -> None:
    change = date(2026, 3, 29)  # Berlin: 02:00 → 03:00

    assert offset_text("Europe/Berlin", change, time(1, 30)) == "UTC+1"
    assert offset_text("Europe/Berlin", change, time(3, 30)) == "UTC+2"


@pytest.mark.parametrize("day", [date(2026, 3, 28), date(2026, 3, 29), date(2026, 7, 1)])
def test_the_answer_never_flips_on_a_daylight_saving_date(day: date) -> None:
    """Berlin and Paris always share a clock, London and Lisbon too: still different zones.
    The rule takes no date at all."""
    assert offset_shown("Europe/Berlin", "Europe/Berlin") is False
    assert offset_shown("Europe/Paris", "Europe/Berlin") is True
    assert offset_text("Europe/Paris", day, AT) == offset_text("Europe/Berlin", day, AT)


# One zone, two names: what Chrome and Android's WebView still report (CLDR's ids), and IANA's
# own name (the seeded cities, Firefox). The same table as in `timeLabel.test.ts`.
ALIASES = [
    ("Africa/Asmera", "Africa/Asmara"),
    ("America/Buenos_Aires", "America/Argentina/Buenos_Aires"),
    ("America/Catamarca", "America/Argentina/Catamarca"),
    ("America/Cordoba", "America/Argentina/Cordoba"),
    ("America/Jujuy", "America/Argentina/Jujuy"),
    ("America/Mendoza", "America/Argentina/Mendoza"),
    ("America/Coral_Harbour", "America/Atikokan"),
    ("America/Godthab", "America/Nuuk"),
    ("America/Indianapolis", "America/Indiana/Indianapolis"),
    ("America/Louisville", "America/Kentucky/Louisville"),
    ("Asia/Calcutta", "Asia/Kolkata"),
    ("Asia/Katmandu", "Asia/Kathmandu"),
    ("Asia/Rangoon", "Asia/Yangon"),
    ("Asia/Saigon", "Asia/Ho_Chi_Minh"),
    ("Atlantic/Faeroe", "Atlantic/Faroe"),
    ("Europe/Kiev", "Europe/Kyiv"),
    ("Pacific/Enderbury", "Pacific/Kanton"),
    ("Pacific/Ponape", "Pacific/Pohnpei"),
    ("Pacific/Truk", "Pacific/Chuuk"),
]


@pytest.mark.parametrize(("alias", "name"), ALIASES)
def test_two_names_of_one_zone_are_the_viewers_own_zone(alias: str, name: str) -> None:
    """A person in Mysuru whose phone says `Asia/Calcutta` reads `07:00 Mysuru`, no offset."""
    assert offset_shown(name, alias) is False
    assert offset_shown(alias, name) is False
    assert offset_shown(alias, alias) is False


def test_the_alias_table_is_exactly_this_one() -> None:
    """The twin's test holds the same list: a name added on one side fails on the other."""
    assert dict(ALIASES) == ZONE_ALIASES
    assert not set(ZONE_ALIASES) & set(ZONE_ALIASES.values())  # no chains


@pytest.mark.parametrize(("alias", "name"), [ALIASES[10], ALIASES[15]])
def test_both_names_keep_the_same_clock(alias: str, name: str) -> None:
    assert offset_text(alias, DAY, AT) == offset_text(name, DAY, AT)


def test_an_alias_is_still_another_zone_for_everyone_else() -> None:
    """Kolkata and Colombo share a clock: still two zones, under either name."""
    assert offset_shown("Asia/Calcutta", "Asia/Colombo") is True
    assert offset_shown("Asia/Colombo", "Asia/Calcutta") is True
    assert offset_shown("Europe/Kiev", "Europe/Berlin") is True
    assert offset_shown("Asia/Calcutta", None) is True
