"""Tests for the credential vault."""

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

from app.core.exceptions import CredentialError
from app.core.security import CredentialVault


def test_encrypt_roundtrip():
    vault = CredentialVault(Fernet.generate_key())
    token = vault.encrypt("s3cret-password!")
    assert token != "s3cret-password!"
    assert vault.decrypt(token) == "s3cret-password!"


def test_ciphertext_is_not_plaintext():
    vault = CredentialVault(Fernet.generate_key())
    token = vault.encrypt("hello")
    assert "hello" not in token


def test_wrong_key_fails():
    vault_a = CredentialVault(Fernet.generate_key())
    vault_b = CredentialVault(Fernet.generate_key())
    token = vault_a.encrypt("password")
    with pytest.raises(CredentialError):
        vault_b.decrypt(token)


def test_empty_credential_rejected():
    vault = CredentialVault(Fernet.generate_key())
    with pytest.raises(CredentialError):
        vault.encrypt("")


def test_generate_key_is_valid():
    key = CredentialVault.generate_key()
    vault = CredentialVault(key.encode())
    assert vault.decrypt(vault.encrypt("x")) == "x"
