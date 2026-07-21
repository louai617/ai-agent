"""Property Oryx platform - official Agents API implementation.

Publishes residential rental and sales listings via the Property Oryx Agents
API. Rent vs sale is decided from the property (``Rent`` -> rental,
``Sale Price`` -> sales). Reference-data values (type, furnishing, location,
amenities, availability) are resolved to the API's IDs before submission.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

from app.core.config import AppConfig
from app.core.exceptions import OryxApiError, PublishError, ValidationError
from app.core.logging import get_logger
from app.models.schemas import PropertyData, PublishResult
from app.platforms.base import BasePlatform
from app.platforms.propertyoryx.client import PropertyOryxClient
from app.platforms.propertyoryx.images import ImageUploader
from app.platforms.propertyoryx.reference import ReferenceDataService
from app.platforms.registry import register_platform

logger = get_logger(__name__)


@register_platform
class PropertyOryxPlatform(BasePlatform):
    """Creates and manages Property Oryx listings through the REST API."""

    name = "propertyoryx"
    display_name = "Property Oryx"

    def __init__(
        self,
        credential: str,
        config: AppConfig | None = None,
        client: PropertyOryxClient | None = None,
        reference: ReferenceDataService | None = None,
    ) -> None:
        super().__init__(credential, config)
        self._oryx_cfg = self.config.oryx
        self.client = client or PropertyOryxClient(credential, self._oryx_cfg)
        self.reference = reference or ReferenceDataService(self.client, self._oryx_cfg)
        self._uploader = ImageUploader(self.client, watermark=self._oryx_cfg.watermark_images)
        self._agents_cache: dict[str, int] | None = None

    # ------------------------------------------------------------------ auth

    def login(self) -> None:
        """Verify the API key by fetching the account (raises AuthError if invalid)."""
        account = self.client.account()
        logger.info("Property Oryx: authenticated as %s", account.get("email", "?"))

    def is_authenticated(self) -> bool:
        try:
            self.client.account()
            return True
        except OryxApiError:
            return False

    def logout(self) -> None:
        """Stateless API - nothing to release."""
        return None

    # ------------------------------------------------------------- publish

    def publish(self, data: PropertyData, image_paths: list[str]) -> PublishResult:
        """Upload images, build the payload, create the listing, resolve its ID."""
        started = time.monotonic()
        category = data.listing_category()
        image_hashes = self._uploader.upload_all(image_paths)
        payload = self._build_payload(data, image_hashes, category)

        try:
            if category == "rent":
                self.client.create_rental(payload)
            else:
                self.client.create_sale(payload)
        except OryxApiError as exc:
            raise PublishError(f"Property Oryx create listing failed: {exc}") from exc

        listing_id = self._find_listing_id(data.property_ref, category)
        listing_url = ""
        if listing_id is not None:
            listing_url = self._oryx_cfg.public_listing_url_template.format(id=listing_id)
        else:
            logger.warning("Listing for %s created but its ID could not be resolved", data.property_ref)

        return PublishResult(
            success=True,
            listing_id=str(listing_id or ""),
            listing_url=listing_url,
            duration_seconds=time.monotonic() - started,
            published_at=datetime.now(UTC),
        )

    def update(self, external_id: str, data: PropertyData, image_paths: list[str]) -> PublishResult:
        """Update an existing listing by ID."""
        started = time.monotonic()
        if not external_id.isdigit():
            raise PublishError(f"Property Oryx update requires a numeric listing ID, got {external_id!r}")
        listing_id = int(external_id)
        category = data.listing_category()
        image_hashes = self._uploader.upload_all(image_paths)
        payload = self._build_payload(data, image_hashes, category)
        try:
            if category == "rent":
                self.client.update_rental(listing_id, payload)
            else:
                self.client.update_sale(listing_id, payload)
        except OryxApiError as exc:
            raise PublishError(f"Property Oryx update failed: {exc}") from exc
        listing_url = self._oryx_cfg.public_listing_url_template.format(id=listing_id)
        return PublishResult(
            success=True,
            listing_id=external_id,
            listing_url=listing_url,
            duration_seconds=time.monotonic() - started,
            published_at=datetime.now(UTC),
        )

    def delete(self, external_id: str, category: str) -> bool:
        """Remove a listing by ID."""
        if not external_id.isdigit():
            logger.error("Property Oryx delete needs a numeric ID, got %r", external_id)
            return False
        listing_id = int(external_id)
        try:
            if category == "rent":
                self.client.delete_rental(listing_id)
            else:
                self.client.delete_sale(listing_id)
            return True
        except OryxApiError as exc:
            logger.error("Property Oryx delete failed for %s: %s", external_id, exc)
            return False

    # ------------------------------------------------------------- helpers

    def _build_payload(self, data: PropertyData, image_hashes: list[str], category: str) -> dict[str, Any]:
        """Assemble a Create*ListingForm payload with all required keys."""
        price = data.rent if category == "rent" else data.sale_price
        if price is None:
            raise ValidationError("Listing has no price")

        payload: dict[str, Any] = {
            "type": self.reference.resolve_type(data.property_type),
            "title": data.title,
            "titleAr": data.title_ar or None,
            "description": data.description,
            "descriptionAr": data.description_ar or None,
            "bedrooms": max(0, data.bedrooms if data.bedrooms is not None else 0),
            "bathrooms": max(1, data.bathrooms if data.bathrooms is not None else 1),
            "price": int(round(price)),
            "reference": data.property_ref or None,
            "area": data.area_sqm if (data.area_sqm and data.area_sqm >= 5) else None,
            "furnishing": self.reference.resolve_furnishing(data.furnished),
            "amenities": self.reference.resolve_amenities(data.amenities),
            "commission": self._oryx_cfg.default_commission,
            "flags": [],
            "images": image_hashes,
            "location": self.reference.resolve_location(data.district, data.location),
            "agentId": self._resolve_agent(data.agent),
        }
        if category == "rent":
            payload["deposit"] = self._oryx_cfg.default_deposit
        else:
            payload["availability"] = self.reference.resolve_availability(
                data.availability, self._oryx_cfg.default_availability
            )
        return payload

    def _resolve_agent(self, agent_name: str) -> int | None:
        """Map an agent name to its ID via GET /agent, falling back to config default."""
        if not agent_name:
            return self._oryx_cfg.default_agent_id
        if self._agents_cache is None:
            try:
                agents = self.client.list_agents().get("agents", [])
                self._agents_cache = {a["name"].strip().lower(): int(a["id"]) for a in agents}
            except OryxApiError:
                self._agents_cache = {}
        return self._agents_cache.get(agent_name.strip().lower(), self._oryx_cfg.default_agent_id)

    def _find_listing_id(self, reference: str, category: str) -> int | None:
        """Resolve the newly-created listing ID by searching for its reference."""
        if not reference:
            return None
        try:
            response = self.client.dashboard_search(category=category, reference=reference, page=1)
        except OryxApiError as exc:
            logger.warning("Could not search for new listing %s: %s", reference, exc)
            return None
        matches = [
            listing
            for listing in response.get("listings", [])
            if (listing.get("reference") or "").strip() == reference.strip()
        ]
        if not matches:
            return None
        newest = max(matches, key=lambda item: item.get("created", 0))
        return int(newest["id"])
