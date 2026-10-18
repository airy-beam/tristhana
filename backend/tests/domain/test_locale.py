import pytest

from tristhana.domain.locale import negotiate_locale


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("ru", "ru"),
        ("ru-RU", "ru"),
        ("RU", "ru"),
        ("be", "ru"),
        ("kk", "ru"),
        ("ky", "ru"),
        ("uk", "en"),
        ("en", "en"),
        ("en-GB", "en"),
        ("de", "en"),
        ("", "en"),
        (None, "en"),
    ],
)
def test_negotiate_locale(code: str | None, expected: str) -> None:
    assert negotiate_locale(code) == expected
