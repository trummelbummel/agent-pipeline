"""GET /claims/{claim_id} decision path tests (R018)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from api.app import create_app
from compliance.config.settings import (
    AnalysisConfig,
    AppConfig,
)

TRIP_CANCELLATION = "1"
MEDICAL_EMERGENCY = "2"
MEDICAL_CERTIFICATE = "1"

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


def test_get_claim_runs_process_then_analyze_returns_decision(
    tmp_path: Path,
    api_config_factory: Callable[..., AppConfig],
    cancellation_analysis_config: AnalysisConfig,
    cancellation_chat_fn: MagicMock,
) -> None:
    """GET /claims/{id} runs process_then_analyze and returns decision JSON."""
    data_dir = tmp_path / "raw"
    data_dir.mkdir()
    _seed_raw_claim(data_dir, "claim 1")
    config = api_config_factory(data_dir, analysis=cancellation_analysis_config)
    app = create_app(config=config, chat_fn=cancellation_chat_fn)

    with TestClient(app) as client:
        response = client.get("/claims/claim%201")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["claim_id"] == "claim 1"
    analysis = body["analysis_result"]
    assert isinstance(analysis, dict)
    assert analysis["coverage_labels"] == ["Trip cancellation or rescheduling"]
    assert analysis["coverage_label_codes"] == [TRIP_CANCELLATION]
    assert "reason_labels" in analysis
    assert "document_labels" in analysis
    assert "Medical emergency" in analysis["reason_labels"]
    assert "medical certificate" in analysis["document_labels"]
    analysis_path = (
        Path(config.preprocessing.results_dir)
        / "claim 1"
        / config.preprocessing.artifacts.analysis_result
    )
    assert analysis_path.is_file()


def test_get_claim_missing_raw_folder_returns_404(
    tmp_path: Path,
    api_config_factory: Callable[..., AppConfig],
    cancellation_analysis_config: AnalysisConfig,
    cancellation_chat_fn: MagicMock,
) -> None:
    """GET unknown claim_id returns 404 when raw folder is missing."""
    data_dir = tmp_path / "raw"
    data_dir.mkdir()
    config = api_config_factory(data_dir, analysis=cancellation_analysis_config)
    app = create_app(config=config, chat_fn=cancellation_chat_fn)

    with TestClient(app) as client:
        response = client.get("/claims/claim%2099")

    assert response.status_code == 404, response.text


def test_get_claim_unsafe_id_returns_422(
    tmp_path: Path,
    api_config_factory: Callable[..., AppConfig],
    cancellation_analysis_config: AnalysisConfig,
    cancellation_chat_fn: MagicMock,
) -> None:
    """GET with path-unsafe claim_id returns 422 before filesystem escape."""
    data_dir = tmp_path / "raw"
    data_dir.mkdir()
    config = api_config_factory(data_dir, analysis=cancellation_analysis_config)
    app = create_app(config=config, chat_fn=cancellation_chat_fn)

    with TestClient(app) as client:
        # Percent-encoded ".." so the segment reaches the route handler.
        response = client.get("/claims/%2E%2E")

    assert response.status_code == 422, response.text
