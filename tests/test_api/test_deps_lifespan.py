"""Lifespan DI tests for create_app (R021)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi import Request
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
    """Build AppConfig with tmp roots for API lifespan tests.

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


def _deps() -> tuple[Any, Any, Any]:
    """Import Depends helpers; fail intentionally when deps are absent."""
    try:
        from api.deps import get_claims, get_config, get_preprocessing
    except ImportError as exc:
        pytest.fail(f"api.deps helpers not implemented: {exc}")
    return get_config, get_preprocessing, get_claims


def test_lifespan_exposes_pipelines_via_depends(tmp_path: Path) -> None:
    """Lifespan yields PreprocessingPipeline and ClaimPipeline accessible via Depends."""
    create_app = _create_app()
    _get_config, get_preprocessing, get_claims = _deps()

    data_dir = tmp_path / "raw"
    data_dir.mkdir()
    config = _config(data_dir)
    app = create_app(config=config)

    @app.get("/_probe")
    def _probe(request: Request) -> dict[str, int]:
        return {
            "prep_id": id(get_preprocessing(request)),
            "claims_id": id(get_claims(request)),
        }

    with TestClient(app) as client:
        first = client.get("/_probe")
        second = client.get("/_probe")

    assert first.status_code == 200, first.text
    assert second.status_code == 200
    assert first.json()["prep_id"] == second.json()["prep_id"]
    assert first.json()["claims_id"] == second.json()["claims_id"]
    assert first.json()["prep_id"] != 0
    assert first.json()["claims_id"] != 0


def test_create_app_uses_injected_config_roots(tmp_path: Path) -> None:
    """Depends get_config returns the injected AppConfig roots, not hardcoded defaults."""
    create_app = _create_app()
    get_config, _get_preprocessing, _get_claims = _deps()

    data_dir = tmp_path / "injected-raw"
    preprocessed_dir = tmp_path / "injected-preprocessed"
    results_dir = tmp_path / "injected-results"
    data_dir.mkdir()
    config = _config(
        data_dir,
        preprocessed_dir=preprocessed_dir,
        results_dir=results_dir,
    )
    app = create_app(config=config)

    @app.get("/_config_probe")
    def _config_probe(request: Request) -> dict[str, str]:
        cfg = get_config(request)
        return {
            "data_dir": cfg.preprocessing.data_dir,
            "preprocessed_dir": cfg.preprocessing.preprocessed_dir,
            "results_dir": cfg.preprocessing.results_dir,
        }

    with TestClient(app) as client:
        response = client.get("/_config_probe")

    assert response.status_code == 200
    body = response.json()
    assert body["data_dir"] == str(data_dir)
    assert body["preprocessed_dir"] == str(preprocessed_dir)
    assert body["results_dir"] == str(results_dir)
