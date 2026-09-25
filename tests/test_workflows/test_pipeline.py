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
from compliance.models.claim import BookingData, DocumentData, DocumentMetaData, GroundTruth
from compliance.preprocessing.description import DescriptionReader
from compliance.preprocessing.extractor import InformationExtractor
from compliance.workflows import (
    PreprocessingPipeline,
    output_root_from_config,
    results_root_from_config,
)
from main import main


def _config(
    data_dir: Path,
    *,
    preprocessed_dir: Path | str = "data/preprocessed",
    results_dir: Path | str = "data/results",
) -> AppConfig:
    return AppConfig(
        preprocessing=PreprocessingConfig(
            data_dir=str(data_dir),
            document_formats=["webp", "jpg", "jpeg", "png", "pdf"],
            confidence_threshold=0.7,
            preprocessed_dir=str(preprocessed_dir),
            results_dir=str(results_dir),
        ),
        extraction=ExtractionConfig(model="test-model", prompt="extract fields"),
        classification=ClassificationConfig(
            labels=["Trip cancellation or rescheduling"],
            other_label="Other",
            model="test-model",
            prompt="classify",
        ),
    )


def _expected_artifacts(config: AppConfig) -> tuple[str, ...]:
    names = config.preprocessing.artifacts
    return (
        names.description,
        names.answer,
        names.supporting_document,
        names.supporting_documents,
        names.document_metadata,
    )


def _seed_minimal_claim(claim_dir: Path, *, decision: str = "APPROVE") -> None:
    claim_dir.mkdir(parents=True, exist_ok=True)
    (claim_dir / "answer.json").write_text(
        json.dumps({"decision": decision}),
        encoding="utf-8",
    )
    (claim_dir / "description.txt").write_text("Please refund.", encoding="utf-8")


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
        return DocumentData(
            raw_text="x",
            metadata=DocumentMetaData(extraction_probability=0.9),
        )

    reader.read.side_effect = _read
    return reader


def test_output_root_from_config_matches_preprocessing_dir(tmp_path: Path) -> None:
    config = _config(tmp_path)
    assert output_root_from_config(config) == Path(config.preprocessing.preprocessed_dir)
    assert PreprocessingPipeline(config).output_root == Path(config.preprocessing.preprocessed_dir)
    assert results_root_from_config(config) == Path(config.preprocessing.results_dir)
    assert PreprocessingPipeline(config).results_root == Path(config.preprocessing.results_dir)


def test_process_claim_writes_predicted_answer_on_fraud_deny(tmp_path: Path) -> None:
    claim = tmp_path / "claim 7"
    claim.mkdir()
    (claim / "answer.json").write_text('{"decision": "APPROVE"}', encoding="utf-8")
    (claim / "description.txt").write_text("Please refund.", encoding="utf-8")
    (claim / "scan.png").write_bytes(b"png")

    fraud_doc = DocumentData.model_validate(
        {
            "decision": "DENY",
            "reason": "fraud",
            "fields": {
                "decision": "DENY",
                "reason": "fraud",
                "benford_chi_squared": 99.5,
                "benford_conformity": False,
            },
        }
    )
    output_root = tmp_path / "preprocessed_out"
    results_root = tmp_path / "results_out"
    config = _config(tmp_path, results_dir=results_root)
    claim_out = PreprocessingPipeline(
        config,
        description_reader=_mock_description_reader(),
        document_reader=_mock_document_reader({"scan.png": fraud_doc}),
    ).process_claim(claim, output_root)

    predicted_path = results_root / "claim 7" / config.preprocessing.artifacts.predicted_answer
    assert predicted_path.is_file()
    assert not (claim_out / config.preprocessing.artifacts.predicted_answer).exists()
    predicted = json.loads(predicted_path.read_text(encoding="utf-8"))
    assert predicted["decision"] == "DENY"
    assert "fraud" in predicted["explanation"]
    # Ground truth answer.json stays separate from the prediction
    answer = json.loads(
        (claim_out / config.preprocessing.artifacts.answer).read_text(encoding="utf-8")
    )
    assert answer["decision"] == "APPROVE"


def test_process_claim_skips_predicted_answer_without_pipeline_decision(tmp_path: Path) -> None:
    claim = tmp_path / "claim 8"
    claim.mkdir()
    (claim / "answer.json").write_text('{"decision": "APPROVE"}', encoding="utf-8")
    (claim / "description.txt").write_text("Please refund.", encoding="utf-8")
    (claim / "scan.png").write_bytes(b"png")

    output_root = tmp_path / "preprocessed_out"
    results_root = tmp_path / "results_out"
    config = _config(tmp_path, results_dir=results_root)
    claim_out = PreprocessingPipeline(
        config,
        description_reader=_mock_description_reader(),
        document_reader=_mock_document_reader(
            {"scan.png": DocumentData(raw_text="ok", metadata=DocumentMetaData(extraction_probability=0.9))}
        ),
    ).process_claim(claim, output_root)

    assert not (claim_out / config.preprocessing.artifacts.predicted_answer).exists()
    assert not (results_root / "claim 8" / config.preprocessing.artifacts.predicted_answer).exists()


