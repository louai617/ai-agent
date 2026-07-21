"""Upload locally-processed images to Property Oryx.

Flow per image (per the API):
1. sha256 the file bytes -> use as the client-side ``hash``.
2. POST /request-upload -> signed URL.
3. PUT the bytes to the signed URL.
4. POST /process-image -> final processed-image hash to reference in the listing.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from app.core.exceptions import UploadError
from app.core.logging import get_logger
from app.platforms.propertyoryx.client import PropertyOryxClient

logger = get_logger(__name__)

_CONTENT_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}


class ImageUploader:
    """Uploads processed image files and returns Property Oryx image hashes."""

    def __init__(self, client: PropertyOryxClient, watermark: bool = False) -> None:
        self._client = client
        self._watermark = watermark

    def upload(self, path: str | Path) -> str:
        """Upload one image; returns the processed-image hash to use in a listing."""
        file_path = Path(path)
        if not file_path.is_file():
            raise UploadError(f"Image not found: {file_path}")
        content_type = _CONTENT_TYPES.get(file_path.suffix.lower(), "image/jpeg")
        data = file_path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()

        signed_url = self._client.request_upload(digest, content_type)
        self._client.upload_bytes(signed_url, data, content_type)
        processed_hash = self._client.process_image(digest, "PropertyImage", self._watermark)
        logger.info("Uploaded image %s -> %s", file_path.name, processed_hash[:12])
        return processed_hash

    def upload_all(self, paths: list[str]) -> list[str]:
        """Upload every image, preserving order and de-duplicating hashes."""
        hashes: list[str] = []
        for path in paths:
            image_hash = self.upload(path)
            if image_hash not in hashes:
                hashes.append(image_hash)
        if not hashes:
            raise UploadError("No images were uploaded to Property Oryx")
        return hashes
