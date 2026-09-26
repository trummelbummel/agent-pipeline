from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from compliance.branch_log import log_branch_decision
from compliance.config.settings import AppConfig, PreprocessedArtifactNames
from compliance.models.claim import (
    BookingData,
    ClaimBundle,
    DocumentData,
    DocumentMetaData,
    is_nan_scalar,
)
from compliance.preprocessing.claim_batch import (
    _claim_document_summary,
    _discover_claim_folders,
    _document_decision_fields,
    _predicted_answer_from_bundle,
    _process_single_claim,
)
from compliance.preprocessing.extraction_failure import ExtractionFailure
from compliance.preprocessing.preprocessing import FormatConverter
from compliance.workflows.predicted_answer_io import (
    remove_stale_preprocess_prediction,
    write_preprocess_predicted_answer,
)

logger = logging.getLogger(__name__)


def _validate_claim_dir_name(name: str) -> None:
    """Refuse claim folder names that could escape the output root (T-03-03).

    :param name: ``claim_dir.name`` path segment.
    :raises ValueError: When the name is not a single safe path segment.
    """
    if os.sep in name or (os.altsep is not None and os.altsep in name):
        _path_safety_denial(name, reason="path_separator")
    if name in {".", ".."}:
        _path_safety_denial(name, reason="dot_segment")
    log_branch_decision(
        logger,
        branch="path_safety",
        outcome="PASS",
        reason="single_segment",
        level=logging.DEBUG,
        claim=name,
    )


def _path_safety_denial(name: str, reason: str) -> None:
    log_branch_decision(
        logger,
        branch="path_safety",
        outcome="DENY",
        reason=reason,
        level=logging.WARNING,
        claim=name,
    )
    raise ValueError(f"Unsafe claim directory name: {name!r}")


def _is_claim_folder(path: Path) -> bool:
    """Return True when ``path`` is a single safe claim folder (startswith claim).

    :param path: Candidate filesystem path.
    :return: Whether ``path`` should be treated as one claim folder (not a batch root).
    """
    if not path.is_dir():
        return False
    try:
        _validate_claim_dir_name(path.name)
    except ValueError:
        return False
    return path.name.lower().startswith("claim")


def _description_txt_bytes(bundle: ClaimBundle) -> bytes:
    text = bundle.description_text
    if is_nan_scalar(text) or not isinstance(text, str):
        return b""
    return text.encode("utf-8")


def _answer_json_text(bundle: ClaimBundle) -> str:
    return bundle.ground_truth.model_dump_json(indent=2)


def _booking_md_lines(heading: str, booking: BookingData) -> list[str]:
    """Render non-nan BookingData fields as markdown key/value lines.

    :param heading: Section heading (without ``##`` prefix).
    :param booking: Booking record to render.
    :return: Markdown lines including the heading, or empty when all fields nan.
    """
    field_lines: list[str] = []
    for key, value in booking.model_dump().items():
        if is_nan_scalar(value):
            continue
        field_lines.append(f"**{key}**: {value}")
    if not field_lines:
        return []
    return [f"## {heading}", *field_lines]


def _document_md_lines(index: int, document: DocumentData) -> list[str]:
    """Render one Docling-extracted document as a markdown section.

    :param index: 1-based document ordinal.
    :param document: Extracted document (``raw_text`` is Docling markdown).
    :return: Markdown lines for this document.
    """
    raw = document.raw_text
    body = "" if is_nan_scalar(raw) or not isinstance(raw, str) else raw
    return [f"## Document: {index}", body]


def _markdown_document(title: str, sections: list[list[str]]) -> str:
    if not sections:
        return f"# {title}\n\n_none_\n"
    body = "\n\n".join("\n".join(chunk) for chunk in sections)
    return f"# {title}\n\n{body}\n"


def _supporting_document_md_text(bundle: ClaimBundle) -> str:
    """Markdown body for supporting_document.md from Docling document content.

    :param bundle: Populated ClaimBundle.
    :return: Full markdown document text (Docling exports only; no JSON dump).
    """
    sections = [
        _document_md_lines(i, document)
        for i, document in enumerate(bundle.documents, start=1)
    ]
    return _markdown_document("Supporting document", sections)


def _supporting_documents_md_text(bundle: ClaimBundle) -> str:
    """Markdown body for supporting_documents.md from booking and internal data.

    :param bundle: Populated ClaimBundle.
    :return: Full markdown document text.
    """
    sections: list[list[str]] = []

    booking_lines = _booking_md_lines("Booking", bundle.booking_data)
    if booking_lines:
        sections.append(booking_lines)
    for i, internal in enumerate(bundle.internal_data, start=1):
        internal_lines = _booking_md_lines(f"Internal: {i}", internal)
        if internal_lines:
            sections.append(internal_lines)

    return _markdown_document("Supporting documents", sections)


