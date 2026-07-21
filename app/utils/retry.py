"""Retry helper with exponential backoff.

Used by the publishing engine and API calls. Non-retryable errors (validation,
auth, 4xx) can be excluded via ``no_retry`` so they fail fast.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from functools import wraps
from typing import ParamSpec, TypeVar

from app.core.logging import get_logger

P = ParamSpec("P")
T = TypeVar("T")

logger = get_logger(__name__)


def compute_backoff(
    attempt: int,
    base: float = 5.0,
    multiplier: float = 2.0,
    max_seconds: float = 300.0,
) -> float:
    """Exponential backoff delay for a 1-based attempt number."""
    return min(base * (multiplier ** (attempt - 1)), max_seconds)


def retry_with_backoff(
    max_attempts: int = 3,
    base: float = 5.0,
    multiplier: float = 2.0,
    max_seconds: float = 300.0,
    retry_on: tuple[type[Exception], ...] = (Exception,),
    no_retry: tuple[type[Exception], ...] = (),
    on_retry: Callable[[int, Exception], None] | None = None,
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """Decorator: retry the wrapped callable with exponential backoff.

    Exceptions in ``no_retry`` always propagate immediately.
    """

    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            last_exc: Exception | None = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except no_retry:
                    raise
                except retry_on as exc:
                    last_exc = exc
                    if attempt == max_attempts:
                        break
                    delay = compute_backoff(attempt, base, multiplier, max_seconds)
                    logger.warning(
                        "%s attempt %d/%d failed (%s); retrying in %.0fs",
                        func.__qualname__, attempt, max_attempts, exc, delay,
                    )
                    if on_retry is not None:
                        on_retry(attempt, exc)
                    time.sleep(delay)
            assert last_exc is not None
            raise last_exc

        return wrapper

    return decorator
