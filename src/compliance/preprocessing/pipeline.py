from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import numpy as np

from compliance.config.settings import AppConfig
from compliance.models.claim import (
    BookingData,
    ClaimBundle,
    DocumentData,
    GroundTruth,
    SourceFiles,
)
from compliance.preprocessing.answer import AnswerReader
from compliance.preprocessing.description import DescriptionReader
from compliance.preprocessing.document import DocumentReader
from compliance.preprocessing.extractor import InformationExtractor
from compliance.preprocessing.markdown import MarkdownReader
from compliance.preprocessing.preprocessing import FormatConverter

logger = logging.getLogger(__name__)

_MISSING = np.nan
_CLAIM_NUM = re.compile(r"(\d+)")


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
        if name in {"answer.json", "description.txt", "processed.json"}:
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


def _read_ground_truth(answer_path: str | float, answer_reader: AnswerReader) -> GroundTruth:
    """Load GroundTruth, or a placeholder when answer.json is missing.

    :param answer_path: Path string or np.nan.
    :param answer_reader: AnswerReader instance.
    :return: GroundTruth model.
    """
    if not _is_present(answer_path):
        logger.warning("Missing answer.json — using UNKNOWN decision")
        return GroundTruth(decision="UNKNOWN")
    return answer_reader.read(Path(str(answer_path)))  # type: ignore[return-value]


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
            logger.warning("Markdown read failed for %s: %s", path.name, exc)
            continue
        assert isinstance(parsed, BookingData)
        if path.name.lower().startswith("supporting"):
            booking_data = parsed
        else:
            internal_data.append(parsed)

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
        return BookingData(), _MISSING

    path = Path(str(description_path))
    try:
        booking = description_reader.read(path)
        assert isinstance(booking, BookingData)
        return booking, description_reader.last_raw_text
    except Exception as exc:
        logger.warning("Description extraction failed for %s: %s", path, exc)
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
            logger.warning("Document extraction failed for %s: %s", path.name, exc)
            continue
        assert isinstance(parsed, DocumentData)
        documents.append(parsed)
        logger.info("Extracted document %s (hitl=%s)", path.name, parsed.human_in_the_loop)
    return documents


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
        document_reader = DocumentReader(
            document_formats=prep.document_formats,
            confidence_threshold=prep.confidence_threshold,
            format_converter=format_converter,
        )

    ground_truth = _read_ground_truth(sources.answer_path, answer_reader)
    booking_data, internal_data = _read_markdowns(sources.markdown_paths, markdown_reader)
    description_booking, description_text = _read_description(
        sources.description_path,
        description_reader,
    )
    documents = _read_documents(sources.document_paths, document_reader)

    return ClaimBundle(
        claim_id=claim_dir.name,
        ground_truth=ground_truth,
        booking_data=booking_data,
        description_booking=description_booking,
        internal_data=internal_data,
        documents=documents,
        description_text=description_text,
        source_files=sources,
    )


def _write_processed(claim_dir: Path, bundle: ClaimBundle, output_filename: str) -> Path:
    """Write ClaimBundle JSON to the claim folder.

    :param claim_dir: Claim folder path.
    :param bundle: Bundle to serialize.
    :param output_filename: Output filename from config.
    :return: Path written.
    """
    out_path = claim_dir / output_filename
    out_path.write_text(bundle.model_dump_json(indent=2), encoding="utf-8")
    return out_path


def run_pipeline(config: AppConfig, **reader_overrides: Any) -> list[ClaimBundle]:
    """Discover claims, process each, and write processed.json per folder.

    Extraction/Docling failures are logged; the run continues for remaining claims.

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
            out_path = _write_processed(
                claim_dir,
                bundle,
                config.preprocessing.output_filename,
            )
            logger.info(
                "Wrote %s (%d documents, %d internal md)",
                out_path,
                len(bundle.documents),
                len(bundle.internal_data),
            )
            bundles.append(bundle)
        except Exception as exc:
            logger.exception("Failed to process %s: %s", claim_dir.name, exc)

    return bundles
