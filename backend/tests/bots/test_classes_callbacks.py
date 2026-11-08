"""The `c1:` callback data for classes (SC-02 spec §5, ADR-0008): a free prefix, uuids as
SC-01's 22-character base64url, dates as `yyyymmdd`, weeks 0-3, the longest at 59 bytes (Telegram
allows 64), anything malformed decodes to None. The meaning of each tap is pinned through the
webhook in `test_classes_bot.py`.

Assumed module: `tristhana.bots.telegram.classes_callbacks` (as SC-01's `shalas_callbacks`)."""

from uuid import UUID, uuid4

import pytest

from tristhana.bots.telegram.classes_callbacks import PREFIX, decode
from tristhana.bots.telegram.shalas_callbacks import short_id

MAX = UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")


def test_the_prefix_is_free() -> None:
    from tristhana.bots.telegram import shalas_callbacks, teacher_links_callbacks

    assert PREFIX == "c1"
    assert PREFIX not in {shalas_callbacks.PREFIX, teacher_links_callbacks.PREFIX}


def _all(shala: UUID, cls: UUID) -> list[str]:
    s, c = short_id(shala), short_id(cls)
    return [
        *(f"c1:w:{s}:{week}" for week in range(4)),
        f"c1:p:{s}",
        *(f"c1:{kind}:{s}:{c}:20261113" for kind in "oxrh"),
        f"c1:d:{s}",
    ]


@pytest.mark.parametrize("data", _all(MAX, MAX))
def test_every_tap_decodes_and_fits(data: str) -> None:
    assert decode(data) is not None
    assert len(data.encode()) <= 59  # `c1:x:` + 22 + `:` + 22 + `:` + 8


def test_the_longest_is_59_bytes() -> None:
    assert max(len(d.encode()) for d in _all(MAX, MAX)) == 59


@pytest.mark.parametrize(
    "data",
    [
        None,
        "",
        "c1",
        "c1:",
        "c2:p:" + short_id(MAX),
        "h1:p:" + short_id(MAX),
        f"c1:w:{short_id(MAX)}",
        f"c1:w:{short_id(MAX)}:4",  # weeks 0-3
        f"c1:w:{short_id(MAX)}:-1",
        f"c1:w:{short_id(MAX)}:x",
        f"c1:p:{uuid4()}",  # the long form is no id here
        "c1:p:short",
        f"c1:o:{short_id(MAX)}:{short_id(MAX)}",
        f"c1:o:{short_id(MAX)}:{short_id(MAX)}:2026-11-13",
        f"c1:o:{short_id(MAX)}:{short_id(MAX)}:20261332",  # no such date
        f"c1:x:{short_id(MAX)}:{short_id(MAX)}:2026111",
        f"c1:z:{short_id(MAX)}",
        f"c1:d:{short_id(MAX)}:extra",
    ],
)
def test_malformed_data_is_none(data: str | None) -> None:
    assert decode(data) is None
