from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import numpy as np

from compliance.config.settings import (
    AppConfig,
    ClassificationConfig,
    ExtractionConfig,
    PreprocessingConfig,
)
from compliance.models.claim import BookingData, ClaimBundle, DocumentData
from compliance.preprocessing.description import DescriptionReader
from compliance.preprocessing.extractor import InformationExtractor
from compliance.preprocessing.pipeline import (
    _classify_files,
    _discover_claim_folders,
    _process_single_claim,
    run_pipeline,
)


def _is_nan(value: object) -> bool:
    return isinstance(value, float) and np.isnan(value)


def _config(data_dir: Path) -> AppConfig:
    return AppConfig(
        preprocessing=PreprocessingConfig(
            data_dir=str(data_dir),
            output_filename="processed.json",
            document_formats=["webp", "jpg", "jpeg", "png", "pdf"],
            confidence_threshold=0.7,
        ),
        extraction=ExtractionConfig(model="test-model", prompt="extract fields"),
        classification=ClassificationConfig(
            labels=["Trip cancellation or rescheduling"],
            other_label="Other",
            model="test-model",
            prompt="classify",
        ),
    )


def _mock_description_reader(fields: dict[str, Any] | None = None) -> DescriptionReader:
    import json

    payload = fields or {}
    chat = MagicMock(
        return_value=SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))
    )
    extractor = InformationExtractor(
        target_model=BookingData,
        model_name="test-model",
        prompt="p",
        chat_fn=chat,
    )
    return DescriptionReader(extractor=extractor)


def _mock_document_reader(docs: dict[str, DocumentData] | None = None) -> MagicMock:
    mapping = docs or {}
    reader = MagicMock()

    def _read(path: Path) -> DocumentData:
        if path.name in mapping:
            return mapping[path.name]
        return DocumentData(raw_text="x", confidence=0.9, human_in_the_loop=False)

    reader.read.side_effect = _read
    return reader


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


def test_process_single_claim_missing_optional_files(tmp_path: Path) -> None:
    claim = tmp_path / "claim 99"
    claim.mkdir()
    (claim / "answer.json").write_text('{"decision": "DENY"}', encoding="utf-8")
    (claim / "description.txt").write_text("Please refund.", encoding="utf-8")

    bundle = _process_single_claim(
        claim,
        _config(tmp_path),
        description_reader=_mock_description_reader({"name": "Pat"}),
        document_reader=_mock_document_reader(),
    )

    assert bundle.claim_id == "claim 99"
    assert bundle.ground_truth.decision == "DENY"
    assert bundle.description_booking.name == "Pat"
    assert bundle.description_text == "Please refund."
    assert bundle.documents == []
    assert bundle.internal_data == []
    assert _is_nan(bundle.booking_data.name)


def test_process_single_claim_with_markdown_and_document(tmp_path: Path) -> None:
    claim = tmp_path / "claim 7"
    claim.mkdir()
    (claim / "answer.json").write_text('{"decision": "APPROVE"}', encoding="utf-8")
    (claim / "description.txt").write_text("letter", encoding="utf-8")
    (claim / "supporting1.md").write_text("**Name**: Ada\n**Booking Ref**: R1", encoding="utf-8")
    (claim / "internal flight data.md").write_text("**Name**: Internal", encoding="utf-8")
    (claim / "pass.png").write_bytes(b"png")

    doc = DocumentData(person="Ada", raw_text="pass", confidence=0.95, human_in_the_loop=False)
    bundle = _process_single_claim(
        claim,
        _config(tmp_path),
        description_reader=_mock_description_reader(),
        document_reader=_mock_document_reader({"pass.png": doc}),
    )

    assert bundle.booking_data.name == "Ada"
    assert bundle.booking_data.booking_ref == "R1"
    assert len(bundle.internal_data) == 1
    assert bundle.internal_data[0].name == "Internal"
    assert len(bundle.documents) == 1
    assert bundle.documents[0].person == "Ada"


def test_run_pipeline_writes_processed_json(tmp_path: Path) -> None:
    claim = tmp_path / "claim 1"
    claim.mkdir()
    (claim / "answer.json").write_text('{"decision": "APPROVE"}', encoding="utf-8")
    (claim / "description.txt").write_text("hi", encoding="utf-8")

    bundles = run_pipeline(
        _config(tmp_path),
        description_reader=_mock_description_reader(),
        document_reader=_mock_document_reader(),
    )

    assert len(bundles) == 1
    out = claim / "processed.json"
    assert out.is_file()
    reloaded = ClaimBundle.model_validate_json(out.read_text(encoding="utf-8"))
    assert reloaded.claim_id == "claim 1"
    assert reloaded.ground_truth.decision == "APPROVE"
