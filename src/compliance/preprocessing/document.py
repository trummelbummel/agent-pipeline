from __future__ import annotations

import logging
import math
import re
from pathlib import Path
from typing import Any

import ollama
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import (
    PictureClassificationLabel,
    PdfPipelineOptions,
)
from docling.document_converter import DocumentConverter, ImageFormatOption, PdfFormatOption
from pydantic import BaseModel

from compliance.branch_log import log_branch_decision
from compliance.config.settings import OcrRetryConfig
from compliance.llm.chat import ChatFn, response_content
from compliance.models.claim import _MISSING, DocumentData, DocumentMetaData
from compliance.preprocessing.extraction_failure import ExtractionFailure
from compliance.preprocessing.preprocessing import FormatConverter, Preprocessor
from compliance.preprocessing.reader import Reader
from compliance.tools.benford import BenfordLawChecker, BenfordResult

logger = logging.getLogger(__name__)

_FRAUD_DENY = "DENY"
_FRAUD_REASON = "fraud"
_WHITESPACE = re.compile(r"\s+")
_KV_LINE = re.compile(r"^([^:\n]+):\s*(.+)$")
_SIGNATURE_CLASS = PictureClassificationLabel.SIGNATURE.value
_IMAGE_RETRY_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".webp"})

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


def _document_converter_with_picture_classification() -> DocumentConverter:
    """Build a DocumentConverter with DocumentFigureClassifier enabled.

    Picture classification runs via Docling's ``DocumentPictureClassifier`` enrichment
    (``do_picture_classification``) so signatures are detected as figure classes, not
    inferred from OCR text.

    :return: Converter configured for IMAGE and PDF inputs.
    """
    pipeline_options = PdfPipelineOptions()
    pipeline_options.generate_picture_images = True
    pipeline_options.images_scale = 2
    pipeline_options.do_picture_classification = True
    return DocumentConverter(
        format_options={
            InputFormat.IMAGE: ImageFormatOption(pipeline_options=pipeline_options),
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options),
        }
    )


def _has_signature_from_pictures(document: Any) -> bool:
    """Return True when DocumentFigureClassifier labels any picture as signature.

    Uses the top prediction on each ``PictureItem`` (``meta.classification``).

    :param document: Docling ``DoclingDocument`` from a conversion result.
    :return: Whether any picture's top class is ``signature``.
    """
    for picture in getattr(document, "pictures", None) or []:
        meta = getattr(picture, "meta", None)
        classification = getattr(meta, "classification", None) if meta is not None else None
        predictions = getattr(classification, "predictions", None) if classification is not None else None
        if not predictions:
            continue
        top = predictions[0]
        if getattr(top, "class_name", None) == _SIGNATURE_CLASS:
            return True
    return False


