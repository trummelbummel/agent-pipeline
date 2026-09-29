"""GET /claims list tests (R019 / SR-007)."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from fastapi.testclient import TestClient

from api.app import create_app
from compliance.config.settings import AppConfig
from compliance.workflows.artifact_publication import publish_claim_generation


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
    assert body[0].get("errors") is None
    assert body[1]["predicted_answer"]["decision"] == "DENY"
    assert body[1]["analysis_result"]["claim_id"] == "claim 10"
    assert body[1].get("errors") is None


def test_list_claims_unparseable_artifact_reports_invalid_json(
    tmp_path: Path,
    api_config_factory: Callable[..., AppConfig],
) -> None:
    """One unparseable analysis artifact stays listed with invalid_json; others intact."""
    data_dir = tmp_path / "raw"
    data_dir.mkdir()
    results_dir = tmp_path / "results"
    config = api_config_factory(data_dir, results_dir=results_dir)
    artifacts = config.preprocessing.artifacts

    good = results_dir / "claim 1"
    good.mkdir(parents=True)
    (good / artifacts.analysis_result).write_text(
        json.dumps({"claim_id": "claim 1", "coverage_labels": ["1"]}),
        encoding="utf-8",
    )

    bad = results_dir / "claim 2"
    bad.mkdir(parents=True)
    (bad / artifacts.analysis_result).write_text("{not-json", encoding="utf-8")

    app = create_app(config=config)

    with TestClient(app) as client:
        response = client.get("/claims")

    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body) == 2
    by_id = {item["claim_id"]: item for item in body}
    assert by_id["claim 1"]["analysis_result"]["coverage_labels"] == ["1"]
    assert by_id["claim 1"].get("errors") is None
    assert by_id["claim 2"]["analysis_result"] is None
    assert by_id["claim 2"]["errors"] == {artifacts.analysis_result: "invalid_json"}


def test_list_claims_run_id_mismatch_reports_errors(
    tmp_path: Path,
    api_config_factory: Callable[..., AppConfig],
) -> None:
    """A published claim whose artifact disagrees with its manifest reports run_id_mismatch."""
    data_dir = tmp_path / "raw"
    data_dir.mkdir()
    results_dir = tmp_path / "results"
    config = api_config_factory(data_dir, results_dir=results_dir)
    artifacts = config.preprocessing.artifacts
    run_id = "20260929T120000-abcd1234"

    publish_claim_generation(
        results_root=results_dir,
        claim_id="claim 1",
        run_id=run_id,
        bodies={
            artifacts.analysis_result: json.dumps({"run_id": run_id, "claim_id": "claim 1"}) + "\n",
            artifacts.predicted_answer: json.dumps({"run_id": run_id, "decision": "APPROVE"}) + "\n",
        },
        manifest_name=artifacts.run_manifest,
        source="analysis",
    )
    analysis_path = results_dir / "claim 1" / artifacts.analysis_result
    payload = json.loads(analysis_path.read_text(encoding="utf-8"))
    payload["run_id"] = "superseded-run-id"
    analysis_path.write_text(json.dumps(payload), encoding="utf-8")

    clean = results_dir / "claim 2"
    clean.mkdir(parents=True)
    (clean / artifacts.analysis_result).write_text(
        json.dumps({"claim_id": "claim 2", "coverage_labels": ["2"]}),
        encoding="utf-8",
    )

    app = create_app(config=config)

    with TestClient(app) as client:
        response = client.get("/claims")

    assert response.status_code == 200, response.text
    body = response.json()
    by_id = {item["claim_id"]: item for item in body}
    assert by_id["claim 1"]["analysis_result"] is None
    assert by_id["claim 1"]["errors"][artifacts.analysis_result] == "run_id_mismatch"
    assert by_id["claim 2"]["analysis_result"]["coverage_labels"] == ["2"]
    assert by_id["claim 2"].get("errors") is None