def test_process_claim_writes_four_artifacts(tmp_path: Path) -> None:
    claim = tmp_path / "claim 1"
    claim.mkdir()
    (claim / "answer.json").write_text('{"decision": "APPROVE"}', encoding="utf-8")
    letter = "I need a refund for my cancelled trip."
    (claim / "description.txt").write_text(letter, encoding="utf-8")
    (claim / "supporting1.md").write_text("**Name**: Ada Lovelace\n**Booking Ref**: R1", encoding="utf-8")
    (claim / "scan.png").write_bytes(b"png")

    output_root = tmp_path / "preprocessed_out"
    doc = DocumentData(
        person="Ada",
        raw_text="pass text",
        metadata=DocumentMetaData(extraction_probability=0.95),
    )
    config = _config(tmp_path)
    expected = _expected_artifacts(config)

    claim_out = PreprocessingPipeline(
        config,
        description_reader=_mock_description_reader(),
        document_reader=_mock_document_reader({"scan.png": doc}),
    ).process_claim(claim, output_root)

    assert claim_out == output_root / "claim 1"
    written = sorted(p.name for p in claim_out.iterdir() if p.is_file())
    assert written == sorted([*expected, "scan.png"])
    assert (claim_out / "scan.png").read_bytes() == b"png"
    assert (claim_out / config.preprocessing.artifacts.description).read_text(encoding="utf-8") == letter
    answer = json.loads(
        (claim_out / config.preprocessing.artifacts.answer).read_text(encoding="utf-8")
    )
    assert answer["decision"] == "APPROVE"
    supporting_doc = (
        claim_out / config.preprocessing.artifacts.supporting_document
    ).read_text(encoding="utf-8")
    assert "## Document: 1" in supporting_doc
    assert "pass text" in supporting_doc
    md_body = (claim_out / config.preprocessing.artifacts.supporting_documents).read_text(
        encoding="utf-8"
    )
    assert "Ada Lovelace" in md_body
    assert "pass text" not in md_body


def test_process_claim_writes_webp_as_png(tmp_path: Path) -> None:
    from PIL import Image

    claim = tmp_path / "claim 17"
    claim.mkdir()
    (claim / "answer.json").write_text('{"decision": "APPROVE"}', encoding="utf-8")
    (claim / "description.txt").write_text("Please refund.", encoding="utf-8")
    webp = claim / "Spanish_medical_16.webp"
    Image.new("RGB", (8, 8), color=(10, 20, 30)).save(webp, format="WEBP")

    output_root = tmp_path / "preprocessed_out"
    config = _config(tmp_path)
    claim_out = PreprocessingPipeline(
        config,
        description_reader=_mock_description_reader(),
        document_reader=_mock_document_reader(
            {
                "Spanish_medical_16.webp": DocumentData(
                    raw_text="cert",
                    metadata=DocumentMetaData(extraction_probability=0.9),
                )
            }
        ),
    ).process_claim(claim, output_root)

    png_path = claim_out / "Spanish_medical_16.png"
    assert png_path.is_file()
    assert not (claim_out / "Spanish_medical_16.webp").exists()
    with Image.open(png_path) as image:
        assert image.format == "PNG"


def test_process_claim_missing_optionals_still_emits_four_files(tmp_path: Path) -> None:
    claim = tmp_path / "claim 99"
    claim.mkdir()
    (claim / "answer.json").write_text('{"decision": "DENY"}', encoding="utf-8")
    (claim / "description.txt").write_text("Please refund.", encoding="utf-8")

    output_root = tmp_path / "preprocessed_out"
    config = _config(tmp_path)
    claim_out = PreprocessingPipeline(
        config,
        description_reader=_mock_description_reader(),
        document_reader=_mock_document_reader(),
    ).process_claim(claim, output_root)

    for name in _expected_artifacts(config):
        assert (claim_out / name).is_file()
    supporting_doc = (
        claim_out / config.preprocessing.artifacts.supporting_document
    ).read_text(encoding="utf-8")
    assert "_none_" in supporting_doc
    assert (claim_out / config.preprocessing.artifacts.supporting_documents).is_file()
    metadata = json.loads(
        (claim_out / config.preprocessing.artifacts.document_metadata).read_text(encoding="utf-8")
    )
    assert metadata["documents"][0]["faulty_extraction"] is True
    assert metadata["documents"][0]["human_in_the_loop"] is True


