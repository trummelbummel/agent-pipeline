from __future__ import annotations

import logging
import math
import re
from pathlib import Path
from typing import Any

import numpy as np
from docling.document_converter import DocumentConverter
from pydantic import BaseModel

from compliance.models.claim import DocumentData
from compliance.preprocessing.preprocessing import FormatConverter, Preprocessor
from compliance.preprocessing.reader import Reader

logger = logging.getLogger(__name__)

_MISSING = np.nan
_RASTER_SUFFIXES = frozenset({"webp", "jpg", "jpeg", "png"})
_WHITESPACE = re.compile(r"\s+")
_KV_LINE = re.compile(r"^([^:\n]+):\s*(.+)$")

_SIGNATURE_PATTERNS = re.compile(
    r"(?:firma|signature|sello|stamp|signé|signatur|suscrit[oa]|soussigné|"
    r"je\s+soussigné|firmado|signed\s+by|dr\.\s*\w+|docteur\s+\w+|"
    r"médico\s+tratante|praticien)",
    re.IGNORECASE,
)

_TIMESTAMP_PATTERN = re.compile(
    r"\b("
    r"\d{1,2}[-/\.]\d{1,2}[-/\.]\d{2,4}"      # DD/MM/YYYY or similar
    r"|\d{4}[-/\.]\d{1,2}[-/\.]\d{1,2}"        # YYYY-MM-DD
    r"|\d{1,2}\s+(?:de\s+)?(?:enero|febrero|marzo|abril|mayo|junio|julio|agosto|"
    r"septiembre|octubre|noviembre|diciembre|"
    r"janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre|"
    r"january|february|march|april|may|june|july|august|september|october|november|december|"
    r"Januar|Februar|März|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember)"
    r"(?:\s+(?:de\s+|del?\s+)?\d{2,4})?"       # optional year after month name
    r")\b",
    re.IGNORECASE,
)

# Normalized label → DocumentData core field or fields-dict key
_PERSON_KEYS = frozenset({"person", "name", "patient", "patient name", "claimant", "nombre"})
_DATE_KEYS = frozenset({"date", "fecha", "admission date", "visit date", "document date"})


class DocumentPreprocessor(Preprocessor):
    """Clean Docling text and structure optional field candidates."""

    def preprocess(self, raw: Any) -> dict[str, Any]:
        """Normalize Docling output into DocumentData construction inputs.

        :param raw: Dict with ``text`` and ``confidence`` from DocumentReader._load.
        :return: Dict with cleaned text, confidence, person, date, has_signature, timestamps, fields.
        :raises TypeError: If raw is not a mapping.
        """
        if not isinstance(raw, dict):
            msg = f"Document raw must be a dict, got {type(raw).__name__}"
            raise TypeError(msg)

        text = str(raw.get("text", "") or "")
        cleaned = self._clean_text(text)
        person, date, fields = self._extract_candidates(cleaned)
        has_signature = self._detect_signature(cleaned)
        timestamps = self._extract_timestamps(cleaned)
        confidence = raw.get("confidence", _MISSING)
        return {
            "raw_text": cleaned if cleaned else _MISSING,
            "confidence": confidence,
            "person": person,
            "date": date,
            "has_signature": has_signature,
            "timestamps": timestamps,
            "fields": fields,
        }

    @staticmethod
    def _clean_text(text: str) -> str:
        """Collapse excess whitespace while preserving line breaks for KV parsing.

        :param text: Raw Docling markdown/text export.
        :return: Cleaned text.
        """
        lines = [_WHITESPACE.sub(" ", line).strip() for line in text.splitlines()]
        return "\n".join(line for line in lines if line)

    @staticmethod
    def _extract_candidates(text: str) -> tuple[Any, Any, dict[str, Any]]:
        """Pull person/date and other key/value candidates from cleaned text.

        :param text: Cleaned document text.
        :return: (person, date, fields) with np.nan when person/date absent.
        """
        person: Any = _MISSING
        date: Any = _MISSING
        fields: dict[str, Any] = {}

        for line in text.splitlines():
            match = _KV_LINE.match(line.strip().strip("*").strip())
            if not match:
                continue
            key = _WHITESPACE.sub(" ", match.group(1).strip().strip("*")).lower()
            value = match.group(2).strip().strip("*").strip()
            if not value:
                continue
            if key in _PERSON_KEYS and isinstance(person, float) and math.isnan(person):
                person = value
            elif key in _DATE_KEYS and isinstance(date, float) and math.isnan(date):
                date = value
            else:
                fields[key] = value

        return person, date, fields

    @staticmethod
    def _detect_signature(text: str) -> bool:
        """Check whether text contains signature-related indicators.

        :param text: Cleaned document text.
        :return: True when a signature pattern is found.
        """
        return bool(_SIGNATURE_PATTERNS.search(text))

    @staticmethod
    def _extract_timestamps(text: str) -> list[str]:
        """Extract all date/timestamp occurrences from text.

        :param text: Cleaned document text.
        :return: De-duplicated timestamps in order of first appearance.
        """
        seen: set[str] = set()
        timestamps: list[str] = []
        for match in _TIMESTAMP_PATTERN.finditer(text):
            value = match.group(1).strip()
            if value not in seen:
                seen.add(value)
                timestamps.append(value)
        return timestamps


