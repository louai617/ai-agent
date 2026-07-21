"""Platform plugin contract (transport-agnostic).

A platform is any listing destination. Property Oryx is implemented against
its official REST API, but the contract does not assume a browser or an API -
each platform decides how ``publish``/``update``/``delete`` are carried out.

To add a platform, create ``app/platforms/<name>/platform.py`` with a class
inheriting ``BasePlatform``, decorate it with ``@register_platform``, and
implement the lifecycle. No existing code needs to change (Open/Closed).
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.core.config import AppConfig, get_config
from app.core.logging import get_logger
from app.models.schemas import PropertyData, PublishResult

logger = get_logger(__name__)


class BasePlatform(ABC):
    """Abstract base every listing destination implements.

    Lifecycle used by the publishing engine::

        platform = SomePlatform(credential)
        platform.login()                       # verify the credential works
        result = platform.publish(data, image_paths)
        platform.logout()
    """

    #: unique machine name (matches the "Platform" value in the sheet)
    name: str = ""
    #: human-readable name for the UI
    display_name: str = ""

    def __init__(self, credential: str, config: AppConfig | None = None) -> None:
        self.credential = credential
        self.config = config or get_config()

    # ------------------------------------------------------------- contract

    @abstractmethod
    def login(self) -> None:
        """Verify the credential/API key; raise ``AuthError`` on failure."""

    @abstractmethod
    def is_authenticated(self) -> bool:
        """Cheap check that the credential is currently valid."""

    @abstractmethod
    def publish(self, data: PropertyData, image_paths: list[str]) -> PublishResult:
        """Create and publish a listing; returns its ID and URL."""

    @abstractmethod
    def update(self, external_id: str, data: PropertyData, image_paths: list[str]) -> PublishResult:
        """Update an existing listing identified by ``external_id``."""

    @abstractmethod
    def delete(self, external_id: str, category: str) -> bool:
        """Remove the listing identified by ``external_id``."""

    @abstractmethod
    def logout(self) -> None:
        """Release any session resources (no-op for stateless API clients)."""
