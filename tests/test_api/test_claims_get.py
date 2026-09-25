"""GET /claims/{claim_id} decision path tests (R018)."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from compliance.config.settings import (
    AnalysisConfig,
    AppConfig,
    CheckingConfig,
    ClassificationConfig,
    EvaluationConfig,
    ExtractionConfig,
    PreprocessingConfig,
)

TRIP_CANCELLATION = "1"
MEDICAL_EMERGENCY = "2"
MEDICAL_CERTIFICATE = "1"


def _analysis_config() -> AnalysisConfig:
    coverage = ClassificationConfig(
        labels=["1", "2", "3"],
        other_label="None",
        model="test-model",
        prompt="classify coverage",
    )
    cancellation_reason = ClassificationConfig(
        labels=["1", "2", "3", "4"],
        other_label="None",
        model="test-model",
        prompt="classify reason",
    )
    cancellation_document = ClassificationConfig(
        labels=["1", "2", "3"],
        other_label="None",
        model="test-model",
        prompt="classify cancel doc",
    )
    stage = ClassificationConfig(
        labels=["1"],
        other_label="None",
        model="test-model",
        prompt="classify",
    )
    return AnalysisConfig(
        coverage=coverage,
        cancellation_reason=cancellation_reason,
        cancellation_document=cancellation_document,
        personal_effects_document=stage,
        missed_departure_document=stage,
    )


def _config(
    data_dir: Path,
    *,
    preprocessed_dir: Path | str | None = None,
    results_dir: Path | str | None = None,
) -> AppConfig:
    """Build AppConfig with tmp roots for GET-by-id tests.

    :param data_dir: Temporary claim data root used as preprocessing.data_dir.
    :param preprocessed_dir: Optional preprocessed mirror root.
    :param results_dir: Optional analysis/results root.
    :return: Typed AppConfig suitable for unit tests without live Ollama.
    """
    return AppConfig(
        preprocessing=PreprocessingConfig(
            data_dir=str(data_dir),
            document_formats=["webp", "jpg", "jpeg", "png", "pdf"],
            confidence_threshold=0.7,
            preprocessed_dir=str(preprocessed_dir or data_dir / "preprocessed"),
            results_dir=str(results_dir or data_dir / "results"),
        ),
        extraction=ExtractionConfig(model="test-model", prompt="extract fields"),
        classification=ClassificationConfig(
            labels=["1", "2", "3"],
            other_label="Other",
            model="test-model",
            prompt="classify",
        ),
        checking=CheckingConfig(
            model="test-model",
            containment_prompt="containment",
            contradicts_prompt="contradicts",
        ),
        analysis=_analysis_config(),
        evaluation=EvaluationConfig(
            labels=["APPROVE", "DENY", "UNCERTAIN"],
            metrics_artifact="evaluation_metrics.json",
        ),
    )


def _create_app() -> Any:
    """Import create_app; fail intentionally when the factory is absent."""
    try:
        from api.app import create_app
    except ImportError as exc:
        pytest.fail(f"create_app not implemented: {exc}")
    return create_app


def _chat_response(payload: dict[str, Any]) -> SimpleNamespace:
    return SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))


def _cancellation_chat_fn() -> MagicMock:
    """coverage → reason → cancel-doc → containment LLM → contradicts."""
    coverage = _chat_response(
        {
            "labels": [TRIP_CANCELLATION],
            "probabilities": {TRIP_CANCELLATION: 0.9, "None": 0.1},
        }
    )
    reason = _chat_response(
        {
            "labels": [MEDICAL_EMERGENCY],
            "probabilities": {MEDICAL_EMERGENCY: 0.85, "None": 0.15},
        }
    )
    document = _chat_response(
        {
            "labels": [MEDICAL_CERTIFICATE],
            "probabilities": {MEDICAL_CERTIFICATE: 0.8, "None": 0.2},
        }
    )
    containment = _chat_response({"result": True})
    contradicts = _chat_response({"result": False})
    return MagicMock(
        side_effect=[coverage, reason, document, containment, contradicts]
    )


def _seed_raw_claim(data_dir: Path, claim_id: str = "claim 1") -> Path:
    """Write a minimal raw claim (no images) under data_dir.

    :param data_dir: Configured raw claims root.
    :param claim_id: Safe claim folder segment.
    :return: Path to the seeded claim directory.
    """
    claim_dir = data_dir / claim_id
    claim_dir.mkdir(parents=True)
    description = (
        "I had to cancel my flight to Paris because of a medical emergency."
    )
    (claim_dir / "description.txt").write_text(description, encoding="utf-8")
    (claim_dir / "answer.json").write_text(
        '{"decision": "APPROVE"}', encoding="utf-8"
    )
    return claim_dir


def test_get_claim_runs_process_then_analyze_returns_decision(tmp_path: Path) -> None:
    """GET /claims/{id} runs process_then_analyze and returns decision JSON."""
    create_app = _create_app()
    data_dir = tmp_path / "raw"
    data_dir.mkdir()
    _seed_raw_claim(data_dir, "claim 1")
    config = _config(data_dir)
    app = create_app(config=config, chat_fn=_cancellation_chat_fn())

    with TestClient(app) as client:
        response = client.get("/claims/claim%201")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["claim_id"] == "claim 1"
    analysis = body["analysis_result"]
    assert isinstance(analysis, dict)
    assert analysis["coverage_labels"] == [TRIP_CANCELLATION]
    assert "reason_labels" in analysis
    assert "document_labels" in analysis
    analysis_path = (
        Path(config.preprocessing.results_dir)
        / "claim 1"
        / config.preprocessing.artifacts.analysis_result
    )
    assert analysis_path.is_file()


def test_get_claim_missing_raw_folder_returns_404(tmp_path: Path) -> None:
    """GET unknown claim_id returns 404 when raw folder is missing."""
    create_app = _create_app()
    data_dir = tmp_path / "raw"
    data_dir.mkdir()
    config = _config(data_dir)
    app = create_app(config=config, chat_fn=_cancellation_chat_fn())

    with TestClient(app) as client:
        response = client.get("/claims/claim%2099")

    assert response.status_code == 404, response.text


def test_get_claim_unsafe_id_returns_422(tmp_path: Path) -> None:
    """GET with path-unsafe claim_id returns 422 before filesystem escape."""
    create_app = _create_app()
    data_dir = tmp_path / "raw"
    data_dir.mkdir()
    config = _config(data_dir)
    app = create_app(config=config, chat_fn=_cancellation_chat_fn())

    with TestClient(app) as client:
        # Percent-encoded ".." so the segment reaches the route handler.
        response = client.get("/claims/%2E%2E")

    assert response.status_code == 422, response.text
