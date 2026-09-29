"""POST /claims/{claim_id}/analysis tests (SR-007)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from api.app import create_app
from compliance.config.settings import AnalysisConfig, AppConfig

TRIP_CANCELLATION = "1"


def _seed_raw_claim(data_dir: Path, claim_id: str = "claim 1") -> Path:
    """Write a minimal raw claim (no images) under data_dir.

    :param data_dir: Configured raw claims root.
    :param claim_id: Safe claim folder segment.
    :return: Path to the seeded claim directory.
    """
    claim_dir = data_dir / claim_id
    claim_dir.mkdir(parents=True)
    description = "I had to cancel my flight to Paris because of a medical emergency."
    (claim_dir / "description.txt").write_text(description, encoding="utf-8")
    (claim_dir / "answer.json").write_text('{"decision": "APPROVE"}', encoding="utf-8")
    return claim_dir


def test_post_analysis_returns_decision_and_writes_artifact(
    tmp_path: Path,
    api_config_factory: Callable[..., AppConfig],
    cancellation_analysis_config: AnalysisConfig,
    cancellation_chat_fn: MagicMock,
) -> None:
    """POST /claims/{id}/analysis returns 200 with coverage labels and writes artifact."""
    data_dir = tmp_path / "raw"
    data_dir.mkdir()
    _seed_raw_claim(data_dir, "claim 1")
    config = api_config_factory(data_dir, analysis=cancellation_analysis_config)
    app = create_app(config=config, chat_fn=cancellation_chat_fn)

    with TestClient(app) as client:
        response = client.post("/claims/claim%201/analysis")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["claim_id"] == "claim 1"
    analysis = body["analysis_result"]
    assert analysis["coverage_labels"] == ["Trip cancellation or rescheduling"]
    assert analysis["coverage_label_codes"] == [TRIP_CANCELLATION]
    assert "Medical emergency" in analysis["reason_labels"]
    assert "medical certificate" in analysis["document_labels"]
    analysis_path = Path(config.preprocessing.results_dir) / "claim 1" / config.preprocessing.artifacts.analysis_result
    assert analysis_path.is_file()


def test_post_analysis_missing_raw_folder_returns_404_claim_not_found(
    tmp_path: Path,
    api_config_factory: Callable[..., AppConfig],
    cancellation_analysis_config: AnalysisConfig,
    cancellation_chat_fn: MagicMock,
) -> None:
    """POST analysis without a raw claim folder returns 404 claim_not_found."""
    data_dir = tmp_path / "raw"
    data_dir.mkdir()
    config = api_config_factory(data_dir, analysis=cancellation_analysis_config)
    app = create_app(config=config, chat_fn=cancellation_chat_fn)

    with TestClient(app) as client:
        response = client.post("/claims/claim%2099/analysis")

    assert response.status_code == 404, response.text
    assert response.json()["detail"] == "claim_not_found"


def test_post_analysis_unsafe_id_returns_422(
    tmp_path: Path,
    api_config_factory: Callable[..., AppConfig],
    cancellation_analysis_config: AnalysisConfig,
    cancellation_chat_fn: MagicMock,
) -> None:
    """POST analysis with path-unsafe claim_id returns 422."""
    data_dir = tmp_path / "raw"
    data_dir.mkdir()
    config = api_config_factory(data_dir, analysis=cancellation_analysis_config)
    app = create_app(config=config, chat_fn=cancellation_chat_fn)

    with TestClient(app) as client:
        # Percent-encoded ".." so the segment reaches the route handler.
        response = client.post("/claims/%2E%2E/analysis")

    assert response.status_code == 422, response.text


def test_post_analysis_lock_held_returns_409_in_progress(
    tmp_path: Path,
    api_config_factory: Callable[..., AppConfig],
    cancellation_analysis_config: AnalysisConfig,
    cancellation_chat_fn: MagicMock,
) -> None:
    """POST analysis while the per-claim lock is held returns 409 without LLM work."""
    data_dir = tmp_path / "raw"
    data_dir.mkdir()
    _seed_raw_claim(data_dir, "claim 1")
    config = api_config_factory(data_dir, analysis=cancellation_analysis_config)
    results_root = Path(config.preprocessing.results_dir)
    app = create_app(config=config, chat_fn=cancellation_chat_fn)
    analysis_path = results_root / "claim 1" / config.preprocessing.artifacts.analysis_result

    from compliance.workflows.artifact_publication import claim_analysis_lock

    with claim_analysis_lock(results_root, "claim 1"), TestClient(app) as client:
        response = client.post("/claims/claim%201/analysis")

    assert response.status_code == 409, response.text
    assert response.json()["detail"] == "analysis_in_progress"
    assert cancellation_chat_fn.call_count == 0
    assert not analysis_path.is_file()
