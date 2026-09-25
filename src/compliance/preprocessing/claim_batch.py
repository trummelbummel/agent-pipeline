from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from compliance.branch_log import log_branch_decision
from compliance.config.settings import AppConfig
from compliance.models.claim import (
    _MISSING,
    BookingData,
    ClaimBundle,
    DocumentData,
    GroundTruth,
    SourceFiles,
    is_nan_scalar,
)
from compliance.preprocessing.answer import AnswerReader
from compliance.preprocessing.description import DescriptionReader
from compliance.preprocessing.document import DocumentReader
from compliance.preprocessing.extractor import InformationExtractor
from compliance.preprocessing.markdown import MarkdownReader
from compliance.preprocessing.preprocessing import FormatConverter
from compliance.tools.benford import BenfordLawChecker

logger = logging.getLogger(__name__)

_CLAIM_NUM = re.compile(r"(\d+)")
_FRAUD_DENY = "DENY"
_PREDICTABLE_DECISIONS = frozenset({"DENY", "APPROVE", "UNCERTAIN"})


def _discover_claim_folders(data_dir: Path) -> list[Path]:
    """List claim folders under ``data_dir``, sorted by claim number.

    :param data_dir: Root directory containing ``claim N`` folders.
    :return: Sorted list of claim directory paths.
    """
    if not data_dir.is_dir():
        msg = f"Data directory not found: {data_dir}"
        raise FileNotFoundError(msg)

    folders = [path for path in data_dir.iterdir() if path.is_dir() and path.name.lower().startswith("claim")]
    return sorted(folders, key=_claim_sort_key)


def _claim_sort_key(path: Path) -> tuple[int, str]:
    """Sort key that prefers numeric claim ids.

    :param path: Claim folder path.
    :return: (number, name) for stable ordering.
    """
    match = _CLAIM_NUM.search(path.name)
    number = int(match.group(1)) if match else 0
    return (number, path.name)


def _classify_files(claim_dir: Path, document_formats: list[str]) -> SourceFiles:
    """Classify files in a claim folder into SourceFiles buckets.

    :param claim_dir: Path to a single claim folder.
    :param document_formats: Configured document extensions (no dots).
    :return: SourceFiles with discovered paths.
    """
    formats = {fmt.lower().lstrip(".") for fmt in document_formats}
    answer_path = claim_dir / "answer.json"
    description_path = claim_dir / "description.txt"
    markdown_paths: list[str] = []
    document_paths: list[str] = []

    for path in sorted(claim_dir.iterdir()):
        if not path.is_file():
            continue
        name = path.name
        if name in {"answer.json", "description.txt"}:
            continue
        suffix = path.suffix.lower().lstrip(".")
        if suffix == "md":
            markdown_paths.append(str(path))
        elif suffix in formats:
            document_paths.append(str(path))

    return SourceFiles(
        description_path=str(description_path) if description_path.is_file() else _MISSING,
        answer_path=str(answer_path) if answer_path.is_file() else _MISSING,
        markdown_paths=markdown_paths,
        document_paths=document_paths,
    )


def _is_present(path_value: str | float) -> bool:
    """Return True when a SourceFiles path field holds a real path string.

    :param path_value: Path string or np.nan sentinel.
    :return: Whether the path is usable.
    """
    return isinstance(path_value, str) and bool(path_value)


def _document_decision_fields(document: DocumentData) -> tuple[str, str]:
    """Extract decision/reason from a DocumentData (extras or fields).

    :param document: Parsed document model.
    :return: (decision, reason) with EXTRACTED/docling when no early deny.
    """
    decision = getattr(document, "decision", None)
    reason = getattr(document, "reason", None)
    if isinstance(decision, str) and decision:
        reason_text = reason if isinstance(reason, str) and reason else "unspecified"
        return decision, reason_text
    field_decision = document.fields.get("decision")
    field_reason = document.fields.get("reason")
    if isinstance(field_decision, str) and field_decision:
        reason_text = field_reason if isinstance(field_reason, str) and field_reason else "unspecified"
        return field_decision, reason_text
    return "EXTRACTED", "docling"


def _read_ground_truth(answer_path: str | float, answer_reader: AnswerReader) -> GroundTruth:
    """Load GroundTruth, or a placeholder when answer.json is missing.

    :param answer_path: Path string or np.nan.
    :param answer_reader: AnswerReader instance.
    :return: GroundTruth model.
    """
    if not _is_present(answer_path):
        log_branch_decision(
            logger,
            branch="ground_truth",
            outcome="UNKNOWN",
            reason="missing_answer_json",
            level=logging.WARNING,
        )
        return GroundTruth(decision="UNKNOWN")
    assert isinstance(answer_path, str)
    ground_truth = answer_reader.read(Path(answer_path))
    assert isinstance(ground_truth, GroundTruth)
    log_branch_decision(
        logger,
        branch="ground_truth",
        outcome=ground_truth.decision,
        reason="answer_json",
    )
    return ground_truth