class DocumentPreprocessor(Preprocessor):
    """Clean Docling text and structure optional field candidates."""

    def preprocess(self, raw: Any) -> dict[str, Any]:
        """Normalize Docling output into DocumentData construction inputs.

        :param raw: Dict with ``text``, ``confidence``, and ``has_signature`` from
            DocumentReader (signature comes from DocumentFigureClassifier).
        :return: Dict with cleaned text, confidence, person, date, has_signature, timestamps, fields.
        :raises TypeError: If raw is not a mapping.
        """
        if not isinstance(raw, dict):
            msg = f"Document raw must be a dict, got {type(raw).__name__}"
            raise TypeError(msg)

        text = str(raw.get("text", "") or "")
        cleaned = self._clean_text(text)
        person, date, fields = self._extract_candidates(cleaned)
        timestamps = self._extract_timestamps(cleaned)
        confidence = raw.get("confidence", _MISSING)
        return {
            "raw_text": cleaned if cleaned else _MISSING,
            "confidence": confidence,
            "person": person,
            "date": date,
            "has_signature": bool(raw.get("has_signature", False)),
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
        extraction_failure: ExtractionFailure | None = None,
        ocr_retry: OcrRetryConfig | None = None,
        retry_chat_fn: ChatFn | None = None,
    ) -> None:
        """Create a Docling-backed document reader.

        :param document_formats: Allowed file extensions (no dots) from config.
        :param confidence_threshold: Below this OCR confidence, set human_in_the_loop.
        :param format_converter: Converts raster formats to PNG before Docling.
        :param preprocessor: Optional override; defaults to DocumentPreprocessor.
        :param document_converter: Optional Docling converter (injectable for tests).
            Defaults to a converter with DocumentFigureClassifier picture classification.
        :param benford_checker: Optional forensics check run on PNG before Docling;
            when conformity fails, Docling is skipped and DENY/fraud is returned.
        :param extraction_failure: Detector for unusable OCR; defaults to ExtractionFailure().
        :param ocr_retry: Optional vision-model retry config after faulty Docling OCR.
        :param retry_chat_fn: Optional chat callable for vision retry; defaults to ollama.chat.
        """
        super().__init__(preprocessor or DocumentPreprocessor())
        self.document_formats = [fmt.lower().lstrip(".") for fmt in document_formats]
        self.confidence_threshold = confidence_threshold
        self.format_converter = format_converter
        self.document_converter = (
            document_converter or _document_converter_with_picture_classification()
        )
        self.benford_checker = benford_checker
        self.extraction_failure = extraction_failure or ExtractionFailure()
        self.ocr_retry = ocr_retry
        self._retry_chat: ChatFn = retry_chat_fn or ollama.chat

    def read(self, path: Path) -> BaseModel:
        """Convert to PNG, optionally Benford-check, then Docling — or early DENY.

        Raster images are converted to PNG first. When a Benford checker is wired,
        non-conforming images return ``DocumentData`` with decision DENY / reason
        fraud and never call Docling. PDFs skip Benford (no Pillow conversion).
        When Docling OCR is faulty and ``ocr_retry`` is enabled, retries once via
        a config-driven vision model on the resolved PNG.

        :param path: Filesystem path to the source document.
        :return: DocumentData from Docling (or vision retry), or an early fraud DENY.
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

        docling_payload = self._docling_payload(resolved)
        processed = self.preprocessor.preprocess(docling_payload)
        document = self._to_model(processed, source_file=path.name)
        return self._maybe_retry_ocr(
            document,
            resolved=resolved,
            prior_payload=docling_payload,
            source_file=path.name,
        )

    def _maybe_retry_ocr(
        self,
        document: BaseModel,
        *,
        resolved: Path,
        prior_payload: dict[str, Any],
        source_file: str,
    ) -> BaseModel:
        """Retry once with a vision model when Docling OCR is faulty.

        :param document: DocumentData from the first Docling pass.
        :param resolved: Path Docling consumed (PNG or PDF).
        :param prior_payload: Docling payload used for confidence/signature reuse.
        :param source_file: Basename of the original source path.
        :return: Original or retry DocumentData (never recurses).
        """
        if not isinstance(document, DocumentData):
            return document
        if not document.metadata.faulty_extraction:
            return document

        if self.ocr_retry is None or not self.ocr_retry.enabled:
            log_branch_decision(
                logger,
                branch="ocr_retry",
                outcome="SKIP",
                reason="disabled_or_unset",
                file=source_file,
            )
            return document

        if resolved.suffix.lower() == ".pdf":
            log_branch_decision(
                logger,
                branch="ocr_retry",
                outcome="SKIP",
                reason="pdf",
                file=source_file,
            )
            return document

        if resolved.suffix.lower() not in _IMAGE_RETRY_SUFFIXES:
            log_branch_decision(
                logger,
                branch="ocr_retry",
                outcome="SKIP",
                reason="unsupported_suffix",
                file=source_file,
            )
            return document

        log_branch_decision(
            logger,
            branch="ocr_retry",
            outcome="START",
            reason="faulty_extraction",
            file=source_file,
            model=self.ocr_retry.model,
        )

        try:
            retry_text = self._vision_ocr_text(
                resolved,
                model=self.ocr_retry.model,
                prompt=self.ocr_retry.prompt,
            )
        except Exception as exc:
            log_branch_decision(
                logger,
                branch="ocr_retry",
                outcome="ERROR",
                reason=type(exc).__name__,
                level=logging.WARNING,
                file=source_file,
                model=self.ocr_retry.model,
            )
            return document.model_copy(
                update={
                    "metadata": document.metadata.model_copy(
                        update={
                            "retry_used": True,
                            "retry_model": self.ocr_retry.model,
                        }
                    )
                }
            )

        retry_payload = {
            "text": retry_text,
            "confidence": prior_payload.get("confidence", _MISSING),
            "has_signature": prior_payload.get("has_signature", False),
        }
        retry_processed = self.preprocessor.preprocess(retry_payload)
        retry_document = self._to_model(retry_processed, source_file=source_file)
        if not isinstance(retry_document, DocumentData):
            return document

        retry_meta = retry_document.metadata.model_copy(
            update={
                "retry_used": True,
                "retry_model": self.ocr_retry.model,
            }
        )
        retry_document = retry_document.model_copy(update={"metadata": retry_meta})

        if retry_document.metadata.faulty_extraction:
            log_branch_decision(
                logger,
                branch="ocr_retry",
                outcome="STILL_FAULTY",
                reason=",".join(retry_document.metadata.failure_reasons) or "faulty_extraction",
                level=logging.WARNING,
                file=source_file,
                model=self.ocr_retry.model,
            )
        else:
            log_branch_decision(
                logger,
                branch="ocr_retry",
                outcome="SUCCESS",
                reason="extraction_cleared",
                file=source_file,
                model=self.ocr_retry.model,
            )
        return retry_document

    def _vision_ocr_text(self, image_path: Path, *, model: str, prompt: str) -> str:
        """Call the configured vision model to transcribe a document image.

        :param image_path: Resolved PNG (or other image) path for multimodal input.
        :param model: Vision model name from ``ocr_retry`` config.
        :param prompt: Transcription instruction from ``ocr_retry`` config.
        :return: Model message content (markdown/plain text).
        """
        response = self._retry_chat(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                    "images": [str(image_path)],
                }
            ],
        )
        return response_content(response)

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
                "fields": {
                    "decision": _FRAUD_DENY,
                    "reason": _FRAUD_REASON,
                    "benford_chi_squared": benford.chi_squared,
                    "benford_conformity": False,
                },
                "metadata": DocumentMetaData(
                    source_file=Path(benford.image_path).name if benford.image_path else _MISSING,
                    extraction_probability=_MISSING,
                    faulty_extraction=False,
                    human_in_the_loop=False,
                ),
            }
        )

    def _docling_payload(self, docling_path: Path) -> dict[str, Any]:
        """Run Docling on an already-resolved path and return text + confidence.

        Signature presence is taken from DocumentFigureClassifier picture labels
        (``do_picture_classification``), not from OCR text heuristics.

        :param docling_path: PNG or PDF path ready for DocumentConverter.
        :return: Dict with ``text``, aggregate ``confidence``, and ``has_signature``.
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
        has_signature = _has_signature_from_pictures(result.document)
        log_branch_decision(
            logger,
            branch="signature",
            outcome="DETECTED" if has_signature else "ABSENT",
            reason="document_figure_classifier",
            file=docling_path.name,
            pictures=len(getattr(result.document, "pictures", None) or []),
        )
        return {"text": text, "confidence": confidence, "has_signature": has_signature}

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

    def _to_model(self, processed: Any, *, source_file: str) -> BaseModel:
        """Build DocumentData with DocumentMetaData (signature, probability, HITL).

        ``ExtractionFailure`` marks unusable OCR as ``faulty_extraction`` and forces
        ``human_in_the_loop``. Low ``extraction_probability`` also forces HITL.

        :param processed: Output of DocumentPreprocessor.preprocess.
        :param source_file: Basename of the source document path.
        :return: DocumentData instance including populated metadata.
        """
        confidence = processed.get("confidence", _MISSING)
        failure = self.extraction_failure.evaluate(processed.get("raw_text", _MISSING))
        low_confidence = False
        if isinstance(confidence, (int, float)) and not math.isnan(float(confidence)):
            low_confidence = float(confidence) < self.confidence_threshold
            if low_confidence:
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

        hitl = failure.faulty or low_confidence
        if failure.faulty:
            log_branch_decision(
                logger,
                branch="extraction_failure",
                outcome="HITL",
                reason=",".join(failure.reasons) or "faulty_extraction",
                level=logging.WARNING,
                file=source_file,
            )

        metadata = DocumentMetaData(
            source_file=source_file,
            has_signature=bool(processed.get("has_signature", False)),
            extraction_probability=confidence,
            faulty_extraction=failure.faulty,
            human_in_the_loop=hitl,
            failure_reasons=list(failure.reasons),
        )
        return DocumentData.model_validate(
            {
                "person": processed.get("person", _MISSING),
                "date": processed.get("date", _MISSING),
                "raw_text": processed.get("raw_text", _MISSING),
                "timestamps": processed.get("timestamps", []),
                "fields": processed.get("fields", {}),
                "metadata": metadata,
            }
        )
