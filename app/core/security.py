"""Credential encryption.

Account passwords are encrypted at rest with Fernet (AES-128-CBC + HMAC).
The encryption key resolution order is:

1. ``PUBLISHER_ENCRYPTION_KEY`` environment variable (recommended for
   production / Docker deployments).
2. A key file ``data/.secret.key`` generated on first run with restrictive
   permissions.

Plain-text passwords never touch the database or logs.
"""

from __future__ import annotations

import contextlib
import os
import stat
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import DATA_DIR
from app.core.exceptions import CredentialError

_KEY_FILE = DATA_DIR / ".secret.key"
_ENV_VAR = "PUBLISHER_ENCRYPTION_KEY"


def _load_or_create_key() -> bytes:
    """Resolve the Fernet key from env or key file, creating one if needed."""
    env_key = os.environ.get(_ENV_VAR, "")
    if env_key:
        return env_key.encode()

    if _KEY_FILE.exists():
        return _KEY_FILE.read_bytes().strip()

    key = Fernet.generate_key()
    _KEY_FILE.write_bytes(key)
    with contextlib.suppress(OSError):  # Restrict to owner where the OS supports it
        _KEY_FILE.chmod(stat.S_IRUSR | stat.S_IWUSR)
    return key


class CredentialVault:
    """Encrypts and decrypts credential strings."""

    def __init__(self, key: bytes | None = None) -> None:
        self._fernet = Fernet(key or _load_or_create_key())

    def encrypt(self, plaintext: str) -> str:
        """Encrypt a secret; returns a token safe to store in SQLite."""
        if not plaintext:
            raise CredentialError("Cannot encrypt an empty credential")
        return self._fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")

    def decrypt(self, token: str) -> str:
        """Decrypt a stored token back to the plain secret."""
        try:
            return self._fernet.decrypt(token.encode("ascii")).decode("utf-8")
        except (InvalidToken, ValueError) as exc:
            raise CredentialError(
                "Failed to decrypt credential - the encryption key may have changed."
            ) from exc

    @staticmethod
    def generate_key() -> str:
        """Generate a new key (for provisioning PUBLISHER_ENCRYPTION_KEY)."""
        return Fernet.generate_key().decode("ascii")


def get_vault() -> CredentialVault:
    """Factory used by dependency injection."""
    return CredentialVault()


def key_file_path() -> Path:
    """Expose the key file location (for documentation / backup guidance)."""
    return _KEY_FILE
