"""Property Oryx Agents API client.

A thin, typed wrapper over the REST API documented at
``https://mqdyqyic12.execute-api.ap-southeast-1.amazonaws.com``.

Authentication is via the ``X-API-Key`` header. Every method raises
:class:`OryxApiError` (or :class:`AuthError`) with the API's machine-readable
error codes on failure, so the publishing engine can decide whether a retry is
worthwhile.
"""

from __future__ import annotations

from typing import Any

import requests

from app.core.config import OryxConfig, get_config
from app.core.exceptions import AuthError, OryxApiError, UploadError
from app.core.logging import get_logger

logger = get_logger(__name__)


class PropertyOryxClient:
    """Low-level HTTP client for the Property Oryx Agents API."""

    def __init__(self, api_key: str, config: OryxConfig | None = None) -> None:
        self._config = config or get_config().oryx
        self._base = self._config.api_base_url.rstrip("/")
        self._timeout = self._config.request_timeout_s
        self._session = requests.Session()
        self._session.headers.update(
            {
                "X-API-Key": api_key,
                "Accept": "application/json",
                "Content-Type": "application/json",
            }
        )

    # ------------------------------------------------------------------ core

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        """Perform a request and translate errors into typed exceptions."""
        url = f"{self._base}{path}"
        try:
            response = self._session.request(method, url, timeout=self._timeout, **kwargs)
        except requests.RequestException as exc:
            raise OryxApiError(f"Network error calling {method} {path}: {exc}", endpoint=path) from exc

        if response.ok:
            if response.status_code == 204 or not response.content:
                return None
            try:
                return response.json()
            except ValueError:
                return None

        codes = self._extract_codes(response)
        message = f"{method} {path} failed ({response.status_code}): {', '.join(codes) or response.text[:200]}"
        if response.status_code in (401, 403):
            raise AuthError(message, status_code=response.status_code, codes=codes, endpoint=path)
        raise OryxApiError(message, status_code=response.status_code, codes=codes, endpoint=path)

    @staticmethod
    def _extract_codes(response: requests.Response) -> list[str]:
        """Pull the ApiError codes out of an error body when present."""
        try:
            body = response.json()
        except ValueError:
            return []
        if isinstance(body, list):
            return [item.get("code", "") for item in body if isinstance(item, dict)]
        return []

    # ------------------------------------------------------------- system

    def status(self) -> Any:
        """GET /status - API and database health (no auth required)."""
        return self._request("GET", "/status")

    def session(self) -> Any:
        """GET /session - current portal session, or null."""
        return self._request("GET", "/session")

    def account(self) -> dict[str, Any]:
        """GET /account - authenticated account details (verifies the API key)."""
        return self._request("GET", "/account")

    def company(self) -> dict[str, Any]:
        """GET /company - company details."""
        return self._request("GET", "/company")

    def reference_data(self) -> dict[str, Any]:
        """GET /api-reference-data - current amenities, locations, listing options."""
        return self._request("GET", "/api-reference-data")

    def list_agents(self) -> dict[str, Any]:
        """GET /agent - company agents."""
        return self._request("GET", "/agent")

    # ------------------------------------------------------------- uploads

    def request_upload(self, image_hash: str, content_type: str) -> str:
        """POST /request-upload - obtain a signed URL to PUT image bytes to."""
        body = self._request(
            "POST", "/request-upload", json={"hash": image_hash, "contentType": content_type}
        )
        url = (body or {}).get("url")
        if not url:
            raise UploadError("Property Oryx did not return a signed upload URL")
        return url

    def upload_bytes(self, signed_url: str, data: bytes, content_type: str) -> None:
        """PUT raw image bytes to the pre-signed URL (no API key on this call)."""
        try:
            response = requests.put(
                signed_url, data=data, headers={"Content-Type": content_type}, timeout=self._timeout
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise UploadError(f"Failed to upload image bytes: {exc}") from exc

    def process_image(self, image_hash: str, image_type: str, watermark: bool) -> str:
        """POST /process-image - process an uploaded image; returns the final hash."""
        body = self._request(
            "POST",
            "/process-image",
            json={"hash": image_hash, "imageType": image_type, "shouldWatermark": watermark},
        )
        processed = (body or {}).get("hash")
        if not processed:
            raise UploadError("Property Oryx did not return a processed-image hash")
        return processed

    # ------------------------------------------------------------- listings

    def create_rental(self, payload: dict[str, Any]) -> Any:
        """POST /residential-rental-listing."""
        return self._request("POST", "/residential-rental-listing", json=payload)

    def create_sale(self, payload: dict[str, Any]) -> Any:
        """POST /residential-sales-listing."""
        return self._request("POST", "/residential-sales-listing", json=payload)

    def update_rental(self, listing_id: int, payload: dict[str, Any]) -> Any:
        """POST /residential-rental-listing/{id}."""
        return self._request("POST", f"/residential-rental-listing/{listing_id}", json=payload)

    def update_sale(self, listing_id: int, payload: dict[str, Any]) -> Any:
        """POST /residential-sales-listing/{id}."""
        return self._request("POST", f"/residential-sales-listing/{listing_id}", json=payload)

    def delete_rental(self, listing_id: int) -> Any:
        """DELETE /residential-rental-listing/{id}."""
        return self._request("DELETE", f"/residential-rental-listing/{listing_id}")

    def delete_sale(self, listing_id: int) -> Any:
        """DELETE /residential-sales-listing/{id}."""
        return self._request("DELETE", f"/residential-sales-listing/{listing_id}")

    def get_rental(self, listing_id: int) -> dict[str, Any]:
        """GET /residential-rental-listing/{id}."""
        return self._request("GET", f"/residential-rental-listing/{listing_id}")

    def get_sale(self, listing_id: int) -> dict[str, Any]:
        """GET /residential-sales-listing/{id}."""
        return self._request("GET", f"/residential-sales-listing/{listing_id}")

    def dashboard_search(self, **params: Any) -> dict[str, Any]:
        """GET /dashboard-search - find current listings (used to resolve new IDs)."""
        params.setdefault("page", 1)
        clean = {k: v for k, v in params.items() if v is not None}
        return self._request("GET", "/dashboard-search", params=clean)

    def dashboard_counts(self) -> dict[str, Any]:
        """GET /dashboard-counts - total and sponsored listing counts."""
        return self._request("GET", "/dashboard-counts")

    def stats_overview(self) -> dict[str, Any]:
        """GET /stats/overview - impressions/previews/views/leads today and 7d."""
        return self._request("GET", "/stats/overview")
