from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

import numpy as np

from compliance.config.settings import AppConfig
from compliance.models.claim import BookingData, ClaimBundle, DocumentData
from compliance.preprocessing.pipeline import _discover_claim_folders, _process_single_claim

logger = logging.getLogger(__name__)

_ARTIFACT_NAMES = (
    "description.txt",
    "answer.json",
    "supporting_document.json",
    "supporting_documents.md",
)


def output_root_from_config(config: AppConfig) -> Path:
    """Resolve the workflows preprocessed output root from config.

    :param config: Loaded application configuration.
    :return: Path to ``preprocessing.preprocessed_dir``.
    """
    return Path(config.preprocessing.preprocessed_dir)


def _is_nan_scalar(value: object) -> bool:
    return isinstance(value, float) and np.isnan(value)


def _validate_claim_dir_name(name: str) -> None:
    """Refuse claim folder names that could escape the output root (T-03-03).

    :param name: ``claim_dir.name`` path segment.
    :raises ValueError: When the name is not a single safe path segment.
    """
    if os.sep in name or (os.altsep is not None and os.altsep in name):
        raise ValueError(f"Unsafe claim directory name: {name!r}")
    if name in {".", ".."} or ".." in name.split(os.sep):
        raise ValueError(f"Unsafe claim directory name: {name!r}")


def _description_txt_bytes(bundle: ClaimBundle) -> bytes:
    """UTF-8 bytes for description.txt from the claim letter.

    :param bundle: Populated ClaimBundle.
    :return: Letter text encoded as UTF-8, or empty bytes when missing/nan.
    """
    text = bundle.description_text
    if not isinstance(text, str) or _is_nan_scalar(text):
        return b""
    return text.encode("utf-8")


def _answer_json_text(bundle: ClaimBundle) -> str:
    """JSON text for answer.json from ground truth.

    :param bundle: Populated ClaimBundle.
    :return: Indented JSON string (np.nan → null).
    """
    return bundle.ground_truth.model_dump_json(indent=2)


def _supporting_document_json_text(bundle: ClaimBundle) -> str:
    """JSON text for supporting_document.json wrapping DocumentData entries.

    :param bundle: Populated ClaimBundle.
    :return: Indented JSON object with a documents list.
    """
    documents = [doc.model_dump(mode="json") for doc in bundle.documents]
    return json.dumps({"documents": documents}, indent=2)


def _booking_md_lines(heading: str, booking: BookingData) -> list[str]:
    """Render non-nan BookingData fields as markdown key/value lines.

    :param heading: Section heading (without ``##`` prefix).
    :param booking: Booking record to render.
    :return: Markdown lines including the heading, or empty when all fields nan.
    """
    field_lines: list[str] = []
    for key, value in booking.model_dump().items():
        if _is_nan_scalar(value):
            continue
        field_lines.append(f"**{key}**: {value}")
    if not field_lines:
        return []
    return [f"## {heading}", *field_lines]


def _document_md_lines(index: int, document: DocumentData) -> list[str]:
    """Render one document's raw_text as a markdown section.

    :param index: 1-based document ordinal.
    :param document: Extracted DocumentData.
    :return: Markdown lines for the document section.
    """
    raw = document.raw_text
    body = "" if not isinstance(raw, str) or _is_nan_scalar(raw) else raw
    return [f"## Document: {index}", body]


def _supporting_documents_md_text(bundle: ClaimBundle) -> str:
    """Markdown body for supporting_documents.md from booking and documents.

    :param bundle: Populated ClaimBundle.
    :return: Full markdown document text.
    """
    sections: list[str] = []
    sections.extend(_booking_md_lines("Booking", bundle.booking_data))
    for i, internal in enumerate(bundle.internal_data, start=1):
        sections.extend(_booking_md_lines(f"Internal: {i}", internal))
    for i, document in enumerate(bundle.documents, start=1):
        sections.extend(_document_md_lines(i, document))

    if not sections:
        return "# Supporting documents\n\n_none_\n"

    body = "\n\n".join(
        "\n".join(chunk) if isinstance(chunk, list) else chunk
        for chunk in _chunk_sections(sections)
    )
    return f"# Supporting documents\n\n{body}\n"


def _chunk_sections(flat_lines: list[str]) -> list[list[str]]:
    """Group flat heading+field lines into section chunks.

    :param flat_lines: Alternating ``##`` headings and field/body lines.
    :return: List of per-section line lists.
    """
    chunks: list[list[str]] = []
    current: list[str] = []
    for line in flat_lines:
        if line.startswith("## ") and current:
            chunks.append(current)
            current = [line]
        else:
            current.append(line)
    if current:
        chunks.append(current)
    return chunks


def _write_claim_artifacts(claim_out: Path, bundle: ClaimBundle) -> None:
    """Write the four preprocessed artifacts into ``claim_out``.

    :param claim_out: Destination claim directory (already created).
    :param bundle: Source ClaimBundle fields to project.
    """
    (claim_out / "description.txt").write_bytes(_description_txt_bytes(bundle))
    (claim_out / "answer.json").write_text(_answer_json_text(bundle) + "\n", encoding="utf-8")
    (claim_out / "supporting_document.json").write_text(
        _supporting_document_json_text(bundle) + "\n",
        encoding="utf-8",
    )
    (claim_out / "supporting_documents.md").write_text(
        _supporting_documents_md_text(bundle),
        encoding="utf-8",
    )


def process_claim_to_preprocessed(
    claim_dir: Path,
    output_root: Path,
    config: AppConfig,
    **reader_overrides: Any,
) -> Path:
    """Project one claim folder into a mirrored preprocessed artifact tree.

    Composes Phase 1 ``_process_single_claim``; does not rewrite the Phase 1 bundle output path.

    :param claim_dir: Source claim folder path.
    :param output_root: Root directory for mirrored claim outputs.
    :param config: Application config (readers use preprocessing settings).
    :param reader_overrides: Optional injected readers for tests.
    :return: Path to the written claim output directory.
    :raises ValueError: When ``claim_dir.name`` is not a safe single path segment.
    """
    _validate_claim_dir_name(claim_dir.name)

    bundle = _process_single_claim(claim_dir, config, **reader_overrides)

    claim_out = output_root / claim_dir.name
    claim_out.mkdir(parents=True, exist_ok=True)
    logger.info("Writing preprocessed artifacts for %s under %s", claim_dir.name, claim_out)
    _write_claim_artifacts(claim_out, bundle)
    logger.info("Wrote %s for %s", ", ".join(_ARTIFACT_NAMES), claim_dir.name)
    return claim_out


def run_preprocessing_workflow(
    config: AppConfig,
    **reader_overrides: Any,
) -> list[Path]:
    """Discover all claims and write mirrored preprocessed artifacts (batch).

    Per-claim failures are logged and skipped so the full run continues.

    :param config: Loaded application configuration.
    :param reader_overrides: Optional injected readers for tests.
    :return: Paths to successfully written claim output directories.
    """
    data_dir = Path(config.preprocessing.data_dir)
    folders = _discover_claim_folders(data_dir)
    logger.info("Discovered %d claim folders under %s", len(folders), data_dir)

    output_root = output_root_from_config(config)
    output_root.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    for claim_dir in folders:
        logger.info("Processing %s", claim_dir.name)
        try:
            claim_out = process_claim_to_preprocessed(
                claim_dir,
                output_root,
                config,
                **reader_overrides,
            )
            written.append(claim_out)
        except Exception as exc:
            logger.exception("Failed to process %s: %s", claim_dir.name, exc)

    logger.info("Wrote preprocessed artifacts for %d of %d claims", len(written), len(folders))
    return written