class DocumentReader(Reader):
    """Read document images/PDFs via FormatConverter → PNG then Docling."""

    def __init__(
        self,
        document_formats: list[str],
        confidence_threshold: float,
        format_converter: FormatConverter,
        preprocessor: Preprocessor | None = None,
        document_converter: DocumentConverter | None = None,
    ) -> None:
        """Create a Docling-backed document reader.

        :param document_formats: Allowed file extensions (no dots) from config.
        :param confidence_threshold: Below this score, set human_in_the_loop.
        :param format_converter: Converts raster formats to PNG before Docling.
        :param preprocessor: Optional override; defaults to DocumentPreprocessor.
        :param document_converter: Optional Docling converter (injectable for tests).
        """
        super().__init__(preprocessor or DocumentPreprocessor())
        self.document_formats = [fmt.lower().lstrip(".") for fmt in document_formats]
        self.confidence_threshold = confidence_threshold
        self.format_converter = format_converter
        self.document_converter = document_converter or DocumentConverter()

    def _load(self, path: Path) -> dict[str, Any]:
        """Convert to PNG when needed, then run Docling extraction.

        PDF paths skip FormatConverter (Pillow cannot convert) and go to Docling
        directly. Raster formats always call ``format_converter.to_png`` first.

        :param path: Source document path.
        :return: Dict with extracted ``text`` and aggregate ``confidence``.
        :raises ValueError: If the file suffix is not in ``document_formats``.
        """
        suffix = path.suffix.lower().lstrip(".")
        if suffix not in self.document_formats:
            msg = f"Unsupported document format: .{suffix}"
            raise ValueError(msg)

        docling_path = self._path_for_docling(path, suffix)
        result = self.document_converter.convert(docling_path)
        text = result.document.export_to_markdown()
        confidence = self._aggregate_confidence(result.confidence)

        if (
            isinstance(confidence, float)
            and not math.isnan(confidence)
            and confidence < self.confidence_threshold
        ):
            logger.warning(
                "Low Docling confidence %.3f (threshold %.3f) for %s",
                confidence,
                self.confidence_threshold,
                path.name,
            )

        return {"text": text, "confidence": confidence}

    def _path_for_docling(self, path: Path, suffix: str) -> Path:
        """Resolve the path Docling should read (PNG-first for rasters).

        :param path: Original source path.
        :param suffix: Lowercase extension without dot.
        :return: Path passed to DocumentConverter.
        """
        if suffix == "pdf":
            logger.info("Passing PDF through to Docling without FormatConverter: %s", path.name)
            return path

        if suffix in _RASTER_SUFFIXES or suffix in self.format_converter.source_formats:
            return self.format_converter.to_png(path)

        # Non-raster, non-PDF format listed in config — attempt conversion
        return self.format_converter.to_png(path)

    @staticmethod
    def _aggregate_confidence(report: Any) -> float:
        """Combine Docling confidence scores into a single float.

        Uses the minimum of available layout/ocr/parse scores so low OCR
        quality surfaces as human_in_the_loop.

        :param report: Docling ConfidenceReport instance.
        :return: Aggregate confidence, or np.nan when no scores are present.
        """
        scores: list[float] = []
        for attr in ("layout_score", "ocr_score", "parse_score"):
            value = getattr(report, attr, None)
            if isinstance(value, (int, float)) and not math.isnan(float(value)):
                scores.append(float(value))
        if not scores:
            return float(_MISSING)
        return min(scores)

    def _to_model(self, processed: Any) -> BaseModel:
        """Build DocumentData with human_in_the_loop from confidence threshold.

        :param processed: Output of DocumentPreprocessor.preprocess.
        :return: DocumentData instance.
        """
        confidence = processed.get("confidence", _MISSING)
        hitl = False
        if isinstance(confidence, (int, float)) and not math.isnan(float(confidence)):
            hitl = float(confidence) < self.confidence_threshold

        return DocumentData.model_validate(
            {
                "person": processed.get("person", _MISSING),
                "date": processed.get("date", _MISSING),
                "raw_text": processed.get("raw_text", _MISSING),
                "confidence": confidence,
                "human_in_the_loop": hitl,
                "has_signature": processed.get("has_signature", False),
                "timestamps": processed.get("timestamps", []),
                "fields": processed.get("fields", {}),
            }
        )
