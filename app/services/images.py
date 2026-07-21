"""Image processing pipeline.

For each property image folder this service:
- filters to supported formats (jpg, jpeg, png, webp)
- removes corrupted files from the batch
- deduplicates by SHA-256 of pixel data
- auto-rotates using EXIF orientation
- resizes to the configured bounding box, preserving aspect ratio
- compresses to JPEG under the configured size limit
- renames deterministically: ``<property_ref>_01.jpg`` ...

Processed files are written to ``data/processed_images/<property_ref>/`` so
originals are never modified.
"""

from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.config import DATA_DIR, ImageConfig, get_config
from app.core.exceptions import ImageError
from app.core.logging import get_logger

logger = get_logger(__name__)

PROCESSED_DIR = DATA_DIR / "processed_images"


@dataclass
class ProcessedImage:
    """Result for one image."""

    original_path: str
    processed_path: str
    sha256: str
    width: int
    height: int
    size_bytes: int
    status: str = "Ready"


@dataclass
class ImageBatchResult:
    """Result for a property's whole folder."""

    ready: list[ProcessedImage] = field(default_factory=list)
    duplicates: list[str] = field(default_factory=list)
    corrupted: list[str] = field(default_factory=list)

    @property
    def paths(self) -> list[str]:
        return [img.processed_path for img in self.ready]


class ImageProcessor:
    """Processes a folder of listing images."""

    def __init__(self, config: ImageConfig | None = None) -> None:
        self._config = config or get_config().images

    def process_folder(self, folder: str | Path, property_ref: str) -> ImageBatchResult:
        """Process every supported image in ``folder``.

        Raises ``ImageError`` if the folder is missing or yields zero usable
        images (a listing without photos should not be published).
        """
        src = Path(folder)
        if not src.is_dir():
            raise ImageError(f"Images folder not found: {src}")

        out_dir = PROCESSED_DIR / property_ref
        if out_dir.exists():
            shutil.rmtree(out_dir)
        out_dir.mkdir(parents=True)

        result = ImageBatchResult()
        seen_hashes: set[str] = set()
        candidates = sorted(
            p for p in src.iterdir()
            if p.is_file() and p.suffix.lower() in self._config.allowed_extensions
        )

        index = 0
        for path in candidates:
            if len(result.ready) >= self._config.max_images_per_listing:
                logger.info("Image limit (%d) reached for %s", self._config.max_images_per_listing, property_ref)
                break
            try:
                with Image.open(path) as img:
                    img.verify()  # cheap corruption check
                with Image.open(path) as img:
                    digest = self._pixel_hash(img)
                    if digest in seen_hashes:
                        result.duplicates.append(str(path))
                        logger.info("Duplicate image skipped: %s", path.name)
                        continue
                    seen_hashes.add(digest)
                    index += 1
                    processed = self._process_one(img, out_dir, property_ref, index, str(path), digest)
                    result.ready.append(processed)
            except (UnidentifiedImageError, OSError) as exc:
                result.corrupted.append(str(path))
                logger.warning("Corrupted image skipped: %s (%s)", path.name, exc)

        if not result.ready:
            raise ImageError(f"No usable images found in {src}")
        logger.info(
            "Processed %d images for %s (%d duplicates, %d corrupted)",
            len(result.ready), property_ref, len(result.duplicates), len(result.corrupted),
        )
        return result

    # ------------------------------------------------------------------ internals

    @staticmethod
    def _pixel_hash(img: Image.Image) -> str:
        """Hash of normalised pixel data so re-encoded copies still match."""
        thumb = img.convert("RGB").resize((256, 256))
        return hashlib.sha256(thumb.tobytes()).hexdigest()

    def _process_one(
        self,
        img: Image.Image,
        out_dir: Path,
        property_ref: str,
        index: int,
        original_path: str,
        digest: str,
    ) -> ProcessedImage:
        """Rotate, resize, compress and save one image as JPEG."""
        img = ImageOps.exif_transpose(img)  # honour EXIF rotation
        img = img.convert("RGB")
        img.thumbnail((self._config.max_width, self._config.max_height), Image.LANCZOS)

        target = out_dir / f"{property_ref}_{index:02d}.jpg"
        quality = self._config.jpeg_quality
        max_bytes = int(self._config.max_file_size_mb * 1024 * 1024)
        while True:
            img.save(target, "JPEG", quality=quality, optimize=True, progressive=True)
            if target.stat().st_size <= max_bytes or quality <= 40:
                break
            quality -= 10  # step down until under the upload limit

        return ProcessedImage(
            original_path=original_path,
            processed_path=str(target),
            sha256=digest,
            width=img.width,
            height=img.height,
            size_bytes=target.stat().st_size,
        )
