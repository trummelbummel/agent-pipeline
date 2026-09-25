"""GET /claims list tests (R019)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

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


def _analysis_config() -> AnalysisConfig:
    stage = ClassificationConfig(
        labels=["1", "2", "3"],
        other_label="None",
        model="test-model",
        prompt="classify",
    )
    return AnalysisConfig(
        coverage=stage,
        cancellation_reason=stage,
        cancellation_document=stage,
        personal_effects_document=stage,
        missed_departure_document=stage,
    )


def _config(
    data_dir: Path,
    *,
    preprocessed_dir: Path | str | None = None,
    results_dir: Path | str | None = None,
) -> AppConfig:
    """Build AppConfig with tmp roots for list tests.

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
            identity_prompt="identity",
            healthy_prompt="healthy",
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


def test_list_claims_empty_results_dir_returns_empty_list(tmp_path: Path) -> None:
    """GET /claims with empty results_dir returns 200 and []."""
    create_app = _create_app()
    data_dir = tmp_path / "raw"
    data_dir.mkdir()
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    config = _config(data_dir, results_dir=results_dir)
    app = create_app(config=config)

    with TestClient(app) as client:
        response = client.get("/claims")

    assert response.status_code == 200, response.text
    assert response.json() == []


def test_list_claims_includes_optional_artifacts_stable_order(tmp_path: Path) -> None:
    """GET /claims lists results ordered by claim_id with optional artifacts."""
    create_app = _create_app()
    data_dir = tmp_path / "raw"
    data_dir.mkdir()
    results_dir = tmp_path / "results"
    config = _config(data_dir, results_dir=results_dir)
    artifacts = config.preprocessing.artifacts

    claim_10 = results_dir / "claim 10"
    claim_10.mkdir(parents=True)
    (claim_10 / artifacts.predicted_answer).write_text(
        json.dumps({"decision": "DENY"}),
        encoding="utf-8",
    )
    (claim_10 / artifacts.analysis_result).write_text(
        json.dumps({"claim_id": "claim 10", "coverage_labels": ["1"]}),
        encoding="utf-8",
    )

    claim_2 = results_dir / "claim 2"
    claim_2.mkdir(parents=True)
    (claim_2 / artifacts.analysis_result).write_text(
        json.dumps({"claim_id": "claim 2", "coverage_labels": ["2"]}),
        encoding="utf-8",
    )

    app = create_app(config=config)

    with TestClient(app) as client:
        response = client.get("/claims")

    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body) == 2
    assert body[0]["claim_id"] == "claim 2"
    assert body[1]["claim_id"] == "claim 10"
    assert body[0]["analysis_result"]["coverage_labels"] == ["2"]
    assert body[0].get("predicted_answer") is None
    assert body[1]["predicted_answer"]["decision"] == "DENY"
    assert body[1]["analysis_result"]["claim_id"] == "claim 10"
