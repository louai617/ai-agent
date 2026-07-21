"""Tests for the platform registry and retry helper."""

from __future__ import annotations

import pytest

import app.platforms  # noqa: F401 - triggers registration
from app.core.exceptions import AuthError, ConfigurationError, OryxApiError
from app.platforms.base import BasePlatform
from app.platforms.registry import available_platforms, get_platform_class
from app.utils.retry import compute_backoff, retry_with_backoff


def test_only_property_oryx_is_registered():
    platforms = available_platforms()
    assert set(platforms) == {"propertyoryx"}
    cls = platforms["propertyoryx"]
    assert issubclass(cls, BasePlatform)
    for method in ("login", "publish", "update", "delete", "logout", "is_authenticated"):
        assert callable(getattr(cls, method))


def test_lookup_normalises_name():
    assert get_platform_class("Property Oryx").name == "propertyoryx"


def test_unknown_platform_raises():
    with pytest.raises(ConfigurationError, match="Unknown platform"):
        get_platform_class("nonexistent")


def test_backoff_is_exponential_and_capped():
    assert compute_backoff(1, base=5, multiplier=2) == 5
    assert compute_backoff(2, base=5, multiplier=2) == 10
    assert compute_backoff(3, base=5, multiplier=2) == 20
    assert compute_backoff(10, base=5, multiplier=2, max_seconds=60) == 60


def test_retry_decorator_retries_then_succeeds(monkeypatch):
    monkeypatch.setattr("app.utils.retry.time.sleep", lambda _s: None)
    calls = {"n": 0}

    @retry_with_backoff(max_attempts=3, base=0.01)
    def flaky() -> str:
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("boom")
        return "ok"

    assert flaky() == "ok"
    assert calls["n"] == 3


def test_retry_decorator_respects_no_retry(monkeypatch):
    monkeypatch.setattr("app.utils.retry.time.sleep", lambda _s: None)
    calls = {"n": 0}

    @retry_with_backoff(max_attempts=3, base=0.01, no_retry=(AuthError,))
    def blocked() -> None:
        calls["n"] += 1
        raise AuthError("nope", status_code=401)

    with pytest.raises(AuthError):
        blocked()
    assert calls["n"] == 1


def test_oryx_api_error_retryable_classification():
    assert OryxApiError("net", status_code=None).is_retryable is True
    assert OryxApiError("server", status_code=503).is_retryable is True
    assert OryxApiError("bad", status_code=400).is_retryable is False
    assert AuthError("auth", status_code=401).is_retryable is False
