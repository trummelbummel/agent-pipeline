"""Tests for shared process_then_analyze orchestration (D-09 / R018)."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

from compliance.config.settings import (
    AnalysisConfig,
    AppConfig,
    CheckingConfig,
    ClassificationConfig,
    EvaluationConfig,
    ExtractionConfig,
    PreprocessingConfig,
)
from compliance.models.claim import BookingData, DocumentData, DocumentMetaData
from compliance.preprocessing.description import DescriptionReader
from compliance.preprocessing.extractor import InformationExtractor
from compliance.workflows.claim_pipeline import ClaimPipeline
from compliance.workflows.pipeline import PreprocessingPipeline

TRIP_CANCELLATION = "1"
MEDICAL_EMERGENCY = "2"
MEDICAL_CERTIFICATE = "1"


def _analysis_config() -> AnalysisConfig:
    coverage = ClassificationConfig(
        labels=["1", "2", "3"],
        other_label="False",
        model="test-model",
        prompt="classify coverage",
        label_names={
            "1": "Trip cancellation or rescheduling",
            "2": "Personal Effects",
            "3": "Missed Departure or Missed Connection",
        },
    )
    cancellation_reason = ClassificationConfig(
        labels=["1", "2", "3", "4"],
        other_label="False",
        model="test-model",
        prompt="classify reason",
        label_names={
            "1": "Jury duty",
            "2": "Medical emergency",
            "3": "Theft or criminal incident",
            "4": "Other specified personal emergencies",
        },
    )
    cancellation_document = ClassificationConfig(
        labels=["1", "2", "3"],
        other_label="False",
        model="test-model",
        prompt="classify cancel doc",
        label_names={
            "1": "medical certificate",
            "2": "police report",
            "3": "jury summon letter",
        },
    )
    stage = ClassificationConfig(
        labels=["1"],
        other_label="False",
        model="test-model",
        prompt="classify",
        label_names={"1": "Proof of theft, loss, or damage"},
    )
    return AnalysisConfig(
        coverage=coverage,
        cancellation_reason=cancellation_reason,
        cancellation_document=cancellation_document,
        personal_effects_document=stage,
        missed_departure_document=stage,
    )


def _config(tmp_path: Path) -> AppConfig:
    """Build AppConfig with tmp roots for orchestration tests.

    :param tmp_path: Pytest temporary directory root.
    :return: Typed AppConfig suitable for unit tests without live Ollama.
    """
    data_dir = tmp_path / "raw"
    data_dir.mkdir()
    return AppConfig(
        preprocessing=PreprocessingConfig(
            data_dir=str(data_dir),
            document_formats=["webp", "jpg", "jpeg", "png", "pdf"],
            confidence_threshold=0.7,
            preprocessed_dir=str(tmp_path / "preprocessed"),
            results_dir=str(tmp_path / "results"),
        ),
        extraction=ExtractionConfig(model="test-model", prompt="extract fields"),
        classification=ClassificationConfig(
            labels=["1", "2", "3"],
            other_label="False",
            model="test-model",
            prompt="classify",
        ),
        checking=CheckingConfig(
            model="test-model",
            containment_prompt="containment",
            contradicts_prompt="contradicts",
            identity_prompt="identity",
            healthy_prompt="healthy",
            authenticity_prompt="authenticity",
            incomplete_prompt="incomplete",
        ),
        analysis=_analysis_config(),
        evaluation=EvaluationConfig(
            labels=["APPROVE", "DENY", "UNCERTAIN"],
            metrics_artifact="evaluation_metrics.json",
        ),
    )


def _chat_response(payload: dict[str, Any]) -> SimpleNamespace:
    return SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))


def _cancellation_chat_fn() -> MagicMock:
    """Injected chat_fn: coverage → reason → cancel-doc → checker contradicts."""
    coverage = _chat_response(
        {
            "labels": [TRIP_CANCELLATION],
            "probabilities": {TRIP_CANCELLATION: 0.9, "False": 0.1},
        }
    )
    reason = _chat_response(
        {
            "labels": [MEDICAL_EMERGENCY],
            "probabilities": {MEDICAL_EMERGENCY: 0.85, "False": 0.15},
        }
    )
    document = _chat_response(
        {
            "labels": [MEDICAL_CERTIFICATE],
            "probabilities": {MEDICAL_CERTIFICATE: 0.8, "False": 0.2},
        }
    )
    contradicts = _chat_response({"result": False})
    identity = _chat_response({"result": True})
    healthy = _chat_response({"result": False})
    return MagicMock(side_effect=[coverage, reason, document, contradicts, identity, healthy])


def _mock_description_reader() -> DescriptionReader:
    chat = MagicMock(
        return_value=SimpleNamespace(message=SimpleNamespace(content=json.dumps({})))
    )
    extractor = InformationExtractor(
        target_model=BookingData,
        model_name="test-model",
        prompt="p",
        chat_fn=chat,
    )
    return DescriptionReader(extractor=extractor)


def _mock_document_reader() -> MagicMock:
    reader = MagicMock()
    description = (
        "I had to cancel my flight to Paris because of a medical emergency."
    )
    reader.read.side_effect = lambda path: DocumentData(
        raw_text=description,
        metadata=DocumentMetaData(extraction_probability=0.95),
    )
    return reader


def test_process_then_analyze_calls_process_then_analyze_order(tmp_path: Path) -> None:
    """process_then_analyze writes preprocessed artifacts then analysis_result."""
    from compliance.workflows import process_then_analyze

    config = _config(tmp_path)
    claim_dir = Path(config.preprocessing.data_dir) / "claim 1"
    claim_dir.mkdir()
    description = (
        "I had to cancel my flight to Paris because of a medical emergency."
    )
    (claim_dir / "answer.json").write_text(
        '{"decision": "APPROVE"}', encoding="utf-8"
    )
    (claim_dir / "description.txt").write_text(description, encoding="utf-8")
    (claim_dir / "scan.png").write_bytes(b"png")

    preprocessing = PreprocessingPipeline(
        config,
        description_reader=_mock_description_reader(),
        document_reader=_mock_document_reader(),
    )
    claims = ClaimPipeline(config, chat_fn=_cancellation_chat_fn())

    analysis_path = process_then_analyze(claim_dir, preprocessing, claims)

    artifacts = config.preprocessing.artifacts
    preprocessed = Path(config.preprocessing.preprocessed_dir) / "claim 1"
    assert (preprocessed / artifacts.description).is_file()
    assert analysis_path.is_file()
    assert analysis_path == (
        Path(config.preprocessing.results_dir)
        / "claim 1"
        / artifacts.analysis_result
    )
    payload = json.loads(analysis_path.read_text(encoding="utf-8"))
    assert payload["claim_id"] == "claim 1"
    assert payload["coverage_labels"] == ["Trip cancellation or rescheduling"]
    assert payload["coverage_label_codes"] == [TRIP_CANCELLATION]
    assert "reason_labels" in payload
    assert "document_labels" in payload
    assert "Medical emergency" in payload["reason_labels"]
    assert "medical certificate" in payload["document_labels"]
