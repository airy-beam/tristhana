import json
from pathlib import Path

import pytest

from tristhana.domain.locale import negotiate_locale

# Shared with the Mini App tests (miniapp/src/i18n/negotiate.test.ts).
CASES = json.loads(
    (Path(__file__).resolve().parents[3] / "data" / "i18n" / "locale_cases.json").read_text()
)["cases"]


@pytest.mark.parametrize(("code", "expected"), CASES)
def test_negotiate_locale(code: str | None, expected: str) -> None:
    assert negotiate_locale(code) == expected
