"""`CodeSource`: invite codes from the OS's secure random source (ID-04)."""

import secrets
import string

from tristhana.domain.teacher_links import CODE_LENGTH

_ALPHABET = string.ascii_letters + string.digits


class SecretCodes:
    def new(self) -> str:
        return "".join(secrets.choice(_ALPHABET) for _ in range(CODE_LENGTH))


class SecretTokens:
    """SC-06 calendar feed tokens: 256 bits, 43 base64url characters."""

    def new(self) -> str:
        return secrets.token_urlsafe(32)
