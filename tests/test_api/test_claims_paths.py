"""API path-boundary tests for claim roots (SR-009)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from api.app import create_app
from compliance.config.settings import AnalysisConfig, AppConfig


def _seed_raw_claim(data_dir: Path, claim_id: str = "claim 1") -> Path:
    claim_dir = data_dir / claim_id
    claim_dir.mkdir(parents=True)
    (claim_dir / "description.txt").write_text("cancel flight", encoding="utf-8")
    (claim_dir / "answer.json").write_text('{"decision": "APPROVE"}', encoding="utf-8")
    return claim_dir


def test_post_analysis_rejects_symlinked_claim_root(
    tmp_path: Path,
    api_config_factory: Callable[..., AppConfig],
    cancellation_analysis_config: AnalysisConfig,
    cancellation_chat_fn: MagicMock,
) -> None:
    """Symlinked claim root under data_dir returns 422 and never calls the LLM."""
    data_dir = tmp_path / "raw"
    data_dir.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("do-not-touch", encoding="utf-8")
    (data_dir / "claim 1").symlink_to(outside)
    config = api_config_factory(data_dir, analysis=cancellation_analysis_config)
    app = create_app(config=config, chat_fn=cancellation_chat_fn)

    with TestClient(app) as client:
        response = client.post("/claims/claim%201/analysis")

    assert response.status_code == 422, response.text
    cancellation_chat_fn.assert_not_called()
    assert (outside / "secret.txt").read_text(encoding="utf-8") == "do-not-touch"
    assert not list(outside.glob("*.json"))


def test_claim_endpoints_reject_traversal_claim_id(
    tmp_path: Path,
    api_config_factory: Callable[..., AppConfig],
    cancellation_analysis_config: AnalysisConfig,
    cancellation_chat_fn: MagicMock,
) -> None:
    """Percent-encoded traversal claim ids return 422 on GET and analysis POST."""
    data_dir = tmp_path / "raw"
    data_dir.mkdir()
    config = api_config_factory(data_dir, analysis=cancellation_analysis_config)
    app = create_app(config=config, chat_fn=cancellation_chat_fn)
    traversal = "%2E%2E"

    with TestClient(app) as client:
        get_response = client.get(f"/claims/{traversal}")
        post_response = client.post(f"/claims/{traversal}/analysis")

    assert get_response.status_code == 422, get_response.text
    assert post_response.status_code == 422, post_response.text
    cancellation_chat_fn.assert_not_called()
