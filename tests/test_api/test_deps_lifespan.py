"""Lifespan DI tests for create_app (R021)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from api.app import create_app
from compliance.config.settings import AppConfig


def _deps() -> tuple[Any, Any, Any]:
    """Import Depends helpers; fail intentionally when deps are absent."""
    try:
        from api.deps import get_claims, get_config, get_preprocessing
    except ImportError as exc:
        pytest.fail(f"api.deps helpers not implemented: {exc}")
    return get_config, get_preprocessing, get_claims


def test_lifespan_exposes_pipelines_via_depends(
    tmp_path: Path,
    api_config_factory: Callable[..., AppConfig],
) -> None:
    """Lifespan yields PreprocessingPipeline and ClaimPipeline accessible via Depends."""
    _get_config, get_preprocessing, get_claims = _deps()

    data_dir = tmp_path / "raw"
    data_dir.mkdir()
    config = api_config_factory(data_dir)
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


def test_create_app_uses_injected_config_roots(
    tmp_path: Path,
    api_config_factory: Callable[..., AppConfig],
) -> None:
    """Depends get_config returns the injected AppConfig roots, not hardcoded defaults."""
    get_config, _get_preprocessing, _get_claims = _deps()

    data_dir = tmp_path / "injected-raw"
    preprocessed_dir = tmp_path / "injected-preprocessed"
    results_dir = tmp_path / "injected-results"
    data_dir.mkdir()
    config = api_config_factory(
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
