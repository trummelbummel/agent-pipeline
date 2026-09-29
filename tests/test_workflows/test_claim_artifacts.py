from __future__ import annotations

import json
from pathlib import Path

from compliance.config.settings import PreprocessedArtifactNames
from compliance.workflows.claim_artifacts import ClaimArtifactReader


def _artifacts() -> PreprocessedArtifactNames:
    return PreprocessedArtifactNames()


def _seed_claim(claim_dir: Path, *, metadata: object | None = "default") -> ClaimArtifactReader:
    artifacts = _artifacts()
    claim_dir.mkdir(parents=True, exist_ok=True)
    (claim_dir / artifacts.description).write_text("desc", encoding="utf-8")
    (claim_dir / artifacts.supporting_document).write_text("doc", encoding="utf-8")
    if metadata == "default":
        payload = {
            "run_id": "pre-1",
            "documents": [
                {
                    "has_signature": True,
                    "human_in_the_loop": False,
                    "failure_reasons": [],
                }
            ],
        }
        (claim_dir / artifacts.document_metadata).write_text(
            json.dumps(payload),
            encoding="utf-8",
        )
    elif metadata is not None:
        (claim_dir / artifacts.document_metadata).write_text(
            json.dumps(metadata),
            encoding="utf-8",
        )
    return ClaimArtifactReader(claim_dir=claim_dir, artifacts=artifacts)


def test_texts_and_optional_supporting_documents(tmp_path: Path) -> None:
    """texts() reads required files and tolerates a missing supporting_documents."""
    reader = _seed_claim(tmp_path / "claim 1")
    texts = reader.texts()
    assert texts["description_text"] == "desc"
    assert texts["supporting_document_text"] == "doc"
    assert texts["supporting_documents_text"] == ""

    artifacts = _artifacts()
    (tmp_path / "claim 1" / artifacts.supporting_documents).write_text("booking", encoding="utf-8")
    assert reader.texts()["supporting_documents_text"] == "booking"


def test_signature_and_hitl_flags(tmp_path: Path) -> None:
    """has_signature / human_in_the_loop aggregate across metadata entries."""
    reader = _seed_claim(tmp_path / "claim 1")
    assert reader.has_signature() is True
    assert reader.human_in_the_loop() is False


def test_missing_metadata(tmp_path: Path) -> None:
    """Missing document_metadata.json yields empty flags and None provenance."""
    reader = _seed_claim(tmp_path / "claim 1", metadata=None)
    assert reader.has_signature() is False
    assert reader.human_in_the_loop() is False
    assert reader.ocr_failure_reason() is None
    assert reader.metadata_run_id() is None


def test_malformed_metadata(tmp_path: Path) -> None:
    """Non-dict metadata content is treated as missing."""
    reader = _seed_claim(tmp_path / "claim 1", metadata=["not", "a", "dict"])
    assert reader.metadata_run_id() is None
    assert reader.ocr_failure_reason() is None


def test_ocr_failure_precedence(tmp_path: Path) -> None:
    """ocr_read_failure beats ocr_failure when both appear."""
    reader = _seed_claim(
        tmp_path / "claim 1",
        metadata={
            "documents": [
                {"failure_reasons": ["ocr_failure", "ocr_read_failure"]},
            ],
        },
    )
    assert reader.ocr_failure_reason() == "ocr_read_failure"

    reader_only = _seed_claim(
        tmp_path / "claim 2",
        metadata={"documents": [{"failure_reasons": ["ocr_failure"]}]},
    )
    assert reader_only.ocr_failure_reason() == "ocr_failure"


def test_metadata_run_id(tmp_path: Path) -> None:
    """metadata_run_id returns the preprocess run_id string when present."""
    reader = _seed_claim(tmp_path / "claim 1")
    assert reader.metadata_run_id() == "pre-1"