def _document_metadata_entries(bundle: ClaimBundle) -> list[DocumentMetaData]:
    """Collect DocumentMetaData for JSON persistence, including empty-doc HITL.

    When no documents were extracted (e.g. claim 8 ``supporting_document.md`` is
    ``_none_``), emit one faulty metadata row so human-in-the-loop is recorded.

    :param bundle: Populated ClaimBundle.
    :return: Metadata rows to serialize under ``document_metadata.json``.
    """
    if bundle.documents:
        return [document.metadata for document in bundle.documents]

    failure = ExtractionFailure().evaluate("_none_")
    return [
        DocumentMetaData(
            faulty_extraction=failure.faulty,
            human_in_the_loop=True,
            failure_reasons=list(failure.reasons) or ["empty_text"],
        )
    ]


def _document_metadata_json_text(bundle: ClaimBundle) -> str:
    """JSON body for document_metadata.json.

    :param bundle: Populated ClaimBundle.
    :return: Pretty-printed JSON with a ``documents`` metadata list.
    """
    entries = _document_metadata_entries(bundle)
    payload = {"documents": [entry.model_dump(mode="json") for entry in entries]}
    return json.dumps(payload, indent=2)


def _log_preprocessed_documents(claim_name: str, bundle: ClaimBundle) -> None:
    for document in bundle.documents:
        decision, reason = _document_decision_fields(document)
        log_branch_decision(
            logger,
            branch="preprocessed_document",
            outcome=decision,
            reason=reason,
            level=logging.WARNING
            if decision == "DENY" or document.metadata.human_in_the_loop
            else logging.INFO,
            claim=claim_name,
            hitl=document.metadata.human_in_the_loop,
            faulty=document.metadata.faulty_extraction,
        )


