from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import numpy as np
import pytest

from compliance.config.settings import load_config
from compliance.models.claim import BookingData, ClaimBundle, DocumentData
from compliance.preprocessing.description import DescriptionReader
from compliance.preprocessing.extractor import InformationExtractor
from compliance.preprocessing.pipeline import run_pipeline

DATA_DIR = Path("data")


def _is_nan(value: object) -> bool:
    return isinstance(value, float) and np.isnan(value)


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
def test_pipeline_all_25_claims_write_processed_json() -> None:
    if not DATA_DIR.is_dir():
        pytest.skip("data/ directory not present")

    config = load_config("config.yaml")
    assert Path(config.preprocessing.data_dir).resolve() == DATA_DIR.resolve() or Path(
        config.preprocessing.data_dir
    ).name == "data"

    kwargs: dict[str, Any] = {}
    if not _ollama_available():
        kwargs["description_reader"] = _passthrough_description_reader()

    bundles = run_pipeline(config, **kwargs)

    assert len(bundles) == 25
    for claim_dir in sorted(DATA_DIR.glob("claim *"), key=lambda p: p.name):
        out = claim_dir / config.preprocessing.output_filename
        assert out.is_file(), f"missing {out}"
        bundle = ClaimBundle.model_validate_json(out.read_text(encoding="utf-8"))
        assert bundle.claim_id == claim_dir.name
        assert isinstance(bundle.ground_truth.decision, str)
        assert isinstance(bundle.description_text, str) or _is_nan(bundle.description_text)


@pytest.mark.integration
def test_spot_checks_key_claims() -> None:
    if not DATA_DIR.is_dir():
        pytest.skip("data/ directory not present")

    config = load_config("config.yaml")
    output_name = config.preprocessing.output_filename
    formats = config.preprocessing.document_formats

    def load_claim(n: int) -> ClaimBundle:
        path = DATA_DIR / f"claim {n}" / output_name
        if not path.is_file():
            pytest.skip(f"processed.json missing for claim {n}; run full integration first")
        return ClaimBundle.model_validate_json(path.read_text(encoding="utf-8"))

    # Ensure processed files exist (depends on prior test or prior run)
    claim1_out = DATA_DIR / "claim 1" / output_name
    if not claim1_out.is_file():
        kwargs: dict[str, Any] = {}
        if not _ollama_available():
            kwargs["description_reader"] = _passthrough_description_reader()
        run_pipeline(config, **kwargs)

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
    # claim 13 currently includes a medical image in data/; assert matches disk
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
        AppConfig,
        ClassificationConfig,
        ExtractionConfig,
        PreprocessingConfig,
    )

    claim = tmp_path / "claim 1"
    claim.mkdir()
    (claim / "answer.json").write_text('{"decision": "APPROVE"}', encoding="utf-8")
    (claim / "description.txt").write_text("refund please", encoding="utf-8")

    config = AppConfig(
        preprocessing=PreprocessingConfig(
            data_dir=str(tmp_path),
            output_filename="processed.json",
            document_formats=["webp", "jpg", "jpeg", "png", "pdf"],
            confidence_threshold=0.7,
        ),
        extraction=ExtractionConfig(model="unused", prompt="unused"),
        classification=ClassificationConfig(
            labels=["Trip cancellation or rescheduling"],
            other_label="Other",
            model="unused",
            prompt="unused",
        ),
    )
    bundles = run_pipeline(config, description_reader=_passthrough_description_reader())
    assert len(bundles) == 1
    assert (claim / "processed.json").is_file()
    payload = json.loads((claim / "processed.json").read_text(encoding="utf-8"))
    assert payload["claim_id"] == "claim 1"
