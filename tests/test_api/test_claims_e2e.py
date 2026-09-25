"""End-to-end Claims API flow: POST → GET decision → GET list."""

from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock
from urllib.parse import quote

from fastapi.testclient import TestClient

from api.app import create_app
from compliance.config.settings import (
    AnalysisConfig,
    AppConfig,
    CheckingConfig,
    ClassificationConfig,
    EvaluationConfig,
    ExtractionConfig,
    PreprocessingConfig,
)
from compliance.models.claim import BookingData, DocumentData, DocumentMetaData
from compliance.preprocessing.description import DescriptionReader
from compliance.preprocessing.extractor import InformationExtractor

TRIP_CANCELLATION = "1"
MEDICAL_EMERGENCY = "2"
MEDICAL_CERTIFICATE = "1"


def _analysis_config() -> AnalysisConfig:
    coverage = ClassificationConfig(
        labels=["1", "2", "3"],
        other_label="None",
        model="test-model",
        prompt="classify coverage",
        label_names={
            "1": "Trip cancellation or rescheduling",
            "2": "Personal Effects",
            "3": "Missed Departure or Missed Connection",
        },
    )
    cancellation_reason = ClassificationConfig(
        labels=["1", "2", "3", "4"],
        other_label="None",
        model="test-model",
        prompt="classify reason",
        label_names={
            "1": "Jury duty",
            "2": "Medical emergency",
            "3": "Theft or criminal incident",
            "4": "Other specified personal emergencies",
        },
    )
    cancellation_document = ClassificationConfig(
        labels=["1", "2", "3"],
        other_label="None",
        model="test-model",
        prompt="classify cancel doc",
        label_names={
            "1": "medical certificate",
            "2": "police report",
            "3": "jury summon letter",
        },
    )
    stage = ClassificationConfig(
        labels=["1"],
        other_label="None",
        model="test-model",
        prompt="classify",
        label_names={"1": "Proof of theft, loss, or damage"},
    )
    return AnalysisConfig(
        coverage=coverage,
        cancellation_reason=cancellation_reason,
        cancellation_document=cancellation_document,
        personal_effects_document=stage,
        missed_departure_document=stage,
    )


def _config(tmp_path: Path) -> AppConfig:
    """Build AppConfig with isolated tmp filesystem roots.

    :param tmp_path: Pytest temporary directory.
    :return: AppConfig pointing raw/preprocessed/results under ``tmp_path``.
    """
    data_dir = tmp_path / "raw"
    data_dir.mkdir()
    return AppConfig(
        preprocessing=PreprocessingConfig(
            data_dir=str(data_dir),
            document_formats=["webp", "jpg", "jpeg", "png", "pdf"],
            confidence_threshold=0.7,
            preprocessed_dir=str(tmp_path / "preprocessed"),
            results_dir=str(tmp_path / "results"),
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
            identity_prompt="identity",
            healthy_prompt="healthy",
        ),
        analysis=_analysis_config(),
        evaluation=EvaluationConfig(
            labels=["APPROVE", "DENY", "UNCERTAIN"],
            metrics_artifact="evaluation_metrics.json",
        ),
    )


def _chat_response(payload: dict[str, Any]) -> SimpleNamespace:
    return SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))


def _cancellation_chat_fn() -> MagicMock:
    """Injected LLM seam for cancellation path (no live Ollama)."""
    coverage = _chat_response(
        {
            "labels": [TRIP_CANCELLATION],
            "probabilities": {TRIP_CANCELLATION: 0.9, "None": 0.1},
        }
    )
    reason = _chat_response(
        {
            "labels": [MEDICAL_EMERGENCY],
            "probabilities": {MEDICAL_EMERGENCY: 0.85, "None": 0.15},
        }
    )
    document = _chat_response(
        {
            "labels": [MEDICAL_CERTIFICATE],
            "probabilities": {MEDICAL_CERTIFICATE: 0.8, "None": 0.2},
        }
    )
    containment = _chat_response({"result": True})
    contradicts = _chat_response({"result": False})
    identity = _chat_response({"result": True})
    healthy = _chat_response({"result": False})
    return MagicMock(
        side_effect=[coverage, reason, document, containment, contradicts, identity, healthy]
    )


def _description_reader() -> DescriptionReader:
    chat = MagicMock(
        return_value=SimpleNamespace(message=SimpleNamespace(content=json.dumps({})))
    )
    extractor = InformationExtractor(
        target_model=BookingData,
        model_name="test-model",
        prompt="p",
        chat_fn=chat,
    )
    return DescriptionReader(extractor=extractor)


def _document_reader() -> MagicMock:
    reader = MagicMock()
    text = "I had to cancel my flight to Paris because of a medical emergency."
    reader.read.side_effect = lambda path: DocumentData(
        raw_text=text,
        metadata=DocumentMetaData(extraction_probability=0.95),
    )
    return reader


def _multipart_files() -> dict[str, Any]:
    narrative = (
        b"I had to cancel my flight to Paris because of a medical emergency."
    )
    return {
        "description": ("description.txt", BytesIO(narrative), "text/plain"),
        "supporting_documents": (
            "supporting_documents.md",
            BytesIO(b"# medical certificate\n"),
            "text/markdown",
        ),
        "image": ("scan.png", BytesIO(b"png-bytes"), "application/octet-stream"),
    }


def test_claims_endpoints_post_get_list_flow(tmp_path: Path) -> None:
    """POST a claim, GET its decision, then see it on GET /claims."""
    config = _config(tmp_path)
    artifacts = config.preprocessing.artifacts
    data_dir = Path(config.preprocessing.data_dir)
    app = create_app(
        config=config,
        chat_fn=_cancellation_chat_fn(),
        description_reader=_description_reader(),
        document_reader=_document_reader(),
    )

    with TestClient(app) as client:
        empty = client.get("/claims")
        assert empty.status_code == 200, empty.text
        assert empty.json() == []

        created = client.post("/claims", files=_multipart_files())
        assert created.status_code == 201, created.text
        claim_id = created.json()["claim_id"]
        assert claim_id.lower().startswith("claim")

        claim_dir = data_dir / claim_id
        assert (claim_dir / artifacts.description).is_file()
        assert (claim_dir / artifacts.supporting_documents).is_file()
        assert (claim_dir / "scan.png").is_file()

        decision = client.get(f"/claims/{quote(claim_id)}")
        assert decision.status_code == 200, decision.text
        body = decision.json()
        assert body["claim_id"] == claim_id
        analysis = body["analysis_result"]
        assert isinstance(analysis, dict)
        assert analysis["coverage_labels"] == ["Trip cancellation or rescheduling"]
        assert analysis["coverage_label_codes"] == [TRIP_CANCELLATION]
        assert "reason_labels" in analysis
        assert "document_labels" in analysis

        listed = client.get("/claims")
        assert listed.status_code == 200, listed.text
        items = listed.json()
        assert len(items) == 1
        assert items[0]["claim_id"] == claim_id
        assert items[0]["analysis_result"] is not None
        assert items[0]["analysis_result"]["coverage_label_codes"] == [
            TRIP_CANCELLATION
        ]