class PreprocessingPipeline:
    """Mirror claim folders into a preprocessed artifact tree.

    Composes Phase 1 ``_process_single_claim``; projects each ClaimBundle into
    config-named artifacts under ``preprocessing.preprocessed_dir``. Pipeline
    predictions (predicted_answer) are written under ``preprocessing.results_dir``.

    :param config: Loaded application configuration.
    :param reader_overrides: Optional injected readers for tests.
    """

    def __init__(self, config: AppConfig, **reader_overrides: Any) -> None:
        self._config = config
        self._reader_overrides = reader_overrides

    @property
    def output_root(self) -> Path:
        """Root directory for mirrored preprocessed claim outputs."""
        return Path(self._config.preprocessing.preprocessed_dir)

    @property
    def results_root(self) -> Path:
        """Root directory for pipeline prediction artifacts."""
        return Path(self._config.preprocessing.results_dir)

    @property
    def artifacts(self) -> PreprocessedArtifactNames:
        """Configured preprocessed artifact filenames."""
        return self._config.preprocessing.artifacts

    def process_claim(self, claim_dir: Path, output_root: Path | None = None) -> Path:
        """Project one claim folder into a mirrored preprocessed artifact tree.

        :param claim_dir: Source claim folder path.
        :param output_root: Destination root; defaults to ``self.output_root``.
        :return: Path to the written claim output directory.
        :raises ValueError: When ``claim_dir.name`` is not a safe single path segment.
        """
        _validate_claim_dir_name(claim_dir.name)

        root = self.output_root if output_root is None else output_root
        bundle = _process_single_claim(claim_dir, self._config, **self._reader_overrides)

        claim_out = root / claim_dir.name
        claim_out.mkdir(parents=True, exist_ok=True)
        predicted_path = self._write_claim_artifacts(claim_out, bundle)
        summary = _claim_document_summary(bundle)
        _log_preprocessed_documents(claim_dir.name, bundle)
        log_branch_decision(
            logger,
            branch="preprocessed_write",
            outcome="WROTE",
            reason="artifact_tree",
            claim=claim_dir.name,
            fraud_deny=summary["fraud_deny"],
            hitl=summary["hitl"],
            extracted=summary["extracted"],
            artifacts=",".join(self._written_artifact_names(claim_out, predicted_path)),
        )
        return claim_out

    def run(self, source: Path | None = None) -> list[Path]:
        """Process one claim folder or soft-fail batch under a claims directory.

        :param source: Caller-supplied path — one claim folder, a directory of
            claims, or ``None`` to use config ``data_dir``.
        :return: Paths to successfully written claim output directories.
        """
        output_root = self.output_root
        output_root.mkdir(parents=True, exist_ok=True)
        self.results_root.mkdir(parents=True, exist_ok=True)

        if source is not None and _is_claim_folder(source):
            log_branch_decision(
                logger,
                branch="workflow_batch",
                outcome="SINGLE",
                reason="caller_claim_folder",
                claim=source.name,
            )
            return [self.process_claim(source, output_root)]

        data_dir = (
            Path(self._config.preprocessing.data_dir) if source is None else source
        )
        folders = _discover_claim_folders(data_dir)
        logger.info("Discovered %d claim folders under %s", len(folders), data_dir)

        written = self._written_claim_outputs(folders, output_root)
        log_branch_decision(
            logger,
            branch="workflow_batch",
            outcome="COMPLETE",
            reason="soft_fail_batch",
            written=len(written),
            total=len(folders),
        )
        return written

    def _written_claim_outputs(
        self, folders: list[Path], output_root: Path
    ) -> list[Path]:
        written: list[Path] = []
        for claim_dir in folders:
            logger.info("Processing %s", claim_dir.name)
            try:
                written.append(self.process_claim(claim_dir, output_root))
            except Exception as exc:
                log_branch_decision(
                    logger,
                    branch="preprocessed_write",
                    outcome="SKIP",
                    reason="claim_failed",
                    level=logging.ERROR,
                    claim=claim_dir.name,
                    error=type(exc).__name__,
                )
                logger.exception("Failed to process %s: %s", claim_dir.name, exc)
        return written

    def _written_artifact_names(
        self, claim_out: Path, predicted_path: Path | None
    ) -> list[str]:
        names = self.artifacts
        written_names = [
            names.description,
            names.answer,
            names.supporting_document,
            names.supporting_documents,
            names.document_metadata,
            *[path.name for path in claim_out.glob("*.png")],
        ]
        if predicted_path is not None:
            written_names.insert(2, names.predicted_answer)
        return written_names

    def _write_claim_artifacts(self, claim_out: Path, bundle: ClaimBundle) -> Path | None:
        """Write preprocessed artifacts and optional predicted_answer under results_dir.

        :param claim_out: Destination claim output directory (preprocessed tree).
        :param bundle: Populated ClaimBundle for this claim.
        :return: Path to predicted_answer when written; otherwise None.
        """
        self._write_mirrored_artifacts(claim_out, bundle)
        return self._predicted_answer_path(claim_out, bundle)

    def _write_mirrored_artifacts(self, claim_out: Path, bundle: ClaimBundle) -> None:
        names = self.artifacts
        (claim_out / names.description).write_bytes(_description_txt_bytes(bundle))
        (claim_out / names.answer).write_text(
            _answer_json_text(bundle) + "\n", encoding="utf-8"
        )
        (claim_out / names.supporting_document).write_text(
            _supporting_document_md_text(bundle),
            encoding="utf-8",
        )
        (claim_out / names.supporting_documents).write_text(
            _supporting_documents_md_text(bundle),
            encoding="utf-8",
        )
        (claim_out / names.document_metadata).write_text(
            _document_metadata_json_text(bundle) + "\n",
            encoding="utf-8",
        )
        self._write_document_pngs(claim_out, bundle)

    def _predicted_answer_path(
        self, claim_out: Path, bundle: ClaimBundle
    ) -> Path | None:
        results_claim = self.results_root / claim_out.name
        predicted_path = results_claim / self.artifacts.predicted_answer
        analysis_result_path = results_claim / self.artifacts.analysis_result
        predicted = _predicted_answer_from_bundle(bundle)
        if predicted is None:
            # Drop preprocess-origin leftovers (e.g. Benford DENYs) only when
            # analysis has not authored a sibling result — never wipe evaluator
            # predictions written by ClaimPipeline.
            remove_stale_preprocess_prediction(
                predicted_path,
                analysis_result_path=analysis_result_path,
            )
            return None

        return write_preprocess_predicted_answer(predicted_path, predicted)

    def _write_document_pngs(self, claim_out: Path, bundle: ClaimBundle) -> list[Path]:
        """Copy or convert claim raster documents to PNG under ``claim_out``.

        PDFs are skipped (FormatConverter cannot rasterize them). Existing PNGs
        are copied under their original basename; other rasters become ``{stem}.png``.

        :param claim_out: Destination claim output directory.
        :param bundle: Claim bundle whose ``source_files.document_paths`` are written.
        :return: Paths of PNG files written under ``claim_out``.
        """
        converter = FormatConverter(
            source_formats=self._config.preprocessing.document_formats
        )
        written: list[Path] = []
        for path_str in bundle.source_files.document_paths:
            src = Path(path_str)
            suffix = src.suffix.lower().lstrip(".")
            if suffix == "pdf":
                log_branch_decision(
                    logger,
                    branch="preprocessed_png",
                    outcome="SKIP",
                    reason="pdf",
                    claim=bundle.claim_id,
                    file=src.name,
                )
                continue
            png_path = converter.to_png(src, output_dir=claim_out)
            written.append(png_path)
            log_branch_decision(
                logger,
                branch="preprocessed_png",
                outcome="WROTE",
                reason="copy" if suffix == "png" else "convert",
                claim=bundle.claim_id,
                file=src.name,
                png=png_path.name,
            )
        return written


def output_root_from_config(config: AppConfig) -> Path:
    """Resolve the workflows preprocessed output root from config.

    Public convenience for callers that do not need a full pipeline instance.

    :param config: Loaded application configuration.
    :return: Path to ``preprocessing.preprocessed_dir``.
    """
    return Path(config.preprocessing.preprocessed_dir)


def results_root_from_config(config: AppConfig) -> Path:
    """Resolve the pipeline results output root from config.

    Public convenience for callers that do not need a full pipeline instance.

    :param config: Loaded application configuration.
    :return: Path to ``preprocessing.results_dir``.
    """
    return Path(config.preprocessing.results_dir)
