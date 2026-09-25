from __future__ import annotations

import logging
import math
import re
from pathlib import Path
from typing import Any

from docling.document_converter import DocumentConverter
from pydantic import BaseModel

from compliance.branch_log import log_branch_decision
from compliance.models.claim import _MISSING, DocumentData
from compliance.preprocessing.preprocessing import FormatConverter, Preprocessor
from compliance.preprocessing.reader import Reader
from compliance.tools.benford import BenfordLawChecker, BenfordResult

logger = logging.getLogger(__name__)

_FRAUD_DENY = "DENY"
_FRAUD_REASON = "fraud"
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
        benford_checker: BenfordLawChecker | None = None,
    ) -> None:
        """Create a Docling-backed document reader.

        :param document_formats: Allowed file extensions (no dots) from config.
        :param confidence_threshold: Below this OCR confidence, set human_in_the_loop.
        :param format_converter: Converts raster formats to PNG before Docling.
        :param preprocessor: Optional override; defaults to DocumentPreprocessor.
        :param document_converter: Optional Docling converter (injectable for tests).
        :param benford_checker: Optional forensics check run on PNG before Docling;
            when conformity fails, Docling is skipped and DENY/fraud is returned.
        """
        super().__init__(preprocessor or DocumentPreprocessor())
        self.document_formats = [fmt.lower().lstrip(".") for fmt in document_formats]
        self.confidence_threshold = confidence_threshold
        self.format_converter = format_converter
        self.document_converter = document_converter or DocumentConverter()
        self.benford_checker = benford_checker

    def read(self, path: Path) -> BaseModel:
        """Convert to PNG, optionally Benford-check, then Docling — or early DENY.

        Raster images are converted to PNG first. When a Benford checker is wired,
        non-conforming images return ``DocumentData`` with decision DENY / reason
        fraud and never call Docling. PDFs skip Benford (no Pillow conversion).

        :param path: Filesystem path to the source document.
        :return: DocumentData from Docling, or an early fraud DENY payload.
        :raises ValueError: If the file suffix is not in ``document_formats``.
        """
        suffix = path.suffix.lower().lstrip(".")
        if suffix not in self.document_formats:
            msg = f"Unsupported document format: .{suffix}"
            raise ValueError(msg)

        resolved = self._path_for_docling(path, suffix)
        fraud_deny = self._fraud_deny_from_benford(resolved, suffix)
        if fraud_deny is not None:
            return fraud_deny

        processed = self.preprocessor.preprocess(self._docling_payload(resolved))
        return self._to_model(processed)

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

        return self._docling_payload(self._path_for_docling(path, suffix))

    def _fraud_deny_from_benford(self, image_path: Path, suffix: str) -> DocumentData | None:
        """Return DENY/fraud DocumentData when Benford conformity fails.

        :param image_path: PNG path (or PDF — PDFs skip this check).
        :param suffix: Lowercase extension without dot.
        :return: Early-deny DocumentData, or None to continue to Docling.
        """
        if self.benford_checker is None:
            log_branch_decision(
                logger,
                branch="benford",
                outcome="SKIP",
                reason="disabled_or_unset",
                file=image_path.name,
            )
            return None

        if suffix == "pdf":
            log_branch_decision(
                logger,
                branch="benford",
                outcome="SKIP",
                reason="pdf_passthrough",
                file=image_path.name,
            )
            return None

        benford = self.benford_checker.check(image_path)
        if benford.conformity:
            log_branch_decision(
                logger,
                branch="benford",
                outcome="PASS",
                reason="conformity",
                file=image_path.name,
                chi_squared=f"{benford.chi_squared:.4f}",
                coefficients=benford.total_coefficients,
            )
            return None

        log_branch_decision(
            logger,
            branch="benford",
            outcome=_FRAUD_DENY,
            reason=_FRAUD_REASON,
            level=logging.WARNING,
            file=image_path.name,
            chi_squared=f"{benford.chi_squared:.4f}",
            next_step="skip_docling",
        )
        return self._fraud_deny_document(benford)

    @staticmethod
    def _fraud_deny_document(benford: BenfordResult) -> DocumentData:
        """Build the early-return DocumentData for a Benford violation.

        :param benford: Non-conforming BenfordResult.
        :return: DocumentData with decision DENY and reason fraud.
        """
        return DocumentData.model_validate(
            {
                "decision": _FRAUD_DENY,
                "reason": _FRAUD_REASON,
                "raw_text": _MISSING,
                "confidence": _MISSING,
                "human_in_the_loop": False,
                "fields": {
                    "decision": _FRAUD_DENY,
                    "reason": _FRAUD_REASON,
                    "benford_chi_squared": benford.chi_squared,
                    "benford_conformity": False,
                },
            }
        )

    def _docling_payload(self, docling_path: Path) -> dict[str, Any]:
        """Run Docling on an already-resolved path and return text + confidence.

        :param docling_path: PNG or PDF path ready for DocumentConverter.
        :return: Dict with extracted ``text`` and aggregate ``confidence``.
        """
        log_branch_decision(
            logger,
            branch="docling",
            outcome="RUN",
            reason="benford_cleared_or_skipped",
            file=docling_path.name,
        )
        result = self.document_converter.convert(docling_path)
        text = result.document.export_to_markdown()
        confidence = self._aggregate_confidence(result.confidence)
        return {"text": text, "confidence": confidence}

    def _path_for_docling(self, path: Path, suffix: str) -> Path:
        """Resolve the path Docling should read (PNG-first for rasters).

        :param path: Original source path.
        :param suffix: Lowercase extension without dot.
        :return: Path passed to DocumentConverter.
        """
        if suffix == "pdf":
            log_branch_decision(
                logger,
                branch="format_convert",
                outcome="PASSTHROUGH",
                reason="pdf",
                file=path.name,
            )
            return path

        if suffix == "png":
            log_branch_decision(
                logger,
                branch="format_convert",
                outcome="PASSTHROUGH",
                reason="already_png",
                file=path.name,
            )
            return self.format_converter.to_png(path)

        converted = self.format_converter.to_png(path)
        log_branch_decision(
            logger,
            branch="format_convert",
            outcome="CONVERT_PNG",
            reason=f"source_{suffix}",
            file=path.name,
            png=converted.name,
        )
        return converted

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
            if hitl:
                log_branch_decision(
                    logger,
                    branch="ocr_confidence",
                    outcome="HITL",
                    reason="below_threshold",
                    level=logging.WARNING,
                    confidence=f"{float(confidence):.3f}",
                    threshold=f"{self.confidence_threshold:.3f}",
                )
            else:
                log_branch_decision(
                    logger,
                    branch="ocr_confidence",
                    outcome="ACCEPT",
                    reason="above_threshold",
                    confidence=f"{float(confidence):.3f}",
                    threshold=f"{self.confidence_threshold:.3f}",
                )
        else:
            log_branch_decision(
                logger,
                branch="ocr_confidence",
                outcome="ACCEPT",
                reason="confidence_unavailable",
            )

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
