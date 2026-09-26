"""GET /claims list tests (R019)."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from fastapi.testclient import TestClient

from api.app import create_app
from compliance.config.settings import AppConfig


def test_list_claims_empty_results_dir_returns_empty_list(
    tmp_path: Path,
    api_config_factory: Callable[..., AppConfig],
) -> None:
    """GET /claims with empty results_dir returns 200 and []."""
    data_dir = tmp_path / "raw"
    data_dir.mkdir()
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    config = api_config_factory(data_dir, results_dir=results_dir)
    app = create_app(config=config)

    with TestClient(app) as client:
        response = client.get("/claims")

    assert response.status_code == 200, response.text
    assert response.json() == []


def test_list_claims_includes_optional_artifacts_stable_order(
    tmp_path: Path,
    api_config_factory: Callable[..., AppConfig],
) -> None:
    """GET /claims lists results ordered by claim_id with optional artifacts."""
    data_dir = tmp_path / "raw"
    data_dir.mkdir()
    results_dir = tmp_path / "results"
    config = api_config_factory(data_dir, results_dir=results_dir)
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
