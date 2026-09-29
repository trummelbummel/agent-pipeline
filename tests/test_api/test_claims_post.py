"""POST /claims multipart intake tests (R017)."""

from __future__ import annotations

from collections.abc import Callable
from io import BytesIO
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from api.app import create_app
from compliance.config.settings import AppConfig


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


def test_post_claims_writes_raw_folder(
    tmp_path: Path,
    api_config_factory: Callable[..., AppConfig],
) -> None:
    """POST multipart writes description.txt, supporting_documents.md, and image under data_dir/{claim_id}."""
    data_dir = tmp_path / "raw"
    data_dir.mkdir()
    config = api_config_factory(data_dir)
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


def test_post_claims_rejects_disallowed_image_extension(
    tmp_path: Path,
    api_config_factory: Callable[..., AppConfig],
) -> None:
    """POST rejects image suffix not in config document_formats with 422."""
    data_dir = tmp_path / "raw"
    data_dir.mkdir()
    config = api_config_factory(data_dir)
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


def test_post_claims_conflict_when_folder_exists(
    tmp_path: Path,
    api_config_factory: Callable[..., AppConfig],
) -> None:
    """POST returns 409 when the next claim folder already exists."""
    from unittest.mock import patch

    data_dir = tmp_path / "raw"
    data_dir.mkdir()
    # Simulate TOCTOU: generated id already present when mkdir runs.
    (data_dir / "claim 1").mkdir()
    ((data_dir / "claim 1") / "keep.txt").write_text("original", encoding="utf-8")
    config = api_config_factory(data_dir)
    app = create_app(config=config)

    with patch("api.routes_claims._next_claim_id", return_value="claim 1"), TestClient(app) as client:
        response = client.post("/claims", files=_multipart_files())

    assert response.status_code == 409, response.text
    assert ((data_dir / "claim 1") / "keep.txt").read_text(encoding="utf-8") == "original"
    assert not ((data_dir / "claim 1") / "scan.png").exists()


def test_post_rejects_path_traversal_image_filename(
    tmp_path: Path,
    api_config_factory: Callable[..., AppConfig],
) -> None:
    """POST stores only basename for traversal-like filenames (or 422)."""
    import os

    data_dir = tmp_path / "raw"
    data_dir.mkdir()
    config = api_config_factory(data_dir)
    app = create_app(config=config)
    traversal_name = f"..{os.sep}..{os.sep}outside.png"

    with TestClient(app) as client:
        response = client.post(
            "/claims",
            files=_multipart_files(image_name=traversal_name),
        )

    # Accept either basename-only write (201) or early rejection (422).
    assert response.status_code in {201, 422}, response.text
    if response.status_code == 201:
        claim_id = response.json()["claim_id"]
        claim_dir = Path(config.preprocessing.data_dir) / claim_id
        written = list(claim_dir.iterdir())
        assert all(path.parent == claim_dir for path in written)
        assert (claim_dir / "outside.png").is_file()
        assert not (tmp_path / "outside.png").exists()
        assert (claim_dir / "outside.png").read_bytes() == b"png-bytes"


def test_generated_claim_id_always_safe_single_segment(
    tmp_path: Path,
    api_config_factory: Callable[..., AppConfig],
) -> None:
    """Generated claim_id is a single safe path segment starting with claim."""
    from compliance.preprocessing.claim_batch import _validate_claim_dir_name

    data_dir = tmp_path / "raw"
    data_dir.mkdir()
    (data_dir / "claim 7").mkdir()
    (data_dir / "claim 12").mkdir()
    config = api_config_factory(data_dir)
    app = create_app(config=config)

    with TestClient(app) as client:
        response = client.post("/claims", files=_multipart_files())

    assert response.status_code == 201, response.text
    claim_id = response.json()["claim_id"]
    assert claim_id.lower().startswith("claim")
    assert "/" not in claim_id
    assert "\\" not in claim_id
    _validate_claim_dir_name(claim_id)
    claim_dir = Path(config.preprocessing.data_dir) / claim_id
    assert claim_dir.parent == Path(config.preprocessing.data_dir)
    assert claim_dir.is_dir()
