"""Field-level encryption (ADR-0016): XChaCha20-Poly1305 (libsodium, via PyNaCl).

Sealed value = key id (1 byte) ‖ nonce (24 random bytes) ‖ ciphertext + tag (16 bytes).
The AAD binds a value to its place (table, column, row), so a sealed value copied to
another row or account doesn't open.
"""

import base64
import binascii
import secrets

from nacl import bindings
from nacl.exceptions import CryptoError

from tristhana.application.ports.storage import StorageUnavailable

_NONCE = bindings.crypto_aead_xchacha20poly1305_ietf_NPUBBYTES
_KEY = bindings.crypto_aead_xchacha20poly1305_ietf_KEYBYTES
_TAG = bindings.crypto_aead_xchacha20poly1305_ietf_ABYTES


class UnreadableSeal(Exception):
    """Unknown key id, wrong key, wrong place (AAD) or tampered bytes."""


class FieldCipher:
    def __init__(self, keyring: str) -> None:
        """`keyring` = "<id>:<base64 32-byte key>[,…]"; the first key seals, all open."""
        self._keys: dict[int, bytes] = {}
        self._active = -1
        for entry in (e.strip() for e in keyring.split(",") if e.strip()):
            raw_id, _, raw_key = entry.partition(":")
            if not (raw_id.isascii() and raw_id.isdigit()):
                raise ValueError("field encryption keys: expected <id>:<base64>")
            try:
                key_id, key = int(raw_id), base64.b64decode(raw_key, validate=True)
            except (ValueError, binascii.Error):
                raise ValueError("field encryption keys: expected <id>:<base64>") from None
            if not 1 <= key_id <= 255 or len(key) != _KEY or key_id in self._keys:
                raise ValueError("field encryption keys: ids 1-255, unique, 32-byte keys")
            self._keys[key_id] = key
            if self._active < 0:
                self._active = key_id
        if self._active < 0:
            raise ValueError("field encryption keys: none given")

    def seal(self, plaintext: bytes, aad: bytes) -> bytes:
        nonce = secrets.token_bytes(_NONCE)
        sealed = bindings.crypto_aead_xchacha20poly1305_ietf_encrypt(
            plaintext, aad, nonce, self._keys[self._active]
        )
        return bytes([self._active]) + nonce + sealed

    def open(self, sealed: bytes, aad: bytes) -> bytes:
        if len(sealed) < 1 + _NONCE + _TAG:
            raise UnreadableSeal("truncated")
        key = self._keys.get(sealed[0])
        if key is None:
            raise UnreadableSeal("unknown key id")
        nonce, body = sealed[1 : 1 + _NONCE], sealed[1 + _NONCE :]
        try:
            return bindings.crypto_aead_xchacha20poly1305_ietf_decrypt(body, aad, nonce, key)
        except CryptoError:
            raise UnreadableSeal("authentication failed") from None


class MissingCipher:
    """No FIELD_ENCRYPTION_KEYS (dev without a key): private values are unavailable, never
    stored in plain text."""

    def seal(self, plaintext: bytes, aad: bytes) -> bytes:
        raise StorageUnavailable("field encryption key not configured")

    def open(self, sealed: bytes, aad: bytes) -> bytes:
        raise StorageUnavailable("field encryption key not configured")
