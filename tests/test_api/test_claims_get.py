"""GET /claims/{claim_id} read-only decision path tests (SR-007)."""

from __future__ import annotations

import json
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


def _tree_snapshot(base: Path, *roots: Path) -> dict[str, tuple[int, int]]:
    """Map relative paths under roots to (size, mtime_ns).

    :param base: Common ancestor used for relative keys.
    :param roots: Directory trees to snapshot (missing roots are skipped).
    :return: Relative-path → (byte size, mtime_ns) for every file found.
    """
    snapshot: dict[str, tuple[int, int]] = {}
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file():
                rel = str(path.relative_to(base))
                stat = path.stat()
                snapshot[rel] = (stat.st_size, stat.st_mtime_ns)
    return snapshot


def test_get_claim_reads_published_generation_unchanged(
    tmp_path: Path,
    api_config_factory: Callable[..., AppConfig],
    cancellation_analysis_config: AnalysisConfig,
    cancellation_chat_fn: MagicMock,
) -> None:
    """GET serves the published decision without writing or calling the LLM."""
    data_dir = tmp_path / "raw"
    data_dir.mkdir()
    _seed_raw_claim(data_dir, "claim 1")
    config = api_config_factory(data_dir, analysis=cancellation_analysis_config)
    app = create_app(config=config, chat_fn=cancellation_chat_fn)
    results_dir = Path(config.preprocessing.results_dir)
    preprocessed_dir = Path(config.preprocessing.preprocessed_dir)

    with TestClient(app) as client:
        posted = client.post("/claims/claim%201/analysis")
        assert posted.status_code == 200, posted.text
        chat_after_post = cancellation_chat_fn.call_count
        before = _tree_snapshot(tmp_path, data_dir, preprocessed_dir, results_dir)

        response = client.get("/claims/claim%201")

    assert response.status_code == 200, response.text
    assert response.json() == posted.json()
    assert _tree_snapshot(tmp_path, data_dir, preprocessed_dir, results_dir) == before
    assert cancellation_chat_fn.call_count == chat_after_post
    # POST left .locks/{claim}.lock (never unlinked — P-02); GET must not create .staging
    # and must not alter the lock tree (covered by the snapshot equality above).
    assert not (results_dir / ".staging").exists()
    assert (results_dir / ".locks").is_dir()


def test_get_claim_analysis_not_found_when_nothing_published(
    tmp_path: Path,
    api_config_factory: Callable[..., AppConfig],
    cancellation_analysis_config: AnalysisConfig,
    cancellation_chat_fn: MagicMock,
) -> None:
    """GET with raw inputs but no published analysis returns 404 analysis_not_found."""
    data_dir = tmp_path / "raw"
    data_dir.mkdir()
    _seed_raw_claim(data_dir, "claim 1")
    config = api_config_factory(data_dir, analysis=cancellation_analysis_config)
    app = create_app(config=config, chat_fn=cancellation_chat_fn)
    results_dir = Path(config.preprocessing.results_dir)

    with TestClient(app) as client:
        response = client.get("/claims/claim%201")

    assert response.status_code == 404, response.text
    assert response.json()["detail"] == "analysis_not_found"
    assert not results_dir.exists() or not any(results_dir.iterdir())


def test_get_claim_run_id_mismatch_returns_409(
    tmp_path: Path,
    api_config_factory: Callable[..., AppConfig],
    cancellation_analysis_config: AnalysisConfig,
    cancellation_chat_fn: MagicMock,
) -> None:
    """GET returns 409 run_id_mismatch when the artifact disagrees with the manifest."""
    data_dir = tmp_path / "raw"
    data_dir.mkdir()
    _seed_raw_claim(data_dir, "claim 1")
    config = api_config_factory(data_dir, analysis=cancellation_analysis_config)
    app = create_app(config=config, chat_fn=cancellation_chat_fn)
    artifacts = config.preprocessing.artifacts
    analysis_path = Path(config.preprocessing.results_dir) / "claim 1" / artifacts.analysis_result

    with TestClient(app) as client:
        posted = client.post("/claims/claim%201/analysis")
        assert posted.status_code == 200, posted.text
        payload = json.loads(analysis_path.read_text(encoding="utf-8"))
        payload["run_id"] = "superseded-run-id"
        analysis_path.write_text(json.dumps(payload), encoding="utf-8")

        response = client.get("/claims/claim%201")

    assert response.status_code == 409, response.text
    assert response.json()["detail"] == "run_id_mismatch"


def test_get_claim_invalid_json_returns_409(
    tmp_path: Path,
    api_config_factory: Callable[..., AppConfig],
    cancellation_analysis_config: AnalysisConfig,
    cancellation_chat_fn: MagicMock,
) -> None:
    """GET returns 409 invalid_json for an unparseable analysis artifact without a manifest."""
    data_dir = tmp_path / "raw"
    data_dir.mkdir()
    config = api_config_factory(data_dir, analysis=cancellation_analysis_config)
    app = create_app(config=config, chat_fn=cancellation_chat_fn)
    results_dir = Path(config.preprocessing.results_dir)
    claim_results = results_dir / "claim 1"
    claim_results.mkdir(parents=True)
    (claim_results / config.preprocessing.artifacts.analysis_result).write_text(
        "{not-json",
        encoding="utf-8",
    )

    with TestClient(app) as client:
        response = client.get("/claims/claim%201")

    assert response.status_code == 409, response.text
    assert response.json()["detail"] == "invalid_json"


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
