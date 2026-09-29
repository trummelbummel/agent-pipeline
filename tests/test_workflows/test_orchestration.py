"""Tests for shared process_then_analyze orchestration (D-09 / R018 / SR-007)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from conftest import build_minimal_app_config

from compliance.config.settings import AnalysisConfig, ClassificationConfig
from compliance.models.claim import DocumentData, DocumentMetaData
from compliance.workflows.claim_pipeline import ClaimPipeline
from compliance.workflows.pipeline import PreprocessingPipeline

if TYPE_CHECKING:
    from conftest import (
        CancellationChatFactory,
        MockDescriptionReaderFactory,
        MockDocumentReaderFactory,
    )

TRIP_CANCELLATION = "1"

_ORCH_CLASSIFICATION = ClassificationConfig(
    labels=["1", "2", "3"],
    other_label="False",
    model="test-model",
    prompt="classify",
)


def _config(tmp_path: Path, analysis: AnalysisConfig):
    """Build AppConfig with tmp roots for orchestration tests.

    :param tmp_path: Pytest temporary directory root.
    :param analysis: Shared labeled cancellation analysis stages.
    :return: Typed AppConfig suitable for unit tests without live Ollama.
    """
    data_dir = tmp_path / "raw"
    data_dir.mkdir()
    return build_minimal_app_config(
        data_dir,
        preprocessed_dir=tmp_path / "preprocessed",
        results_dir=tmp_path / "results",
        analysis=analysis,
        classification=_ORCH_CLASSIFICATION,
    )


def _seed_claim(claim_dir: Path, description: str) -> None:
    """Write minimal raw claim files into an existing directory.

    :param claim_dir: Destination claim folder.
    :param description: Narrative text for description.txt.
    """
    claim_dir.mkdir(parents=True, exist_ok=True)
    (claim_dir / "answer.json").write_text('{"decision": "APPROVE"}', encoding="utf-8")
    (claim_dir / "description.txt").write_text(description, encoding="utf-8")
    (claim_dir / "scan.png").write_bytes(b"png")


def _pipelines(
    config,
    *,
    cancellation_chat_factory: CancellationChatFactory,
    mock_description_reader_factory: MockDescriptionReaderFactory,
    mock_document_reader_factory: MockDocumentReaderFactory,
    description: str,
) -> tuple[PreprocessingPipeline, ClaimPipeline]:
    """Build preprocessing and claim pipelines for orchestration tests.

    :param config: AppConfig with tmp roots.
    :param cancellation_chat_factory: Shared chat mock factory.
    :param mock_description_reader_factory: Description reader factory.
    :param mock_document_reader_factory: Document reader factory.
    :param description: Narrative text returned by the document reader.
    :return: (preprocessing, claims) pipeline pair.
    """
    preprocessing = PreprocessingPipeline(
        config,
        description_reader=mock_description_reader_factory(),
        document_reader=mock_document_reader_factory(
            default=DocumentData(
                raw_text=description,
                metadata=DocumentMetaData(extraction_probability=0.95),
            )
        ),
    )
    claims = ClaimPipeline(
        config,
        chat_fn=cancellation_chat_factory([
            {"result": False},
            {"name": "Ada Lovelace"},
            {"name": "Ada Lovelace"},
            {"result": False},
            {"result": False},
            {"result": False},
        ]),
    )
    return preprocessing, claims


def test_process_then_analyze_calls_process_then_analyze_order(
    tmp_path: Path,
    cancellation_analysis_config: AnalysisConfig,
    cancellation_chat_factory: CancellationChatFactory,
    mock_description_reader_factory: MockDescriptionReaderFactory,
    mock_document_reader_factory: MockDocumentReaderFactory,
) -> None:
    """process_then_analyze writes preprocessed artifacts then analysis_result."""
    from compliance.workflows.orchestration import process_then_analyze

    config = _config(tmp_path, cancellation_analysis_config)
    claim_dir = Path(config.preprocessing.data_dir) / "claim 1"
    description = "I had to cancel my flight to Paris because of a medical emergency."
    _seed_claim(claim_dir, description)
    preprocessing, claims = _pipelines(
        config,
        cancellation_chat_factory=cancellation_chat_factory,
        mock_description_reader_factory=mock_description_reader_factory,
        mock_document_reader_factory=mock_document_reader_factory,
        description=description,
    )

    analysis_path = process_then_analyze(claim_dir, preprocessing, claims)

    artifacts = config.preprocessing.artifacts
    preprocessed = Path(config.preprocessing.preprocessed_dir) / "claim 1"
    assert (preprocessed / artifacts.description).is_file()
    assert analysis_path.is_file()
    assert analysis_path == (Path(config.preprocessing.results_dir) / "claim 1" / artifacts.analysis_result)
    payload = json.loads(analysis_path.read_text(encoding="utf-8"))
    assert payload["claim_id"] == "claim 1"
    assert payload["coverage_labels"] == ["Trip cancellation or rescheduling"]
    assert payload["coverage_label_codes"] == [TRIP_CANCELLATION]
    assert "Medical emergency" in payload["reason_labels"]
    assert "medical certificate" in payload["document_labels"]


def test_analyze_claim_exclusively_publishes_consistent_generation(
    tmp_path: Path,
    cancellation_analysis_config: AnalysisConfig,
    cancellation_chat_factory: CancellationChatFactory,
    mock_description_reader_factory: MockDescriptionReaderFactory,
    mock_document_reader_factory: MockDocumentReaderFactory,
) -> None:
    """analyze_claim_exclusively publishes a generation with matching run_ids."""
    from compliance.workflows.orchestration import analyze_claim_exclusively

    config = _config(tmp_path, cancellation_analysis_config)
    claim_dir = Path(config.preprocessing.data_dir) / "claim 1"
    description = "I had to cancel my flight to Paris because of a medical emergency."
    _seed_claim(claim_dir, description)
    preprocessing, claims = _pipelines(
        config,
        cancellation_chat_factory=cancellation_chat_factory,
        mock_description_reader_factory=mock_description_reader_factory,
        mock_document_reader_factory=mock_document_reader_factory,
        description=description,
    )

    analysis_path = analyze_claim_exclusively(claim_dir, preprocessing, claims)

    artifacts = config.preprocessing.artifacts
    claim_results = Path(config.preprocessing.results_dir) / "claim 1"
    assert analysis_path == claim_results / artifacts.analysis_result
    manifest = json.loads((claim_results / artifacts.run_manifest).read_text(encoding="utf-8"))
    analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
    predicted = json.loads((claim_results / artifacts.predicted_answer).read_text(encoding="utf-8"))
    assert manifest["run_id"] == analysis["run_id"] == predicted["run_id"]


def test_claim_analysis_lock_conflicts_within_one_process(tmp_path: Path) -> None:
    """Two independent acquisitions of the same claim lock conflict; release frees it."""
    from compliance.workflows.artifact_publication import (
        ClaimAnalysisBusyError,
        claim_analysis_lock,
    )

    results_root = tmp_path / "results"
    with claim_analysis_lock(results_root, "claim 1"):
        with pytest.raises(ClaimAnalysisBusyError) as exc_info, claim_analysis_lock(results_root, "claim 1"):
            pass
        assert exc_info.value.claim_id == "claim 1"
    with claim_analysis_lock(results_root, "claim 1"):
        pass


def test_analyze_claim_exclusively_raises_when_lock_held(
    tmp_path: Path,
    cancellation_analysis_config: AnalysisConfig,
    cancellation_chat_factory: CancellationChatFactory,
    mock_description_reader_factory: MockDescriptionReaderFactory,
    mock_document_reader_factory: MockDocumentReaderFactory,
) -> None:
    """Exclusive orchestrator raises ClaimAnalysisBusyError when the lock is held."""
    from compliance.workflows.artifact_publication import (
        ClaimAnalysisBusyError,
        claim_analysis_lock,
    )
    from compliance.workflows.orchestration import analyze_claim_exclusively

    config = _config(tmp_path, cancellation_analysis_config)
    claim_dir = Path(config.preprocessing.data_dir) / "claim 1"
    description = "I had to cancel my flight to Paris because of a medical emergency."
    _seed_claim(claim_dir, description)
    preprocessing, claims = _pipelines(
        config,
        cancellation_chat_factory=cancellation_chat_factory,
        mock_description_reader_factory=mock_description_reader_factory,
        mock_document_reader_factory=mock_document_reader_factory,
        description=description,
    )
    results_root = Path(config.preprocessing.results_dir)
    artifacts = config.preprocessing.artifacts

    with claim_analysis_lock(results_root, "claim 1"):
        with pytest.raises(ClaimAnalysisBusyError) as exc_info:
            analyze_claim_exclusively(claim_dir, preprocessing, claims)
        assert exc_info.value.claim_id == "claim 1"

    assert not (results_root / "claim 1" / artifacts.analysis_result).is_file()
