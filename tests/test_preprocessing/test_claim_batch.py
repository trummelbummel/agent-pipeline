from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from compliance.models.claim import DocumentData, DocumentMetaData, is_nan_scalar
from compliance.preprocessing.claim_batch import (
    _classify_files,
    _discover_claim_folders,
    _process_single_claim,
    run_pipeline,
)

if TYPE_CHECKING:
    from conftest import (
        MinimalAppConfigFactory,
        MockDescriptionReaderFactory,
        MockDocumentReaderFactory,
    )


def test_discover_claim_folders(tmp_path: Path) -> None:
    (tmp_path / "claim 2").mkdir()
    (tmp_path / "claim 10").mkdir()
    (tmp_path / "claim 1").mkdir()
    (tmp_path / "other").mkdir()

    folders = _discover_claim_folders(tmp_path)

    assert [p.name for p in folders] == ["claim 1", "claim 2", "claim 10"]


def test_classify_files(tmp_path: Path) -> None:
    claim = tmp_path / "claim 1"
    claim.mkdir()
    (claim / "answer.json").write_text('{"decision": "APPROVE"}', encoding="utf-8")
    (claim / "description.txt").write_text("hello", encoding="utf-8")
    (claim / "supporting1.md").write_text("**Name**: Ada", encoding="utf-8")
    (claim / "internal train data.md").write_text("**Name**: Bob", encoding="utf-8")
    (claim / "scan.webp").write_bytes(b"webp")
    (claim / "notes.txt").write_text("ignore", encoding="utf-8")

    sources = _classify_files(claim, ["webp", "jpg", "jpeg", "png", "pdf"])

    assert sources.answer_path.endswith("answer.json")
    assert sources.description_path.endswith("description.txt")
    assert len(sources.markdown_paths) == 2
    assert any(p.endswith("scan.webp") for p in sources.document_paths)
    assert not any(p.endswith("notes.txt") for p in sources.document_paths)


def test_process_single_claim_missing_optional_files(
    tmp_path: Path,
    minimal_app_config_factory: MinimalAppConfigFactory,
    mock_description_reader_factory: MockDescriptionReaderFactory,
    mock_document_reader_factory: MockDocumentReaderFactory,
) -> None:
    claim = tmp_path / "claim 99"
    claim.mkdir()
    (claim / "answer.json").write_text('{"decision": "DENY"}', encoding="utf-8")
    (claim / "description.txt").write_text("Please refund.", encoding="utf-8")

    bundle = _process_single_claim(
        claim,
        minimal_app_config_factory(tmp_path),
        description_reader=mock_description_reader_factory({"name": "Pat"}),
        document_reader=mock_document_reader_factory(),
    )

    assert bundle.claim_id == "claim 99"
    assert bundle.ground_truth.decision == "DENY"
    assert bundle.description_booking.name == "Pat"
    assert bundle.description_text == "Please refund."
    assert bundle.documents == []
    assert bundle.internal_data == []
    assert is_nan_scalar(bundle.booking_data.name)


def test_process_single_claim_with_markdown_and_document(
    tmp_path: Path,
    minimal_app_config_factory: MinimalAppConfigFactory,
    mock_description_reader_factory: MockDescriptionReaderFactory,
    mock_document_reader_factory: MockDocumentReaderFactory,
) -> None:
    claim = tmp_path / "claim 7"
    claim.mkdir()
    (claim / "answer.json").write_text('{"decision": "APPROVE"}', encoding="utf-8")
    (claim / "description.txt").write_text("letter", encoding="utf-8")
    (claim / "supporting1.md").write_text("**Name**: Ada\n**Booking Ref**: R1", encoding="utf-8")
    (claim / "internal flight data.md").write_text("**Name**: Internal", encoding="utf-8")
    (claim / "pass.png").write_bytes(b"png")

    doc = DocumentData(
        person="Ada",
        raw_text="pass",
        metadata=DocumentMetaData(extraction_probability=0.95),
    )
    bundle = _process_single_claim(
        claim,
        minimal_app_config_factory(tmp_path),
        description_reader=mock_description_reader_factory(),
        document_reader=mock_document_reader_factory({"pass.png": doc}),
    )

    assert bundle.booking_data.name == "Ada"
    assert bundle.booking_data.booking_ref == "R1"
    assert len(bundle.internal_data) == 1
    assert bundle.internal_data[0].name == "Internal"
    assert len(bundle.documents) == 1
    assert bundle.documents[0].person == "Ada"


def test_run_pipeline_returns_claim_bundles(
    tmp_path: Path,
    minimal_app_config_factory: MinimalAppConfigFactory,
    mock_description_reader_factory: MockDescriptionReaderFactory,
    mock_document_reader_factory: MockDocumentReaderFactory,
) -> None:
    claim = tmp_path / "claim 1"
    claim.mkdir()
    (claim / "answer.json").write_text('{"decision": "APPROVE"}', encoding="utf-8")
    (claim / "description.txt").write_text("hi", encoding="utf-8")

    bundles = run_pipeline(
        minimal_app_config_factory(tmp_path),
        description_reader=mock_description_reader_factory(),
        document_reader=mock_document_reader_factory(),
    )

    assert len(bundles) == 1
    assert bundles[0].claim_id == "claim 1"
    assert bundles[0].ground_truth.decision == "APPROVE"
    assert not (claim / "processed.json").exists()


def test_read_documents_skips_missing_file(tmp_path: Path) -> None:
    from unittest.mock import MagicMock

    from compliance.preprocessing.claim_batch import _read_documents

    missing = tmp_path / "gone.png"
    reader = MagicMock()
    docs = _read_documents([str(missing)], reader)

    assert docs == []
    reader.read.assert_not_called()


def test_read_documents_tags_ocr_read_failure_when_file_exists(
    tmp_path: Path,
) -> None:
    from unittest.mock import MagicMock

    from compliance.preprocessing.claim_batch import _read_documents

    present = tmp_path / "scan.png"
    present.write_bytes(b"png")
    reader = MagicMock()
    reader.read.side_effect = RuntimeError("docling crashed")
    docs = _read_documents([str(present)], reader)

    assert len(docs) == 1
    assert getattr(docs[0], "decision", None) == "UNCERTAIN"
    assert getattr(docs[0], "reason", None) == "ocr_read_failure"
    assert docs[0].metadata.human_in_the_loop is True
    assert "ocr_read_failure" in docs[0].metadata.failure_reasons
    reader.read.assert_called_once()
