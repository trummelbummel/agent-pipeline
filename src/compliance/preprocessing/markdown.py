from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from compliance.models.claim import _MISSING, BookingData
from compliance.preprocessing.preprocessing import Preprocessor
from compliance.preprocessing.reader import Reader

logger = logging.getLogger(__name__)

# Normalized alias → BookingData field name
_KEY_ALIASES: dict[str, str] = {
    "current date is": "current_date",
    "current date": "current_date",
    "name": "name",
    "nombre": "name",
    "claimant": "name",
    "patient name": "name",
    "booking ref": "booking_ref",
    "booking reference": "booking_ref",
    "referencia de reserva": "booking_ref",
    "price": "price",
    "precio": "price",
    "ticket price": "price",
    "ticket cost": "price",
    "operator": "operator",
    "operador": "operator",
    "airline": "operator",
    "flight": "service",
    "flight number": "service",
    "train": "service",
    "tren": "service",
    "event": "service",
    "hotel": "service",
    "hotel name": "service",
    "departure": "departure",
    "salida": "departure",
    "event date": "departure",
    "check-in": "departure",
    "check-in date": "departure",
    "check in": "departure",
    "check in date": "departure",
    "date": "departure",
    "from": "origin",
    "desde": "origin",
    "origin": "origin",
    "to": "destination",
    "hacia": "destination",
    "destination": "destination",
    "location": "destination",
    "seat": "seat",
    "asiento": "seat",
    "fare type": "fare_type",
    "tipo de tarifa": "fare_type",
    "class": "fare_type",
    "ticket type": "fare_type",
    "room type": "fare_type",
    "booked on": "booked_on",
    "reservado el": "booked_on",
    "registered on": "booked_on",
    "date of booking": "booked_on",
    "payment date": "booked_on",
    "check-out": "check_out",
    "check-out date": "check_out",
    "check out": "check_out",
    "check out date": "check_out",
    "guests": "guests",
    "venue": "venue",
    "bib number": "bib_number",
    "booking platform": "booking_platform",
    "cancellation": "cancellation",
}

_BOLD_KV = re.compile(r"\*\*(.+?)\*\*\s*:\s*(.+)")
_BOLD_INLINE_KV = re.compile(r"\*\*(.+?):\s*(.+?)\*\*")
_PLAIN_KV = re.compile(r"^([^:\n*]+):\s*(.+)$")
_WHITESPACE = re.compile(r"\s+")


def _normalize_key(raw: str) -> str:
    """Strip, lower-case, and collapse whitespace in a markdown key.

    :param raw: Raw key text possibly including bold markers or trailing colons.
    :return: Normalized key used for alias lookup.
    """
    key = raw.strip().strip("*").strip()
    key = key.rstrip(":").strip()
    key = _WHITESPACE.sub(" ", key).lower()
    return key


def _translate_key(normalized: str) -> str | None:
    """Map a normalized key to a BookingData field name.

    :param normalized: Output of ``_normalize_key``.
    :return: Canonical field name, or None when unknown.
    """
    return _KEY_ALIASES.get(normalized)


def _extract_kv_pairs(text: str) -> dict[str, str]:
    """Extract key/value pairs from markdown booking text.

    Supports ``**key**: value``, ``**key**:value``, ``**key: value**``
    (e.g. Current date is), and plain ``Key: value`` lines.

    :param text: Full markdown file contents.
    :return: Ordered mapping of raw keys to values (last wins on duplicates).
    """
    pairs: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue

        match = _BOLD_KV.match(stripped)
        if match:
            pairs[match.group(1).strip()] = match.group(2).strip()
            continue

        match = _BOLD_INLINE_KV.match(stripped)
        if match:
            pairs[match.group(1).strip()] = match.group(2).strip()
            continue

        match = _PLAIN_KV.match(stripped)
        if match:
            pairs[match.group(1).strip()] = match.group(2).strip()

    return pairs


class MarkdownPreprocessor(Preprocessor):
    """Extract, normalize, and translate markdown booking keys."""

    def preprocess(self, raw: Any) -> dict[str, str]:
        """Convert markdown text into canonical BookingData field values.

        Unknown keys are dropped after a warning log.

        :param raw: Markdown file text.
        :return: Dict keyed by BookingData field names.
        :raises TypeError: If raw is not a string.
        """
        if not isinstance(raw, str):
            msg = f"Markdown content must be str, got {type(raw).__name__}"
            raise TypeError(msg)

        translated: dict[str, str] = {}
        for raw_key, value in _extract_kv_pairs(raw).items():
            normalized = _normalize_key(raw_key)
            field = _translate_key(normalized)
            if field is None:
                logger.warning("Unknown markdown key dropped: %r (normalized=%r)", raw_key, normalized)
                continue
            translated[field] = value
        return translated


class MarkdownReader(Reader):
    """Read supporting/internal markdown into a BookingData model."""

    def __init__(self, preprocessor: Preprocessor | None = None) -> None:
        """Create a reader with a MarkdownPreprocessor by default.

        :param preprocessor: Optional override; defaults to MarkdownPreprocessor.
        """
        super().__init__(preprocessor or MarkdownPreprocessor())

    def _load(self, path: Path) -> Any:
        """Read markdown file text.

        :param path: Path to a ``.md`` booking file.
        :return: UTF-8 text contents.
        """
        return path.read_text(encoding="utf-8")

    def _to_model(self, processed: Any) -> BaseModel:
        """Build BookingData with np.nan for every absent field.

        :param processed: Dict of canonical field names to string values.
        :return: BookingData instance.
        """
        fields = dict.fromkeys(BookingData.model_fields, _MISSING)
        fields.update(processed)
        return BookingData.model_validate(fields)
