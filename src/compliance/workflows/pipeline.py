from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from compliance.branch_log import log_branch_decision
from compliance.config.settings import AppConfig, PreprocessedArtifactNames
from compliance.models.claim import BookingData, ClaimBundle, DocumentData, is_nan_scalar
from compliance.preprocessing.claim_batch import (
    _claim_document_summary,
    _discover_claim_folders,
    _document_decision_fields,
    _predicted_answer_from_bundle,
    _process_single_claim,
)

logger = logging.getLogger(__name__)


def _validate_claim_dir_name(name: str) -> None:
    """Refuse claim folder names that could escape the output root (T-03-03).

    :param name: ``claim_dir.name`` path segment.
    :raises ValueError: When the name is not a single safe path segment.
    """
    if os.sep in name or (os.altsep is not None and os.altsep in name):
        log_branch_decision(
            logger,
            branch="path_safety",
            outcome="DENY",
            reason="path_separator",
            level=logging.WARNING,
            claim=name,
        )
        raise ValueError(f"Unsafe claim directory name: {name!r}")
    if name in {".", ".."}:
        log_branch_decision(
            logger,
            branch="path_safety",
            outcome="DENY",
            reason="dot_segment",
            level=logging.WARNING,
            claim=name,
        )
        raise ValueError(f"Unsafe claim directory name: {name!r}")
    log_branch_decision(
        logger,
        branch="path_safety",
        outcome="PASS",
        reason="single_segment",
        level=logging.DEBUG,
        claim=name,
    )

def _description_txt_bytes(bundle: ClaimBundle) -> bytes:
    text = bundle.description_text
    if not isinstance(text, str):
        return b""
    return text.encode("utf-8")


def _answer_json_text(bundle: ClaimBundle) -> str:
    return bundle.ground_truth.model_dump_json(indent=2)


def _supporting_document_json_text(bundle: ClaimBundle) -> str:
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
        if is_nan_scalar(value):
            continue
        field_lines.append(f"**{key}**: {value}")
    if not field_lines:
        return []
    return [f"## {heading}", *field_lines]


def _document_md_lines(index: int, document: DocumentData) -> list[str]:
    raw = document.raw_text
    body = raw if isinstance(raw, str) else ""
    return [f"## Document: {index}", body]


def _supporting_documents_md_text(bundle: ClaimBundle) -> str:
    """Markdown body for supporting_documents.md from booking and documents.

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
    for i, document in enumerate(bundle.documents, start=1):
        sections.append(_document_md_lines(i, document))

    if not sections:
        return "# Supporting documents\n\n_none_\n"

    body = "\n\n".join("\n".join(chunk) for chunk in sections)
    return f"# Supporting documents\n\n{body}\n"


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
        for document in bundle.documents:
            decision, reason = _document_decision_fields(document)
            log_branch_decision(
                logger,
                branch="preprocessed_document",
                outcome=decision,
                reason=reason,
                level=logging.WARNING if decision == "DENY" else logging.INFO,
                claim=claim_dir.name,
                hitl=document.human_in_the_loop,
            )
        names = self.artifacts
        written_names = [
            names.description,
            names.answer,
            names.supporting_document,
            names.supporting_documents,
        ]
        if predicted_path is not None:
            written_names.insert(2, names.predicted_answer)
        log_branch_decision(
            logger,
            branch="preprocessed_write",
            outcome="WROTE",
            reason="artifact_tree",
            claim=claim_dir.name,
            fraud_deny=summary["fraud_deny"],
            hitl=summary["hitl"],
            extracted=summary["extracted"],
            artifacts=",".join(written_names),
        )
        return claim_out

    def run(self) -> list[Path]:
        """Discover all claims and write mirrored preprocessed artifacts (batch).

        Per-claim failures are logged and skipped so the full run continues.

        :return: Paths to successfully written claim output directories.
        """
        data_dir = Path(self._config.preprocessing.data_dir)
        folders = _discover_claim_folders(data_dir)
        logger.info("Discovered %d claim folders under %s", len(folders), data_dir)

        output_root = self.output_root
        output_root.mkdir(parents=True, exist_ok=True)
        self.results_root.mkdir(parents=True, exist_ok=True)

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

        log_branch_decision(
            logger,
            branch="workflow_batch",
            outcome="COMPLETE",
            reason="soft_fail_batch",
            written=len(written),
            total=len(folders),
        )
        return written

    def _write_claim_artifacts(self, claim_out: Path, bundle: ClaimBundle) -> Path | None:
        """Write preprocessed artifacts and optional predicted_answer under results_dir.

        :param claim_out: Destination claim output directory (preprocessed tree).
        :param bundle: Populated ClaimBundle for this claim.
        :return: Path to predicted_answer when written; otherwise None.
        """
        names = self.artifacts
        (claim_out / names.description).write_bytes(_description_txt_bytes(bundle))
        (claim_out / names.answer).write_text(_answer_json_text(bundle) + "\n", encoding="utf-8")
        (claim_out / names.supporting_document).write_text(
            _supporting_document_json_text(bundle) + "\n",
            encoding="utf-8",
        )
        (claim_out / names.supporting_documents).write_text(
            _supporting_documents_md_text(bundle),
            encoding="utf-8",
        )

        predicted = _predicted_answer_from_bundle(bundle)
        if predicted is None:
            log_branch_decision(
                logger,
                branch="predicted_answer",
                outcome="SKIP",
                reason="no_pipeline_decision",
                claim=bundle.claim_id,
            )
            return None

        results_claim = self.results_root / claim_out.name
        results_claim.mkdir(parents=True, exist_ok=True)
        predicted_path = results_claim / names.predicted_answer
        predicted_path.write_text(predicted.model_dump_json(indent=2) + "\n", encoding="utf-8")
        log_branch_decision(
            logger,
            branch="predicted_answer",
            outcome="WROTE",
            reason=str(predicted.explanation) if isinstance(predicted.explanation, str) else "decision",
            claim=bundle.claim_id,
            decision=predicted.decision,
            path=str(predicted_path),
        )
        return predicted_path


def output_root_from_config(config: AppConfig) -> Path:
    """Resolve the workflows preprocessed output root from config.

    :param config: Loaded application configuration.
    :return: Path to ``preprocessing.preprocessed_dir``.
    """
    return PreprocessingPipeline(config).output_root


def results_root_from_config(config: AppConfig) -> Path:
    """Resolve the pipeline results output root from config.

    :param config: Loaded application configuration.
    :return: Path to ``preprocessing.results_dir``.
    """
    return PreprocessingPipeline(config).results_root