def test_process_claim_refuses_unsafe_claim_dir_name(tmp_path: Path) -> None:
    output_root = tmp_path / "preprocessed_out"
    output_root.mkdir()
    before = set(output_root.iterdir())

    unsafe = tmp_path / "safe_claim"
    unsafe.mkdir()
    (unsafe / "answer.json").write_text('{"decision": "APPROVE"}', encoding="utf-8")
    (unsafe / "description.txt").write_text("x", encoding="utf-8")

    class _UnsafeDir:
        name = f"..{os.sep}escape"

        def __truediv__(self, other: object) -> Path:
            raise AssertionError("should not join before validation")

    with pytest.raises(ValueError):
        PreprocessingPipeline(
            _config(tmp_path),
            description_reader=_mock_description_reader(),
            document_reader=_mock_document_reader(),
        ).process_claim(
            _UnsafeDir(),  # type: ignore[arg-type]
            output_root,
        )

    assert set(output_root.iterdir()) == before


def test_run_preprocessing_workflow_mirrors_all_claims(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    output_root = tmp_path / "preprocessed_out"
    _seed_minimal_claim(data_dir / "claim 1")
    _seed_minimal_claim(data_dir / "claim 2", decision="DENY")
    config = _config(data_dir, preprocessed_dir=output_root)
    expected = _expected_artifacts(config)

    written = PreprocessingPipeline(
        config,
        description_reader=_mock_description_reader(),
        document_reader=_mock_document_reader(),
    ).run()

    assert sorted(p.name for p in written) == ["claim 1", "claim 2"]
    for claim_name in ("claim 1", "claim 2"):
        claim_out = output_root / claim_name
        assert claim_out.is_dir()
        assert sorted(p.name for p in claim_out.iterdir() if p.is_file()) == sorted(expected)


def test_run_preprocessing_workflow_soft_fails_one_claim(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    output_root = tmp_path / "preprocessed_out"
    _seed_minimal_claim(data_dir / "claim 1")
    _seed_minimal_claim(data_dir / "claim 2", decision="DENY")

    answer_reader = MagicMock()

    def _read_answer(path: Path) -> GroundTruth:
        if path.parent.name == "claim 2":
            raise RuntimeError("simulated claim failure")
        return GroundTruth(decision="APPROVE")

    answer_reader.read.side_effect = _read_answer
    config = _config(data_dir, preprocessed_dir=output_root)

    written = PreprocessingPipeline(
        config,
        answer_reader=answer_reader,
        description_reader=_mock_description_reader(),
        document_reader=_mock_document_reader(),
    ).run()

    assert any(p.name == "claim 1" for p in written)
    assert all(p.name != "claim 2" for p in written)
    assert (output_root / "claim 1").is_dir()
    claim2_out = output_root / "claim 2"
    if claim2_out.exists():
        present = {p.name for p in claim2_out.iterdir() if p.is_file()}
        assert present != set(_expected_artifacts(config))


def test_main_runs_workflow_with_injected_config_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_dir = tmp_path / "data"
    output_root = tmp_path / "preprocessed_out"
    data_dir.mkdir()
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(
        "\n".join(
            [
                "preprocessing:",
                f"  data_dir: {data_dir}",
                "  document_formats: [webp, jpg, jpeg, png, pdf]",
                "  confidence_threshold: 0.7",
                f"  preprocessed_dir: {output_root}",
                f"  results_dir: {tmp_path / 'results_out'}",
                "  artifacts:",
                "    description: description.txt",
                "    answer: answer.json",
                "    supporting_document: supporting_document.md",
                "    supporting_documents: supporting_documents.md",
                "    document_metadata: document_metadata.json",
                "extraction:",
                "  model: test-model",
                "  prompt: extract",
                "classification:",
                "  labels: [Trip cancellation or rescheduling]",
                "  other_label: Other",
                "  model: test-model",
                "  prompt: classify",
                "checking:",
                "  model: test-model",
                "  containment_prompt: check containment",
                "  contradicts_prompt: check contradicts",
                "ocr_retry:",
                "  enabled: false",
                "  model: test-vision",
                "  prompt: ocr",
                "",
            ]
        ),
        encoding="utf-8",
    )

    captured: dict[str, Any] = {}

    def _fake_run(self: PreprocessingPipeline) -> list[Path]:
        captured["data_dir"] = self._config.preprocessing.data_dir
        captured["preprocessed_dir"] = self._config.preprocessing.preprocessed_dir
        return []

    monkeypatch.setattr(PreprocessingPipeline, "run", _fake_run)

    assert main(["--config", str(cfg_path)]) == 0
    assert captured["data_dir"] == str(data_dir)
    assert captured["preprocessed_dir"] == str(output_root)


def test_main_returns_2_when_config_missing(tmp_path: Path) -> None:
    missing = tmp_path / "no-such-config.yaml"
    assert main(["--config", str(missing)]) == 2
