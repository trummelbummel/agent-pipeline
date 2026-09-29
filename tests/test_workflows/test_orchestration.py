"""Tests for shared process_then_analyze orchestration (D-09 / R018)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

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
    claim_dir.mkdir()

    description = "I had to cancel my flight to Paris because of a medical emergency."
    (claim_dir / "answer.json").write_text('{"decision": "APPROVE"}', encoding="utf-8")
    (claim_dir / "description.txt").write_text(description, encoding="utf-8")
    (claim_dir / "scan.png").write_bytes(b"png")

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
