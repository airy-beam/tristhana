import base64

import pytest

from tristhana.application.ports.storage import StorageUnavailable
from tristhana.infrastructure.crypto import FieldCipher, MissingCipher, UnreadableSeal

KEY_1 = "1:" + base64.b64encode(b"\x01" * 32).decode()
KEY_2 = "2:" + base64.b64encode(b"\x02" * 32).decode()
AAD = b"day_log.sealed_status|account|2026-10-18"


def test_round_trip() -> None:
    cipher = FieldCipher(KEY_1)

    assert cipher.open(cipher.seal(b"l", AAD), AAD) == b"l"


def test_seals_are_randomized_and_equal_length() -> None:
    cipher = FieldCipher(KEY_1)

    rest, ladies, again = cipher.seal(b"r", AAD), cipher.seal(b"l", AAD), cipher.seal(b"l", AAD)

    assert len(rest) == len(ladies) == 1 + 24 + 1 + 16
    assert ladies != again


def test_a_seal_only_opens_in_its_place() -> None:
    cipher = FieldCipher(KEY_1)
    sealed = cipher.seal(b"l", AAD)

    with pytest.raises(UnreadableSeal):
        cipher.open(sealed, b"day_log.sealed_status|other-account|2026-10-18")


def test_tampering_is_detected() -> None:
    cipher = FieldCipher(KEY_1)
    sealed = bytearray(cipher.seal(b"l", AAD))
    sealed[-1] ^= 1

    with pytest.raises(UnreadableSeal):
        cipher.open(bytes(sealed), AAD)


def test_rotation_new_key_seals_old_key_still_opens() -> None:
    old = FieldCipher(KEY_1).seal(b"l", AAD)
    rotated = FieldCipher(f"{KEY_2},{KEY_1}")

    assert rotated.open(old, AAD) == b"l"
    assert rotated.seal(b"l", AAD)[0] == 2
    with pytest.raises(UnreadableSeal):
        FieldCipher(KEY_2).open(old, AAD)  # retired key: unreadable, never a crash


@pytest.mark.parametrize(
    "keyring",
    [
        "",
        "1:short",
        "x:" + KEY_1[2:],
        "0:" + KEY_1[2:],
        "+1:" + KEY_1[2:],
        "1_0:" + KEY_1[2:],
        "\u0661:" + KEY_1[2:],  # Arabic-Indic digit one
        f"{KEY_1},{KEY_1}",
        "1:not base64!",
    ],
)
def test_bad_keyrings_are_rejected(keyring: str) -> None:
    with pytest.raises(ValueError, match="field encryption keys"):
        FieldCipher(keyring)


def test_missing_cipher_is_unavailable_not_plain_text() -> None:
    with pytest.raises(StorageUnavailable):
        MissingCipher().seal(b"l", AAD)


@pytest.mark.parametrize("sealed", [b"", b"\x01", b"\x01" + bytes(24), b"\x01" + bytes(40)])
def test_truncated_seals_are_unreadable_not_errors(sealed: bytes) -> None:
    with pytest.raises(UnreadableSeal):
        FieldCipher(KEY_1).open(sealed, AAD)
