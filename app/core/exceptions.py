"""Application-wide exception hierarchy.

Every error raised by the publisher derives from :class:`PublisherError`
so callers can catch a single base class at orchestration boundaries.
"""

from __future__ import annotations


class PublisherError(Exception):
    """Base class for all application errors."""


class ConfigurationError(PublisherError):
    """Raised when configuration is missing or invalid."""


class ValidationError(PublisherError):
    """Raised when a property row fails required-field validation."""

    def __init__(self, message: str, missing_fields: list[str] | None = None) -> None:
        super().__init__(message)
        self.missing_fields = missing_fields or []


class CredentialError(PublisherError):
    """Raised when credentials/API keys are missing, invalid, or cannot be decrypted."""


class SheetError(PublisherError):
    """Raised on Google Sheets / Excel read or write failures."""


class AIError(PublisherError):
    """Raised when AI content generation fails."""


class ImageError(PublisherError):
    """Raised on image processing failures."""


class ReferenceDataError(PublisherError):
    """Raised when a spreadsheet value cannot be mapped to a Property Oryx ID."""


class OryxApiError(PublisherError):
    """Raised when the Property Oryx API returns an error response.

    Carries the HTTP status and the API's machine-readable error codes so the
    engine can decide whether a retry makes sense (5xx/timeout) or not (4xx).
    """

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        codes: list[str] | None = None,
        endpoint: str = "",
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.codes = codes or []
        self.endpoint = endpoint

    @property
    def is_retryable(self) -> bool:
        """Network/server errors are retryable; validation/auth errors are not."""
        if self.status_code is None:
            return True  # connection/timeout error
        return self.status_code >= 500


class AuthError(OryxApiError):
    """Raised on 401/403 from the API (invalid or unauthorised API key)."""


class LoginError(AuthError):
    """Backwards-compatible alias used by the platform login step."""


class PublishError(PublisherError):
    """Raised when a listing could not be created/published."""


class UploadError(PublisherError):
    """Raised when an image upload to Property Oryx fails."""


class NotificationError(PublisherError):
    """Raised when a notification channel fails to deliver."""
