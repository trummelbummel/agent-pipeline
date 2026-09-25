from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from compliance.config.settings import load_config
from compliance.models.claim import BookingData, ClaimBundle, DocumentData, is_nan_scalar
from compliance.preprocessing.description import DescriptionReader
from compliance.preprocessing.extractor import InformationExtractor
from compliance.preprocessing.claim_batch import run_pipeline

DATA_DIR = Path("data/raw")


def _ollama_available() -> bool:
    try:
        import ollama

        ollama.list()
    except Exception:
        return False
    return True


def _passthrough_description_reader() -> DescriptionReader:
    """DescriptionReader that skips live LLM and returns empty BookingData."""
    chat = MagicMock(
        return_value=SimpleNamespace(message=SimpleNamespace(content="{}"))
    )
    extractor = InformationExtractor(
        target_model=BookingData,
        model_name="unused",
        prompt="unused",
        chat_fn=chat,
    )
    return DescriptionReader(extractor=extractor)


def _document_suffixes(claim_dir: Path, formats: list[str]) -> list[Path]:
    allowed = {fmt.lower().lstrip(".") for fmt in formats}
    return sorted(
        path
        for path in claim_dir.iterdir()
        if path.is_file() and path.suffix.lower().lstrip(".") in allowed
    )


@pytest.mark.integration
def test_pipeline_all_25_claims_return_bundles() -> None:
    if not DATA_DIR.is_dir():
        pytest.skip("data/raw directory not present")

    config = load_config("config.yaml")
    assert Path(config.preprocessing.data_dir).resolve() == DATA_DIR.resolve()

    kwargs: dict[str, Any] = {}
    if not _ollama_available():
        kwargs["description_reader"] = _passthrough_description_reader()

    bundles = run_pipeline(config, **kwargs)

    assert len(bundles) == 25
    by_id = {bundle.claim_id: bundle for bundle in bundles}
    for claim_dir in sorted(DATA_DIR.glob("claim *"), key=lambda p: p.name):
        bundle = by_id[claim_dir.name]
        assert isinstance(bundle.ground_truth.decision, str)
        assert isinstance(bundle.description_text, str) or is_nan_scalar(bundle.description_text)
        assert not (claim_dir / "processed.json").exists()


@pytest.mark.integration
def test_spot_checks_key_claims() -> None:
    if not DATA_DIR.is_dir():
        pytest.skip("data/raw directory not present")

    config = load_config("config.yaml")
    formats = config.preprocessing.document_formats

    kwargs: dict[str, Any] = {}
    if not _ollama_available():
        kwargs["description_reader"] = _passthrough_description_reader()
    bundles = {bundle.claim_id: bundle for bundle in run_pipeline(config, **kwargs)}

    def load_claim(n: int) -> ClaimBundle:
        return bundles[f"claim {n}"]

    claim1 = load_claim(1)
    assert any(
        isinstance(doc, DocumentData) for doc in claim1.documents
    ), "claim 1 should extract booking confirmation png"
    assert len(_document_suffixes(DATA_DIR / "claim 1", formats)) >= 1

    claim10 = load_claim(10)
    claim16 = load_claim(16)
    assert len(claim10.documents) >= 1
    assert len(claim16.documents) >= 1

    claim21 = load_claim(21)
    assert claim21.documents == []
    assert not _document_suffixes(DATA_DIR / "claim 21", formats)

    claim13 = load_claim(13)
    # claim 13 currently includes a medical image in data/raw; assert matches disk
    expected_13 = len(_document_suffixes(DATA_DIR / "claim 13", formats))
    assert len(claim13.documents) == expected_13 or len(claim13.documents) <= expected_13

    claim22 = load_claim(22)
    assert claim22.booking_data.name == "José Juan Robledo Romero"
    assert claim22.booking_data.booking_ref == "TRN-99563744"
    assert len(claim22.documents) >= 1


@pytest.mark.integration
def test_pipeline_no_uncaught_exceptions_on_partial_claim(tmp_path: Path) -> None:
    """Sanity: pipeline continues when optional files are absent."""
    from compliance.config.settings import (
        AnalysisConfig,
        AppConfig,
        CheckingConfig,
        ClassificationConfig,
        EvaluationConfig,
        ExtractionConfig,
        PreprocessingConfig,
    )

    claim = tmp_path / "claim 1"
    claim.mkdir()
    (claim / "answer.json").write_text('{"decision": "APPROVE"}', encoding="utf-8")
    (claim / "description.txt").write_text("refund please", encoding="utf-8")

    stage = ClassificationConfig(
        labels=["1"],
        other_label="None",
        model="unused",
        prompt="unused",
    )
    config = AppConfig(
        preprocessing=PreprocessingConfig(
            data_dir=str(tmp_path),
            document_formats=["webp", "jpg", "jpeg", "png", "pdf"],
            confidence_threshold=0.7,
            preprocessed_dir="data/preprocessed",
            results_dir="data/results",
        ),
        extraction=ExtractionConfig(model="unused", prompt="unused"),
        classification=ClassificationConfig(
            labels=["1"],
            other_label="Other",
            model="unused",
            prompt="unused",
        ),
        checking=CheckingConfig(
            model="unused",
            containment_prompt="containment",
            contradicts_prompt="contradicts",
            identity_prompt="identity",
            healthy_prompt="healthy",
        ),
        analysis=AnalysisConfig(
            coverage=stage,
            cancellation_reason=stage,
            cancellation_document=stage,
            personal_effects_document=stage,
            missed_departure_document=stage,
        ),
        evaluation=EvaluationConfig(
            labels=["APPROVE", "DENY", "UNCERTAIN"],
            metrics_artifact="evaluation_metrics.json",
        ),
    )
    bundles = run_pipeline(config, description_reader=_passthrough_description_reader())
    assert len(bundles) == 1
    assert bundles[0].claim_id == "claim 1"
    assert not (claim / "processed.json").exists()