def _read_markdowns(
    markdown_paths: list[str],
    markdown_reader: MarkdownReader,
) -> tuple[BookingData, list[BookingData]]:
    """Parse markdown files into primary booking_data and internal_data.

    ``supporting*`` files become ``booking_data``; all other ``.md`` files
    append to ``internal_data``. Failures are logged without aborting.

    :param markdown_paths: Absolute/relative paths to markdown files.
    :param markdown_reader: MarkdownReader instance.
    :return: (booking_data, internal_data).
    """
    booking_data = BookingData()
    internal_data: list[BookingData] = []

    for path_str in markdown_paths:
        path = Path(path_str)
        try:
            parsed = markdown_reader.read(path)
        except Exception as exc:
            log_branch_decision(
                logger,
                branch="markdown",
                outcome="SKIP",
                reason="read_failed",
                level=logging.WARNING,
                file=path.name,
                error=type(exc).__name__,
            )
            continue
        assert isinstance(parsed, BookingData)
        if path.name.lower().startswith("supporting"):
            booking_data = parsed
            log_branch_decision(
                logger,
                branch="markdown",
                outcome="BOOKING",
                reason="supporting_prefix",
                file=path.name,
            )
        else:
            internal_data.append(parsed)
            log_branch_decision(
                logger,
                branch="markdown",
                outcome="INTERNAL",
                reason="non_supporting_md",
                file=path.name,
            )

    return booking_data, internal_data


def _read_description(
    description_path: str | float,
    description_reader: DescriptionReader,
) -> tuple[BookingData, str | float]:
    """Extract description booking fields and retain raw text.

    LLM failures leave BookingData empty but still return raw text when
    the file exists.

    :param description_path: Path string or np.nan.
    :param description_reader: DescriptionReader instance.
    :return: (description_booking, description_text).
    """
    if not _is_present(description_path):
        log_branch_decision(
            logger,
            branch="description",
            outcome="SKIP",
            reason="missing_description",
        )
        return BookingData(), _MISSING

    assert isinstance(description_path, str)
    path = Path(description_path)
    try:
        booking = description_reader.read(path)
        assert isinstance(booking, BookingData)
        log_branch_decision(
            logger,
            branch="description",
            outcome="EXTRACTED",
            reason="llm_ok",
            file=path.name,
        )
        return booking, description_reader.last_raw_text
    except Exception as exc:
        log_branch_decision(
            logger,
            branch="description",
            outcome="RAW_FALLBACK",
            reason="llm_failed",
            level=logging.WARNING,
            file=path.name,
            error=type(exc).__name__,
        )
        try:
            return BookingData(), path.read_text(encoding="utf-8")
        except OSError:
            return BookingData(), _MISSING


def _read_documents(
    document_paths: list[str],
    document_reader: DocumentReader,
) -> list[DocumentData]:
    """Run DocumentReader on each document path; skip failures.

    :param document_paths: Paths to configured document formats.
    :param document_reader: DocumentReader instance.
    :return: Successfully extracted DocumentData entries.
    """
    documents: list[DocumentData] = []
    for path_str in document_paths:
        path = Path(path_str)
        try:
            parsed = document_reader.read(path)
        except Exception as exc:
            log_branch_decision(
                logger,
                branch="document",
                outcome="SKIP",
                reason="read_failed",
                level=logging.WARNING,
                file=path.name,
                error=type(exc).__name__,
            )
            continue
        assert isinstance(parsed, DocumentData)
        documents.append(parsed)
        decision, reason = _document_decision_fields(parsed)
        level = logging.WARNING if decision == _FRAUD_DENY else logging.INFO
        confidence = parsed.metadata.extraction_probability
        confidence_text = (
            f"{float(confidence):.3f}"
            if isinstance(confidence, (int, float)) and not is_nan_scalar(confidence)
            else "nan"
        )
        log_branch_decision(
            logger,
            branch="document_result",
            outcome=decision,
            reason=reason,
            level=level,
            file=path.name,
            hitl=parsed.metadata.human_in_the_loop,
            faulty=parsed.metadata.faulty_extraction,
            confidence=confidence_text,
        )
    return documents


def _claim_document_summary(bundle: ClaimBundle) -> dict[str, int]:
    """Count document outcomes for claim-level decision logging.

    :param bundle: Populated claim bundle.
    :return: Counts keyed by outcome label.
    """
    fraud_denies = 0
    hitl = 0
    extracted = 0
    for document in bundle.documents:
        decision, _reason = _document_decision_fields(document)
        if decision == _FRAUD_DENY:
            fraud_denies += 1
        elif document.metadata.human_in_the_loop:
            hitl += 1
        else:
            extracted += 1
    return {
        "documents": len(bundle.documents),
        "fraud_deny": fraud_denies,
        "hitl": hitl,
        "extracted": extracted,
    }


