"""POST /claims multipart intake tests (R017)."""

from __future__ import annotations

from io import BytesIO
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

_XFAIL_LATER = pytest.mark.xfail(
    strict=False,
    reason="Wave 0 stub — path-safety edges in Task 3 (05-01)",
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
    """Build AppConfig with tmp roots for POST /claims tests.

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


def _multipart_files(
    *,
    image_name: str = "scan.png",
    image_bytes: bytes = b"png-bytes",
) -> dict[str, Any]:
    return {
        "description": ("description.txt", BytesIO(b"claim narrative"), "text/plain"),
        "supporting_documents": (
            "supporting_documents.md",
            BytesIO(b"# booking\n"),
            "text/markdown",
        ),
        "image": (image_name, BytesIO(image_bytes), "application/octet-stream"),
    }


def test_post_claims_writes_raw_folder(tmp_path: Path) -> None:
    """POST multipart writes description.txt, supporting_documents.md, and image under data_dir/{claim_id}."""
    create_app = _create_app()
    data_dir = tmp_path / "raw"
    data_dir.mkdir()
    config = _config(data_dir)
    artifacts = config.preprocessing.artifacts
    app = create_app(config=config)

    with TestClient(app) as client:
        response = client.post("/claims", files=_multipart_files())

    assert response.status_code == 201, response.text
    body = response.json()
    claim_id = body["claim_id"]
    assert claim_id.lower().startswith("claim")
    claim_dir = Path(config.preprocessing.data_dir) / claim_id
    assert claim_dir.is_dir()
    assert (claim_dir / artifacts.description).read_bytes() == b"claim narrative"
    assert (claim_dir / artifacts.supporting_documents).read_bytes() == b"# booking\n"
    assert (claim_dir / "scan.png").read_bytes() == b"png-bytes"


def test_post_claims_rejects_disallowed_image_extension(tmp_path: Path) -> None:
    """POST rejects image suffix not in config document_formats with 422."""
    create_app = _create_app()
    data_dir = tmp_path / "raw"
    data_dir.mkdir()
    config = _config(data_dir)
    app = create_app(config=config)
    before = {p.name for p in data_dir.iterdir()}

    with TestClient(app) as client:
        response = client.post(
            "/claims",
            files=_multipart_files(image_name="payload.exe"),
        )

    assert response.status_code == 422, response.text
    after = {p.name for p in data_dir.iterdir()}
    assert after == before


def test_post_claims_conflict_when_folder_exists(tmp_path: Path) -> None:
    """POST returns 409 when the next claim folder already exists."""
    from unittest.mock import patch

    create_app = _create_app()
    data_dir = tmp_path / "raw"
    data_dir.mkdir()
    # Simulate TOCTOU: generated id already present when mkdir runs.
    (data_dir / "claim 1").mkdir()
    ((data_dir / "claim 1") / "keep.txt").write_text("original", encoding="utf-8")
    config = _config(data_dir)
    app = create_app(config=config)

    with patch("api.routes_claims._next_claim_id", return_value="claim 1"):
        with TestClient(app) as client:
            response = client.post("/claims", files=_multipart_files())

    assert response.status_code == 409, response.text
    assert ((data_dir / "claim 1") / "keep.txt").read_text(encoding="utf-8") == "original"
    assert not ((data_dir / "claim 1") / "scan.png").exists()

@_XFAIL_LATER
def test_post_rejects_path_traversal_image_filename() -> None:
    """POST stores only basename for traversal-like filenames (or 422)."""
    raise NotImplementedError("Wave 0 stub — path-safety edges in Task 3")
