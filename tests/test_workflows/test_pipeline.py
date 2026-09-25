from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from compliance.config.settings import (
    AppConfig,
    ClassificationConfig,
    ExtractionConfig,
    PreprocessingConfig,
)
from compliance.models.claim import BookingData, DocumentData
from compliance.preprocessing.description import DescriptionReader
from compliance.preprocessing.extractor import InformationExtractor
from compliance.workflows import process_claim_to_preprocessed


def _config(data_dir: Path) -> AppConfig:
    return AppConfig(
        preprocessing=PreprocessingConfig(
            data_dir=str(data_dir),
            output_filename="processed.json",
            document_formats=["webp", "jpg", "jpeg", "png", "pdf"],
            confidence_threshold=0.7,
            preprocessed_dir="preprocessed",
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


_EXPECTED_ARTIFACTS = (
    "description.txt",
    "answer.json",
    "supporting_document.json",
    "supporting_documents.md",
)


def test_process_claim_writes_four_artifacts(tmp_path: Path) -> None:
    claim = tmp_path / "claim 1"
    claim.mkdir()
    (claim / "answer.json").write_text('{"decision": "APPROVE"}', encoding="utf-8")
    letter = "I need a refund for my cancelled trip."
    (claim / "description.txt").write_text(letter, encoding="utf-8")
    (claim / "supporting1.md").write_text("**Name**: Ada Lovelace\n**Booking Ref**: R1", encoding="utf-8")
    (claim / "scan.png").write_bytes(b"png")

    output_root = tmp_path / "preprocessed_out"
    doc = DocumentData(person="Ada", raw_text="pass text", confidence=0.95, human_in_the_loop=False)

    claim_out = process_claim_to_preprocessed(
        claim,
        output_root,
        _config(tmp_path),
        description_reader=_mock_description_reader(),
        document_reader=_mock_document_reader({"scan.png": doc}),
    )

    assert claim_out == output_root / "claim 1"
    assert sorted(p.name for p in claim_out.iterdir() if p.is_file()) == sorted(_EXPECTED_ARTIFACTS)
    assert (claim_out / "description.txt").read_text(encoding="utf-8") == letter
    answer = json.loads((claim_out / "answer.json").read_text(encoding="utf-8"))
    assert answer["decision"] == "APPROVE"
    supporting_doc = json.loads((claim_out / "supporting_document.json").read_text(encoding="utf-8"))
    assert len(supporting_doc["documents"]) == 1
    md_body = (claim_out / "supporting_documents.md").read_text(encoding="utf-8")
    assert "Ada Lovelace" in md_body


def test_process_claim_missing_optionals_still_emits_four_files(tmp_path: Path) -> None:
    claim = tmp_path / "claim 99"
    claim.mkdir()
    (claim / "answer.json").write_text('{"decision": "DENY"}', encoding="utf-8")
    (claim / "description.txt").write_text("Please refund.", encoding="utf-8")

    output_root = tmp_path / "preprocessed_out"
    claim_out = process_claim_to_preprocessed(
        claim,
        output_root,
        _config(tmp_path),
        description_reader=_mock_description_reader(),
        document_reader=_mock_document_reader(),
    )

    for name in _EXPECTED_ARTIFACTS:
        assert (claim_out / name).is_file()
    supporting_doc = json.loads((claim_out / "supporting_document.json").read_text(encoding="utf-8"))
    assert supporting_doc["documents"] == []
    assert (claim_out / "supporting_documents.md").is_file()


def test_process_claim_refuses_unsafe_claim_dir_name(tmp_path: Path) -> None:
    output_root = tmp_path / "preprocessed_out"
    output_root.mkdir()
    before = set(output_root.iterdir())

    unsafe = tmp_path / "safe_claim"
    unsafe.mkdir()
    (unsafe / "answer.json").write_text('{"decision": "APPROVE"}', encoding="utf-8")
    (unsafe / "description.txt").write_text("x", encoding="utf-8")

    # Path.name is a single segment; forge an object whose .name embeds separators / ..
    class _UnsafeDir:
        name = f"..{os.sep}escape"

        def __truediv__(self, other: object) -> Path:
            raise AssertionError("should not join before validation")

    with pytest.raises(ValueError):
        process_claim_to_preprocessed(
            _UnsafeDir(),  # type: ignore[arg-type]
            output_root,
            _config(tmp_path),
            description_reader=_mock_description_reader(),
            document_reader=_mock_document_reader(),
        )

    assert set(output_root.iterdir()) == before
