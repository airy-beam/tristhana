"""Shared screen helpers. `app_url` (UI-06 §3): the one builder of Mini App URLs with an
`open` target. The `open` values are a contract: old messages keep their URLs."""

import pytest

from tristhana.bots.telegram.screens import app_url

APP = "https://tristhana.web.app"


def test_no_target_is_the_plain_app() -> None:
    assert app_url(APP) == APP
    assert app_url(APP, None) == APP


@pytest.mark.parametrize("target", ["new-shala", "practice", "listing", "announce"])
def test_a_target_goes_into_open(target: str) -> None:
    assert app_url(APP, target) == f"{APP}?open={target}"


def test_parameters_follow_open_in_the_order_given() -> None:
    shala = "11111111-1111-4111-8111-111111111111"

    assert app_url(APP, "announce", shala=shala) == f"{APP}?open=announce&shala={shala}"
    assert app_url(APP, "x", b="2", a="1") == f"{APP}?open=x&b=2&a=1"


def test_a_missing_parameter_is_left_out() -> None:
    assert app_url(APP, "announce", shala=None) == f"{APP}?open=announce"


def test_a_base_with_a_query_keeps_it() -> None:
    assert app_url(f"{APP}/?v=2", "new-shala") == f"{APP}/?v=2&open=new-shala"


def test_values_are_encoded() -> None:
    assert app_url(APP, "a b", q="x&y=z") == f"{APP}?open=a+b&q=x%26y%3Dz"
