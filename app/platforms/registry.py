"""Platform registry (plugin system).

Platforms self-register at import time via the ``@register_platform``
decorator, so adding a portal never requires editing engine code.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.exceptions import ConfigurationError

if TYPE_CHECKING:
    from app.platforms.base import BasePlatform

_REGISTRY: dict[str, type[BasePlatform]] = {}


def register_platform[T: "type[BasePlatform]"](cls: T) -> T:
    """Class decorator registering a platform implementation by its ``name``."""
    if not cls.name:
        raise ConfigurationError(f"{cls.__name__} must define a non-empty 'name'")
    if cls.name in _REGISTRY:
        raise ConfigurationError(f"Platform '{cls.name}' is registered twice")
    _REGISTRY[cls.name] = cls
    return cls


def get_platform_class(name: str) -> type[BasePlatform]:
    """Look up a platform implementation; raises with the available names."""
    normalized = name.strip().lower().replace(" ", "")
    if normalized not in _REGISTRY:
        raise ConfigurationError(
            f"Unknown platform '{name}'. Available: {', '.join(sorted(_REGISTRY)) or 'none'}"
        )
    return _REGISTRY[normalized]


def available_platforms() -> dict[str, type[BasePlatform]]:
    """All registered platforms keyed by machine name."""
    return dict(_REGISTRY)
