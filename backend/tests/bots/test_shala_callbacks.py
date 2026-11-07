"""The `h1:` callback data for shalas (SC-01 spec §5, ADR-0008): stateless, versioned, uuids as
22-character base64url so two fit, the longest at 50 bytes, anything malformed decodes to
None. The meaning of each tap is pinned through the webhook in `test_shalas_bot.py`."""

import re
from uuid import UUID, uuid4

import pytest

from tristhana.bots.telegram.shalas_callbacks import PREFIX, decode, parse_short_id, short_id

CODE = "aB3dE6gH9jK2mN5p"
MAX = UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")


def test_the_prefix_is_free() -> None:
    from tristhana.bots.telegram import teacher_links_callbacks

    assert PREFIX == "h1"
    assert teacher_links_callbacks.PREFIX != PREFIX


@pytest.mark.parametrize("id_", [UUID(int=0), MAX, UUID(int=2**64 + 7), uuid4()])
def test_short_ids_round_trip_in_22_url_safe_characters(id_: UUID) -> None:
    short = short_id(id_)

    assert re.fullmatch(r"[A-Za-z0-9_-]{22}", short)
    assert parse_short_id(short) == id_


@pytest.mark.parametrize(
    "value",
    ["", "short", "A" * 21, "A" * 23, "A" * 21 + "=", "A" * 21 + "+", "A" * 21 + ":", str(MAX)],
)
def test_a_malformed_short_id_is_none(value: str) -> None:
    assert parse_short_id(value) is None


def test_a_non_canonical_short_id_is_none() -> None:
    """The last character carries 4 spare bits that a lenient decoder ignores: only the
    canonical form decodes, so one id has one callback string."""
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
    canonical = short_id(MAX)
    last = alphabet.index(canonical[-1])
    twin = alphabet[(last & 0b110000) | ((last + 1) & 0b001111)]  # same 2 data bits

    assert twin != canonical[-1]
    assert parse_short_id(canonical[:-1] + twin) is None


def _all(shala: UUID, acct: UUID) -> list[str]:
    s, a = short_id(shala), short_id(acct)
    return [
        f"h1:a:{CODE}",
        "h1:n",
        f"h1:l:ru:{CODE}",
        f"h1:l:en:{CODE}",
        f"h1:b:{CODE}",
        f"h1:c:{s}",
        f"h1:m:{s}:0",
        f"h1:m:{s}:99",
        f"h1:v:{s}:{a}",
        f"h1:i:{s}",
        f"h1:q:{s}",
        f"h1:w:{s}",
        f"h1:wy:{s}",
        f"h1:e:{s}",
        *(f"h1:e:{s}:{r}" for r in "taom"),
        f"h1:u:{s}:{a}",
        f"h1:x:{s}:{a}",
        f"h1:k:{s}",
        f"h1:ky:{s}",
    ]


@pytest.mark.parametrize("data", _all(MAX, MAX))
def test_every_tap_decodes_and_fits(data: str) -> None:
    assert decode(data) is not None
    assert len(data.encode()) <= 50  # `h1:x:` + 22 + `:` + 22; Telegram allows 64


@pytest.mark.parametrize(
    "data",
    [
        None,
        "",
        "h1",
        "h1:",
        "h2:n",
        "t1:n",
        "h1:a",
        "h1:a:short",
        f"h1:a:{CODE}x",
        f"h1:b:{CODE}-",
        f"h1:l:de:{CODE}",
        "h1:l:ru:short",
        "h1:c:not-an-id",
        f"h1:c:{uuid4()}",  # the long form is no id here
        f"h1:m:{short_id(MAX)}:-1",
        f"h1:m:{short_id(MAX)}:x",
        f"h1:m:{short_id(MAX)}:12345",
        f"h1:v:{short_id(MAX)}",
        f"h1:e:{short_id(MAX)}:z",
        f"h1:e:{short_id(MAX)}:admin",
        f"h1:x:{short_id(MAX)}:short",
        f"h1:zz:{short_id(MAX)}",
        "h1:n:extra",
    ],
)
def test_malformed_data_is_none(data: str | None) -> None:
    assert decode(data) is None
