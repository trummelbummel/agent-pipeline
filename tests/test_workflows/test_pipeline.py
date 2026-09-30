from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock

import pytest

from compliance.config.settings import AppConfig
from compliance.models.claim import DocumentData, DocumentMetaData, GroundTruth
from compliance.workflows import (
    PreprocessingPipeline,
    output_root_from_config,
    results_root_from_config,
)
from main import main

if TYPE_CHECKING:
    from conftest import (
        MinimalAppConfigFactory,
        MockDescriptionReaderFactory,
        MockDocumentReaderFactory,
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


def test_output_root_from_config_matches_preprocessing_dir(
    tmp_path: Path,
    minimal_app_config_factory: MinimalAppConfigFactory,
) -> None:
    config = minimal_app_config_factory(tmp_path)
    assert output_root_from_config(config) == Path(config.preprocessing.preprocessed_dir)
    assert PreprocessingPipeline(config).output_root == Path(config.preprocessing.preprocessed_dir)
    assert results_root_from_config(config) == Path(config.preprocessing.results_dir)
    assert PreprocessingPipeline(config).results_root == Path(config.preprocessing.results_dir)


def test_process_claim_writes_predicted_answer_on_fraud_deny(
    tmp_path: Path,
    minimal_app_config_factory: MinimalAppConfigFactory,
    mock_description_reader_factory: MockDescriptionReaderFactory,
    mock_document_reader_factory: MockDocumentReaderFactory,
) -> None:
    claim = tmp_path / "claim 7"
    claim.mkdir()
    (claim / "answer.json").write_text('{"decision": "APPROVE"}', encoding="utf-8")
    (claim / "description.txt").write_text("Please refund.", encoding="utf-8")
    (claim / "scan.png").write_bytes(b"png")

    fraud_doc = DocumentData.model_validate({
        "decision": "DENY",
        "reason": "fraud",
        "fields": {
            "decision": "DENY",
            "reason": "fraud",
            "benford_chi_squared": 99.5,
            "benford_conformity": False,
        },
    })
    output_root = tmp_path / "preprocessed_out"
    results_root = tmp_path / "results_out"
    config = minimal_app_config_factory(tmp_path, results_dir=results_root)
    claim_out = PreprocessingPipeline(
        config,
        description_reader=mock_description_reader_factory(),
        document_reader=mock_document_reader_factory({"scan.png": fraud_doc}),
    ).process_claim(claim, output_root)

    predicted_path = results_root / "claim 7" / config.preprocessing.artifacts.predicted_answer
    assert predicted_path.is_file()
    assert not (claim_out / config.preprocessing.artifacts.predicted_answer).exists()
    predicted = json.loads(predicted_path.read_text(encoding="utf-8"))
    assert predicted["decision"] == "DENY"
    assert "fraud" in predicted["explanation"]
    assert predicted["source"] == "preprocess"
    # Ground truth answer.json stays separate from the prediction
    answer = json.loads((claim_out / config.preprocessing.artifacts.answer).read_text(encoding="utf-8"))
    assert answer["decision"] == "APPROVE"


def test_preprocess_prediction_publishes_generation(
    tmp_path: Path,
    minimal_app_config_factory: MinimalAppConfigFactory,
    mock_description_reader_factory: MockDescriptionReaderFactory,
    mock_document_reader_factory: MockDocumentReaderFactory,
) -> None:
    """Preprocess prediction publishes under run_id; older analysis_result stays readable."""
    from compliance.workflows.artifact_publication import generation_mismatch

    claim = tmp_path / "claim 7"
    claim.mkdir()
    (claim / "answer.json").write_text('{"decision": "APPROVE"}', encoding="utf-8")
    (claim / "description.txt").write_text("Please refund.", encoding="utf-8")
    (claim / "scan.png").write_bytes(b"png")

    fraud_doc = DocumentData.model_validate({
        "decision": "DENY",
        "reason": "fraud",
        "fields": {
            "decision": "DENY",
            "reason": "fraud",
            "benford_chi_squared": 99.5,
            "benford_conformity": False,
        },
    })
    output_root = tmp_path / "preprocessed_out"
    results_root = tmp_path / "results_out"
    results_claim = results_root / "claim 7"
    results_claim.mkdir(parents=True)
    old_run = "20260929T100000-oldgen01"
    (results_claim / "analysis_result.json").write_text(
        json.dumps({"run_id": old_run, "decision": "APPROVE"}, indent=2) + "\n",
        encoding="utf-8",
    )
    (results_claim / "predicted_answer.json").write_text(
        json.dumps({"run_id": old_run, "decision": "APPROVE", "source": "analysis"}, indent=2) + "\n",
        encoding="utf-8",
    )
    (results_claim / "run_manifest.json").write_text(
        json.dumps(
            {
                "run_id": old_run,
                "published_at": "2026-09-29T10:00:00Z",
                "source": "analysis",
                "artifacts": ["analysis_result.json", "predicted_answer.json"],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    config = minimal_app_config_factory(tmp_path, results_dir=results_root)
    PreprocessingPipeline(
        config,
        description_reader=mock_description_reader_factory(),
        document_reader=mock_document_reader_factory({"scan.png": fraud_doc}),
    ).process_claim(claim, output_root)

    artifacts = config.preprocessing.artifacts
    manifest = json.loads((results_claim / artifacts.run_manifest).read_text(encoding="utf-8"))
    predicted = json.loads((results_claim / artifacts.predicted_answer).read_text(encoding="utf-8"))
    assert manifest["artifacts"] == [artifacts.predicted_answer]
    assert predicted["run_id"] == manifest["run_id"]
    assert predicted["source"] == "preprocess"
    analysis = json.loads((results_claim / artifacts.analysis_result).read_text(encoding="utf-8"))
    assert analysis["run_id"] == old_run
    assert generation_mismatch(results_claim, artifacts.analysis_result, artifacts.run_manifest) == "run_id_mismatch"
    assert not (results_root / ".staging").exists()


def test_process_claim_skips_predicted_answer_without_pipeline_decision(
    tmp_path: Path,
    minimal_app_config_factory: MinimalAppConfigFactory,
    mock_description_reader_factory: MockDescriptionReaderFactory,
    mock_document_reader_factory: MockDocumentReaderFactory,
) -> None:
    claim = tmp_path / "claim 8"
    claim.mkdir()
    (claim / "answer.json").write_text('{"decision": "APPROVE"}', encoding="utf-8")
    (claim / "description.txt").write_text("Please refund.", encoding="utf-8")
    (claim / "scan.png").write_bytes(b"png")

    output_root = tmp_path / "preprocessed_out"
    results_root = tmp_path / "results_out"
    stale = results_root / "claim 8"
    stale.mkdir(parents=True)
    (stale / "predicted_answer.json").write_text(
        '{"decision":"DENY","explanation":"fraud (benford chi_squared=1.0)"}',
        encoding="utf-8",
    )
    config = minimal_app_config_factory(tmp_path, results_dir=results_root)
    claim_out = PreprocessingPipeline(
        config,
        description_reader=mock_description_reader_factory(),
        document_reader=mock_document_reader_factory({
            "scan.png": DocumentData(raw_text="ok", metadata=DocumentMetaData(extraction_probability=0.9))
        }),
    ).process_claim(claim, output_root)

    assert not (claim_out / config.preprocessing.artifacts.predicted_answer).exists()
    assert not (results_root / "claim 8" / config.preprocessing.artifacts.predicted_answer).exists()


def test_process_claim_preserves_analysis_predicted_answer_without_decision(
    tmp_path: Path,
    minimal_app_config_factory: MinimalAppConfigFactory,
    mock_description_reader_factory: MockDescriptionReaderFactory,
    mock_document_reader_factory: MockDocumentReaderFactory,
) -> None:
    claim = tmp_path / "claim 9"
    claim.mkdir()
    (claim / "answer.json").write_text('{"decision": "APPROVE"}', encoding="utf-8")
    (claim / "description.txt").write_text("Please refund.", encoding="utf-8")
    (claim / "scan.png").write_bytes(b"png")

    output_root = tmp_path / "preprocessed_out"
    results_root = tmp_path / "results_out"
    results_claim = results_root / "claim 9"
    results_claim.mkdir(parents=True)
    predicted_name = "predicted_answer.json"
    predicted_payload = {
        "decision": "APPROVE",
        "explanation": "checker_consistent",
        "source": "analysis",
    }
    (results_claim / predicted_name).write_text(
        json.dumps(predicted_payload),
        encoding="utf-8",
    )
    (results_claim / "analysis_result.json").write_text(
        json.dumps({"decision": "APPROVE"}),
        encoding="utf-8",
    )
    config = minimal_app_config_factory(tmp_path, results_dir=results_root)
    PreprocessingPipeline(
        config,
        description_reader=mock_description_reader_factory(),
        document_reader=mock_document_reader_factory({
            "scan.png": DocumentData(
                raw_text="ok",
                metadata=DocumentMetaData(extraction_probability=0.9),
            )
        }),
    ).process_claim(claim, output_root)

    predicted_path = results_claim / config.preprocessing.artifacts.predicted_answer
    assert predicted_path.is_file()
    preserved = json.loads(predicted_path.read_text(encoding="utf-8"))
    assert preserved["decision"] == "APPROVE"
    assert preserved["source"] == "analysis"


def test_process_claim_writes_four_artifacts(
    tmp_path: Path,
    minimal_app_config_factory: MinimalAppConfigFactory,
    mock_description_reader_factory: MockDescriptionReaderFactory,
    mock_document_reader_factory: MockDocumentReaderFactory,
) -> None:
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
    config = minimal_app_config_factory(tmp_path)
    expected = _expected_artifacts(config)

    claim_out = PreprocessingPipeline(
        config,
        description_reader=mock_description_reader_factory(),
        document_reader=mock_document_reader_factory({"scan.png": doc}),
    ).process_claim(claim, output_root)

    assert claim_out == output_root / "claim 1"
    written = sorted(p.name for p in claim_out.iterdir() if p.is_file())
    assert written == sorted([*expected, "scan.png"])
    assert (claim_out / "scan.png").read_bytes() == b"png"
    assert (claim_out / config.preprocessing.artifacts.description).read_text(encoding="utf-8") == letter
    answer = json.loads((claim_out / config.preprocessing.artifacts.answer).read_text(encoding="utf-8"))
    assert answer["decision"] == "APPROVE"
    supporting_doc = (claim_out / config.preprocessing.artifacts.supporting_document).read_text(encoding="utf-8")
    assert "## Document: 1" in supporting_doc
    assert "pass text" in supporting_doc
    md_body = (claim_out / config.preprocessing.artifacts.supporting_documents).read_text(encoding="utf-8")
    assert "Ada Lovelace" in md_body
    assert "pass text" not in md_body


def test_process_claim_writes_webp_as_png(
    tmp_path: Path,
    minimal_app_config_factory: MinimalAppConfigFactory,
    mock_description_reader_factory: MockDescriptionReaderFactory,
    mock_document_reader_factory: MockDocumentReaderFactory,
) -> None:
    from PIL import Image

    claim = tmp_path / "claim 17"
    claim.mkdir()
    (claim / "answer.json").write_text('{"decision": "APPROVE"}', encoding="utf-8")
    (claim / "description.txt").write_text("Please refund.", encoding="utf-8")
    webp = claim / "Spanish_medical_16.webp"
    Image.new("RGB", (8, 8), color=(10, 20, 30)).save(webp, format="WEBP")

    output_root = tmp_path / "preprocessed_out"
    config = minimal_app_config_factory(tmp_path)
    claim_out = PreprocessingPipeline(
        config,
        description_reader=mock_description_reader_factory(),
        document_reader=mock_document_reader_factory({
            "Spanish_medical_16.webp": DocumentData(
                raw_text="cert",
                metadata=DocumentMetaData(extraction_probability=0.9),
            )
        }),
    ).process_claim(claim, output_root)

    png_path = claim_out / "Spanish_medical_16.png"
    assert png_path.is_file()
    assert not (claim_out / "Spanish_medical_16.webp").exists()
    with Image.open(png_path) as image:
        assert image.format == "PNG"


def test_process_claim_missing_optionals_still_emits_four_files(
    tmp_path: Path,
    minimal_app_config_factory: MinimalAppConfigFactory,
    mock_description_reader_factory: MockDescriptionReaderFactory,
    mock_document_reader_factory: MockDocumentReaderFactory,
) -> None:
    claim = tmp_path / "claim 99"
    claim.mkdir()
    (claim / "answer.json").write_text('{"decision": "DENY"}', encoding="utf-8")
    (claim / "description.txt").write_text("Please refund.", encoding="utf-8")

    output_root = tmp_path / "preprocessed_out"
    config = minimal_app_config_factory(tmp_path)
    claim_out = PreprocessingPipeline(
        config,
        description_reader=mock_description_reader_factory(),
        document_reader=mock_document_reader_factory(),
    ).process_claim(claim, output_root)

    for name in _expected_artifacts(config):
        assert (claim_out / name).is_file()
    supporting_doc = (claim_out / config.preprocessing.artifacts.supporting_document).read_text(encoding="utf-8")
    assert "_none_" in supporting_doc
    assert (claim_out / config.preprocessing.artifacts.supporting_documents).is_file()
    metadata = json.loads((claim_out / config.preprocessing.artifacts.document_metadata).read_text(encoding="utf-8"))
    assert metadata["documents"][0]["faulty_extraction"] is True
    assert metadata["documents"][0]["human_in_the_loop"] is True
    assert isinstance(metadata.get("run_id"), str) and metadata["run_id"]


def test_process_claim_refuses_unsafe_claim_dir_name(
    tmp_path: Path,
    minimal_app_config_factory: MinimalAppConfigFactory,
    mock_description_reader_factory: MockDescriptionReaderFactory,
    mock_document_reader_factory: MockDocumentReaderFactory,
) -> None:
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
            pytest.fail("should not join before validation")

    with pytest.raises(ValueError):
        PreprocessingPipeline(
            minimal_app_config_factory(tmp_path),
            description_reader=mock_description_reader_factory(),
            document_reader=mock_document_reader_factory(),
        ).process_claim(
            _UnsafeDir(),  # type: ignore[arg-type]
            output_root,
        )

    assert set(output_root.iterdir()) == before


def test_run_preprocessing_workflow_mirrors_all_claims(
    tmp_path: Path,
    minimal_app_config_factory: MinimalAppConfigFactory,
    mock_description_reader_factory: MockDescriptionReaderFactory,
    mock_document_reader_factory: MockDocumentReaderFactory,
) -> None:
    data_dir = tmp_path / "data"
    output_root = tmp_path / "preprocessed_out"
    _seed_minimal_claim(data_dir / "claim 1")
    _seed_minimal_claim(data_dir / "claim 2", decision="DENY")
    config = minimal_app_config_factory(data_dir, preprocessed_dir=output_root)
    expected = _expected_artifacts(config)

    written = PreprocessingPipeline(
        config,
        description_reader=mock_description_reader_factory(),
        document_reader=mock_document_reader_factory(),
    ).run()

    assert sorted(p.name for p in written) == ["claim 1", "claim 2"]
    for claim_name in ("claim 1", "claim 2"):
        claim_out = output_root / claim_name
        assert claim_out.is_dir()
        assert sorted(p.name for p in claim_out.iterdir() if p.is_file()) == sorted(expected)


def test_preprocessing_pipeline_builds_document_reader_once(
    tmp_path: Path,
    minimal_app_config_factory: MinimalAppConfigFactory,
    mock_description_reader_factory: MockDescriptionReaderFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PreprocessingPipeline constructs DocumentReader.from_config once at init (GO-004)."""
    data_dir = tmp_path / "data"
    output_root = tmp_path / "preprocessed_out"
    _seed_minimal_claim(data_dir / "claim 1")
    _seed_minimal_claim(data_dir / "claim 2", decision="DENY")
    config = minimal_app_config_factory(data_dir, preprocessed_dir=output_root)

    mock_reader = MagicMock()
    mock_reader.read.return_value = DocumentData(
        raw_text="x",
        metadata=DocumentMetaData(extraction_probability=0.9),
    )
    calls: list[int] = []

    @classmethod
    def _fake_from_config(cls: type, *args: object, **kwargs: object) -> MagicMock:
        calls.append(1)
        return mock_reader

    monkeypatch.setattr(
        "compliance.preprocessing.claim_batch.DocumentReader.from_config",
        _fake_from_config,
    )

    written = PreprocessingPipeline(
        config,
        description_reader=mock_description_reader_factory(),
    ).run()

    assert sorted(p.name for p in written) == ["claim 1", "claim 2"]
    assert len(calls) == 1


class _SimulatedClaimFailure(RuntimeError):
    """Injected answer-read failure for one claim folder."""


def test_run_preprocessing_workflow_soft_fails_one_claim(
    tmp_path: Path,
    minimal_app_config_factory: MinimalAppConfigFactory,
    mock_description_reader_factory: MockDescriptionReaderFactory,
    mock_document_reader_factory: MockDocumentReaderFactory,
) -> None:
    data_dir = tmp_path / "data"
    output_root = tmp_path / "preprocessed_out"
    _seed_minimal_claim(data_dir / "claim 1")
    _seed_minimal_claim(data_dir / "claim 2", decision="DENY")

    answer_reader = MagicMock()

    def _read_answer(path: Path) -> GroundTruth:
        if path.parent.name == "claim 2":
            raise _SimulatedClaimFailure
        return GroundTruth(decision="APPROVE")

    answer_reader.read.side_effect = _read_answer
    config = minimal_app_config_factory(data_dir, preprocessed_dir=output_root)

    written = PreprocessingPipeline(
        config,
        answer_reader=answer_reader,
        description_reader=mock_description_reader_factory(),
        document_reader=mock_document_reader_factory(),
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
        "\n".join([
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
            '  labels: ["1"]',
            '  other_label: "False"',
            "  model: test-model",
            "  prompt: classify",
            "checking:",
            "  model: test-model",
            "  containment_prompt: check containment",
            "  contradicts_prompt: check contradicts",
            "  identity_prompt: check identity",
            "  healthy_prompt: check healthy",
            "  incomplete_prompt: incomplete",
            "analysis:",
            "  coverage:",
            '    labels: ["1"]',
            "    branches:",
            '      "1": cancellation',
            '    other_label: "False"',
            "    model: test-model",
            "    prompt: classify",
            "  cancellation_reason:",
            '    labels: ["1"]',
            '    other_label: "False"',
            "    model: test-model",
            "    prompt: classify",
            "  cancellation_document:",
            '    labels: ["1"]',
            '    other_label: "False"',
            "    model: test-model",
            "    prompt: classify",
            "  personal_effects_document:",
            '    labels: ["1"]',
            '    other_label: "False"',
            "    model: test-model",
            "    prompt: classify",
            "  missed_departure_document:",
            '    labels: ["1"]',
            '    other_label: "False"',
            "    model: test-model",
            "    prompt: classify",
            "ocr_retry:",
            "  enabled: false",
            "  model: test-vision",
            "  prompt: ocr",
            "",
        ]),
        encoding="utf-8",
    )

    captured: dict[str, Any] = {}

    def _fake_run(self: PreprocessingPipeline, source: Path | None = None) -> list[Path]:
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


def test_run_with_claim_folder_processes_one(
    tmp_path: Path,
    minimal_app_config_factory: MinimalAppConfigFactory,
    mock_description_reader_factory: MockDescriptionReaderFactory,
    mock_document_reader_factory: MockDocumentReaderFactory,
) -> None:
    """R020: run(claim_folder) processes that folder only — siblings untouched."""
    data_dir = tmp_path / "data"
    output_root = tmp_path / "preprocessed_out"
    claim1 = data_dir / "claim 1"
    claim2 = data_dir / "claim 2"
    _seed_minimal_claim(claim1)
    _seed_minimal_claim(claim2, decision="DENY")
    config = minimal_app_config_factory(data_dir, preprocessed_dir=output_root)
    expected = _expected_artifacts(config)

    written = PreprocessingPipeline(
        config,
        description_reader=mock_description_reader_factory(),
        document_reader=mock_document_reader_factory(),
    ).run(claim1)

    assert [p.name for p in written] == ["claim 1"]
    assert (output_root / "claim 1").is_dir()
    assert sorted(p.name for p in (output_root / "claim 1").iterdir() if p.is_file()) == sorted(expected)
    assert not (output_root / "claim 2").exists()


def test_run_with_directory_batches(
    tmp_path: Path,
    minimal_app_config_factory: MinimalAppConfigFactory,
    mock_description_reader_factory: MockDescriptionReaderFactory,
    mock_document_reader_factory: MockDocumentReaderFactory,
) -> None:
    """R020: run(parent_dir) soft-fail batches under the caller-supplied path."""
    # Parent is NOT config data_dir — proves discovery uses the Path argument.
    parent = tmp_path / "external_batch"
    config_data = tmp_path / "unused_config_data"
    config_data.mkdir()
    output_root = tmp_path / "preprocessed_out"
    _seed_minimal_claim(parent / "claim 1")
    _seed_minimal_claim(parent / "claim 2", decision="DENY")
    config = minimal_app_config_factory(config_data, preprocessed_dir=output_root)

    written = PreprocessingPipeline(
        config,
        description_reader=mock_description_reader_factory(),
        document_reader=mock_document_reader_factory(),
    ).run(parent)

    assert sorted(p.name for p in written) == ["claim 1", "claim 2"]
    assert (output_root / "claim 1").is_dir()
    assert (output_root / "claim 2").is_dir()


def test_run_none_uses_config_roots(
    tmp_path: Path,
    minimal_app_config_factory: MinimalAppConfigFactory,
    mock_description_reader_factory: MockDescriptionReaderFactory,
    mock_document_reader_factory: MockDocumentReaderFactory,
) -> None:
    """R020: run(None) discovers under config data_dir (Phase 03 regression)."""
    data_dir = tmp_path / "data"
    output_root = tmp_path / "preprocessed_out"
    _seed_minimal_claim(data_dir / "claim 1")
    config = minimal_app_config_factory(data_dir, preprocessed_dir=output_root)

    written = PreprocessingPipeline(
        config,
        description_reader=mock_description_reader_factory(),
        document_reader=mock_document_reader_factory(),
    ).run(None)

    assert [p.name for p in written] == ["claim 1"]
    assert (output_root / "claim 1").is_dir()


def test_cli_or_api_passes_path_from_outside(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R020: CLI --claim-id resolves under data_dir and calls process_then_analyze."""
    from main import CliArgs, main

    assert "claim_id" in CliArgs.model_fields

    from compliance.workflows.claim_pipeline import ClaimPipeline
    from compliance.workflows.pipeline import PreprocessingPipeline as PP

    cfg_path = tmp_path / "config.yaml"
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "claim 1").mkdir()
    output_root = tmp_path / "preprocessed_out"
    results = tmp_path / "results_out"
    cfg_path.write_text(
        "\n".join([
            "preprocessing:",
            f"  data_dir: {data_dir}",
            "  document_formats: [webp, jpg, jpeg, png, pdf]",
            "  confidence_threshold: 0.7",
            f"  preprocessed_dir: {output_root}",
            f"  results_dir: {results}",
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
            '  labels: ["1"]',
            '  other_label: "False"',
            "  model: test-model",
            "  prompt: classify",
            "checking:",
            "  model: test-model",
            "  containment_prompt: check containment",
            "  contradicts_prompt: check contradicts",
            "  identity_prompt: check identity",
            "  healthy_prompt: check healthy",
            "  incomplete_prompt: incomplete",
            "analysis:",
            "  coverage:",
            '    labels: ["1"]',
            "    branches:",
            '      "1": cancellation',
            '    other_label: "False"',
            "    model: test-model",
            "    prompt: classify",
            "  cancellation_reason:",
            '    labels: ["1"]',
            '    other_label: "False"',
            "    model: test-model",
            "    prompt: classify",
            "  cancellation_document:",
            '    labels: ["1"]',
            '    other_label: "False"',
            "    model: test-model",
            "    prompt: classify",
            "  personal_effects_document:",
            '    labels: ["1"]',
            '    other_label: "False"',
            "    model: test-model",
            "    prompt: classify",
            "  missed_departure_document:",
            '    labels: ["1"]',
            '    other_label: "False"',
            "    model: test-model",
            "    prompt: classify",
            "ocr_retry:",
            "  enabled: false",
            "  model: test-vision",
            "  prompt: ocr",
            "",
        ]),
        encoding="utf-8",
    )

    captured: dict[str, Any] = {}

    def _fake_pta(
        claim_dir: Path,
        preprocessing: PP,
        claims: ClaimPipeline,
    ) -> Path:
        captured["claim_dir"] = claim_dir
        captured["data_dir"] = preprocessing._config.preprocessing.data_dir
        return results / "claim 1" / "analysis_result.json"

    monkeypatch.setattr("main.analyze_claim_exclusively", _fake_pta)

    assert main(["--config", str(cfg_path), "--claim-id", "claim 1"]) == 0
    assert captured["claim_dir"] == data_dir / "claim 1"
    assert captured["data_dir"] == str(data_dir)


def test_cli_claim_id_exits_1_when_lock_held(
    tmp_path: Path,
) -> None:
    """CLI --claim-id returns 1 when another analysis holds the per-claim lock."""
    from compliance.workflows.artifact_publication import claim_analysis_lock
    from main import main

    cfg_path = tmp_path / "config.yaml"
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "claim 1").mkdir()
    output_root = tmp_path / "preprocessed_out"
    results = tmp_path / "results_out"
    cfg_path.write_text(
        "\n".join([
            "preprocessing:",
            f"  data_dir: {data_dir}",
            "  document_formats: [webp, jpg, jpeg, png, pdf]",
            "  confidence_threshold: 0.7",
            f"  preprocessed_dir: {output_root}",
            f"  results_dir: {results}",
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
            '  labels: ["1"]',
            '  other_label: "False"',
            "  model: test-model",
            "  prompt: classify",
            "checking:",
            "  model: test-model",
            "  containment_prompt: check containment",
            "  contradicts_prompt: check contradicts",
            "  identity_prompt: check identity",
            "  healthy_prompt: check healthy",
            "  incomplete_prompt: incomplete",
            "analysis:",
            "  coverage:",
            '    labels: ["1"]',
            "    branches:",
            '      "1": cancellation',
            '    other_label: "False"',
            "    model: test-model",
            "    prompt: classify",
            "  cancellation_reason:",
            '    labels: ["1"]',
            '    other_label: "False"',
            "    model: test-model",
            "    prompt: classify",
            "  cancellation_document:",
            '    labels: ["1"]',
            '    other_label: "False"',
            "    model: test-model",
            "    prompt: classify",
            "  personal_effects_document:",
            '    labels: ["1"]',
            '    other_label: "False"',
            "    model: test-model",
            "    prompt: classify",
            "  missed_departure_document:",
            '    labels: ["1"]',
            '    other_label: "False"',
            "    model: test-model",
            "    prompt: classify",
            "ocr_retry:",
            "  enabled: false",
            "  model: test-vision",
            "  prompt: ocr",
            "",
        ]),
        encoding="utf-8",
    )

    with claim_analysis_lock(results, "claim 1"):
        assert main(["--config", str(cfg_path), "--claim-id", "claim 1"]) == 1