def _predicted_answer_from_bundle(bundle: ClaimBundle) -> GroundTruth | None:
    """Derive a pipeline prediction from document-level decisions.

    Prefers any ``DENY`` (e.g. Benford fraud) over other predicted labels.
    Returns None when documents carry no predicted decision.

    :param bundle: Populated claim bundle.
    :return: Predicted GroundTruth, or None when nothing was decided yet.
    """
    predictions: list[GroundTruth] = []
    for document in bundle.documents:
        decision, reason = _document_decision_fields(document)
        if decision not in _PREDICTABLE_DECISIONS:
            continue
        explanation: str | float = reason
        chi_squared = document.fields.get("benford_chi_squared")
        if reason == "fraud" and chi_squared is not None:
            explanation = f"fraud (benford chi_squared={chi_squared})"
        predictions.append(GroundTruth(decision=decision, explanation=explanation))

    if not predictions:
        return None
    for prediction in predictions:
        if prediction.decision == _FRAUD_DENY:
            return prediction
    return predictions[0]

def _process_single_claim(
    claim_dir: Path,
    config: AppConfig,
    *,
    answer_reader: AnswerReader | None = None,
    markdown_reader: MarkdownReader | None = None,
    description_reader: DescriptionReader | None = None,
    document_reader: DocumentReader | None = None,
) -> ClaimBundle:
    """Process one claim folder into a ClaimBundle.

    :param claim_dir: Path to the claim folder.
    :param config: Application config (preprocessing + extraction).
    :param answer_reader: Optional injected AnswerReader (tests).
    :param markdown_reader: Optional injected MarkdownReader (tests).
    :param description_reader: Optional injected DescriptionReader (tests).
    :param document_reader: Optional injected DocumentReader (tests).
    :return: Populated ClaimBundle for the claim.
    """
    prep = config.preprocessing
    sources = _classify_files(claim_dir, prep.document_formats)

    answer_reader = answer_reader or AnswerReader()
    markdown_reader = markdown_reader or MarkdownReader()

    if description_reader is None:
        extractor = InformationExtractor(
            target_model=BookingData,
            model_name=config.extraction.model,
            prompt=config.extraction.prompt,
        )
        description_reader = DescriptionReader(extractor=extractor)

    if document_reader is None:
        format_converter = FormatConverter(source_formats=prep.document_formats)
        benford_checker = (
            BenfordLawChecker(config.benford) if config.benford.enabled else None
        )
        document_reader = DocumentReader(
            document_formats=prep.document_formats,
            confidence_threshold=prep.confidence_threshold,
            format_converter=format_converter,
            benford_checker=benford_checker,
            ocr_retry=config.ocr_retry,
        )

    ground_truth = _read_ground_truth(sources.answer_path, answer_reader)
    booking_data, internal_data = _read_markdowns(sources.markdown_paths, markdown_reader)
    description_booking, description_text = _read_description(
        sources.description_path,
        description_reader,
    )
    documents = _read_documents(sources.document_paths, document_reader)

    bundle = ClaimBundle(
        claim_id=claim_dir.name,
        ground_truth=ground_truth,
        booking_data=booking_data,
        description_booking=description_booking,
        internal_data=internal_data,
        documents=documents,
        description_text=description_text,
        source_files=sources,
    )
    summary = _claim_document_summary(bundle)
    log_branch_decision(
        logger,
        branch="claim_summary",
        outcome=ground_truth.decision,
        reason="bundle_complete",
        claim=claim_dir.name,
        documents=summary["documents"],
        fraud_deny=summary["fraud_deny"],
        hitl=summary["hitl"],
        extracted=summary["extracted"],
        markdown=len(sources.markdown_paths),
    )
    return bundle


def run_pipeline(config: AppConfig, **reader_overrides: Any) -> list[ClaimBundle]:
    """Discover claims and process each into a ClaimBundle (no on-disk JSON dump).

    Extraction/Docling failures are logged; the run continues for remaining claims.
    Durable preprocessed artifacts are written by ``PreprocessingPipeline``, not here.

    :param config: Loaded AppConfig.
    :param reader_overrides: Optional reader injections forwarded to ``_process_single_claim``.
    :return: List of ClaimBundle results (one per claim folder processed).
    """
    data_dir = Path(config.preprocessing.data_dir)
    folders = _discover_claim_folders(data_dir)
    logger.info("Discovered %d claim folders under %s", len(folders), data_dir)

    bundles: list[ClaimBundle] = []
    for claim_dir in folders:
        logger.info("Processing %s", claim_dir.name)
        try:
            bundle = _process_single_claim(claim_dir, config, **reader_overrides)
            summary = _claim_document_summary(bundle)
            log_branch_decision(
                logger,
                branch="pipeline_write",
                outcome="PROCESSED",
                reason="claim_bundle",
                claim=claim_dir.name,
                documents=summary["documents"],
                fraud_deny=summary["fraud_deny"],
                hitl=summary["hitl"],
            )
            bundles.append(bundle)
        except Exception as exc:
            log_branch_decision(
                logger,
                branch="pipeline_write",
                outcome="SKIP",
                reason="claim_failed",
                level=logging.ERROR,
                claim=claim_dir.name,
                error=type(exc).__name__,
            )
            logger.exception("Failed to process %s: %s", claim_dir.name, exc)

    return bundles
