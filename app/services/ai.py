"""AI content generation via the Google Gemini API.

Generates SEO titles and professional descriptions strictly from the facts in
the property row - the prompt forbids invented details and emojis. When AI is
disabled (or the API key is missing) a deterministic template fallback is used
so publishing never blocks on the AI layer.
"""

from __future__ import annotations

import re

from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types

from app.core.config import AIConfig, get_config, get_secret
from app.core.exceptions import AIError
from app.core.logging import get_logger
from app.models.schemas import PropertyData

logger = get_logger(__name__)

_EMOJI_RE = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F000-\U0001F02F\U00002190-\U000021FF\U00002B00-\U00002BFF]+"
)


def _strip_emojis(text: str) -> str:
    return _EMOJI_RE.sub("", text).strip()


def _property_facts(data: PropertyData) -> str:
    """Serialise only the known facts for the prompt (no fabrication surface)."""
    facts = [
        f"Property type: {data.property_type}",
        f"Category: {data.category}",
        f"Location: {data.location}" + (f", {data.district}" if data.district else ""),
    ]
    if data.bedrooms is not None:
        facts.append(f"Bedrooms: {data.bedrooms}")
    if data.bathrooms is not None:
        facts.append(f"Bathrooms: {data.bathrooms}")
    if data.area_sqm is not None:
        facts.append(f"Area: {data.area_sqm:g} sqm")
    price = data.price_display()
    if price:
        facts.append(f"Price: {price}")
    if data.furnished:
        facts.append(f"Furnished: {data.furnished}")
    if data.bills_included:
        facts.append("Bills included in rent")
    if data.amenities:
        facts.append(f"Amenities: {', '.join(data.amenities)}")
    return "\n".join(facts)


class ContentGenerator:
    """Generates listing titles and descriptions using Gemini."""

    def __init__(self, config: AIConfig | None = None, client: genai.Client | None = None) -> None:
        self._config = config or get_config().ai
        self._client = client
        if self._client is None and self._config.enabled:
            api_key = get_secret("GEMINI_API_KEY")
            if api_key:
                self._client = genai.Client(api_key=api_key)
            else:
                logger.warning("GEMINI_API_KEY not set - falling back to template content")

    # ------------------------------------------------------------------ titles

    def generate_title(self, data: PropertyData) -> str:
        """Return an SEO title (max ``title_max_chars``, no emojis)."""
        if self._client is not None and self._config.enabled:
            try:
                title = self._complete(
                    system=self._config.title_prompt.format(max_chars=self._config.title_max_chars),
                    user=_property_facts(data),
                    max_tokens=60,
                )
                title = _strip_emojis(title.strip().strip('"'))
                if title:
                    return title[: self._config.title_max_chars]
            except (genai_errors.APIError, AIError) as exc:
                logger.error("AI title generation failed, using template: %s", exc)
        return self._template_title(data)

    def _template_title(self, data: PropertyData) -> str:
        """Deterministic fallback title built from facts."""
        parts: list[str] = []
        if data.bedrooms is not None:
            parts.append(f"{data.bedrooms} BR" if data.bedrooms else "Studio")
        if data.furnished:
            parts.append(data.furnished)
        parts.append(data.property_type or "Property")
        verb = "for Rent" if data.rent is not None else "for Sale"
        parts.append(verb)
        where = data.district or data.location
        if where:
            parts.append(f"in {where}")
        price = data.price_display()
        if price:
            parts.append(f"- {price}")
        return " ".join(parts)[: self._config.title_max_chars]

    # ------------------------------------------------------------ descriptions

    def generate_description(self, data: PropertyData) -> str:
        """Return a professional description highlighting the key facts."""
        if self._client is not None and self._config.enabled:
            try:
                text = self._complete(
                    system=self._config.description_prompt.format(language=self._config.language),
                    user=_property_facts(data),
                    max_tokens=self._config.max_tokens,
                )
                text = _strip_emojis(text.strip())
                if text:
                    return text
            except (genai_errors.APIError, AIError) as exc:
                logger.error("AI description generation failed, using template: %s", exc)
        return self._template_description(data)

    def _template_description(self, data: PropertyData) -> str:
        """Deterministic fallback description."""
        lines = [
            f"{data.property_type or 'Property'} available "
            f"{'for rent' if data.rent is not None else 'for sale'} in "
            f"{data.district or data.location}.",
            "",
        ]
        if data.bedrooms is not None:
            lines.append(f"- Bedrooms: {data.bedrooms if data.bedrooms else 'Studio'}")
        if data.bathrooms is not None:
            lines.append(f"- Bathrooms: {data.bathrooms}")
        if data.area_sqm is not None:
            lines.append(f"- Area: {data.area_sqm:g} sqm")
        if data.furnished:
            lines.append(f"- Furnishing: {data.furnished}")
        price = data.price_display()
        if price:
            lines.append(f"- Price: {price}" + (" (bills included)" if data.bills_included else ""))
        if data.amenities:
            lines.append(f"- Amenities: {', '.join(data.amenities)}")
        lines += ["", f"Contact {data.agent or 'our team'} at {data.phone or data.email} to arrange a viewing."]
        return "\n".join(lines)

    # ------------------------------------------------------------------- Gemini

    def _complete(self, system: str, user: str, max_tokens: int) -> str:
        """Single Gemini generate_content call."""
        if self._client is None:
            raise AIError("Gemini client is not configured")
        response = self._client.models.generate_content(
            model=self._config.model,
            contents=user,
            config=genai_types.GenerateContentConfig(
                system_instruction=system,
                temperature=self._config.temperature,
                max_output_tokens=max_tokens,
            ),
        )
        content = response.text
        if not content:
            raise AIError("Gemini returned empty content")
        return content

    # ------------------------------------------------------------------ arabic

    def _translate(self, text: str, kind: str) -> str:
        """Translate English listing copy to Arabic (returns '' on failure)."""
        if self._client is None or not self._config.enabled or not text:
            return ""
        try:
            translated = self._complete(
                system=(
                    f"Translate this real estate listing {kind} into professional Modern Standard "
                    "Arabic. Keep it accurate to the source; do not add facts. No emojis. "
                    "Return only the Arabic text."
                ),
                user=text,
                max_tokens=self._config.max_tokens,
            )
            return _strip_emojis(translated.strip())
        except genai_errors.APIError as exc:
            logger.error("Arabic %s translation failed: %s", kind, exc)
            return ""

    # ------------------------------------------------------------- enforcement

    def _enforce_min_lengths(self, data: PropertyData) -> None:
        """Property Oryx rejects short copy; pad title/description to the minimums."""
        if len(data.title) < self._config.title_min_chars:
            data.title = self._template_title(data)
        if len(data.title) < self._config.title_min_chars:
            data.title = f"{data.title} - {data.location or data.property_ref}".strip(" -")
        if len(data.description) < self._config.description_min_chars:
            data.description = self._template_description(data)

    def ensure_content(self, data: PropertyData) -> PropertyData:
        """Fill title/description (and Arabic, if enabled) when they are empty."""
        if not data.title:
            data.title = self.generate_title(data)
            logger.info("Generated title for %s: %s", data.property_ref, data.title)
        if not data.description:
            data.description = self.generate_description(data)
            logger.info("Generated description for %s (%d chars)", data.property_ref, len(data.description))
        self._enforce_min_lengths(data)

        if self._config.generate_arabic:
            if not data.title_ar:
                data.title_ar = self._translate(data.title, "title")
            if not data.description_ar:
                data.description_ar = self._translate(data.description, "description")
        return data
