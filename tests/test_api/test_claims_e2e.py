"""End-to-end Claims API flow: POST → GET decision → GET list."""

from __future__ import annotations

from collections.abc import Callable
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock
from urllib.parse import quote

from fastapi.testclient import TestClient

from api.app import create_app
from compliance.config.settings import (
    AnalysisConfig,
    AppConfig,
)
from compliance.models.claim import DocumentData, DocumentMetaData

if TYPE_CHECKING:
    from conftest import MockDescriptionReaderFactory, MockDocumentReaderFactory

TRIP_CANCELLATION = "1"


def _multipart_files() -> dict[str, Any]:
    narrative = b"I had to cancel my flight to Paris because of a medical emergency."
    return {
        "description": ("description.txt", BytesIO(narrative), "text/plain"),
        "supporting_documents": (
            "supporting_documents.md",
            BytesIO(b"# medical certificate\n"),
            "text/markdown",
        ),
        "image": ("scan.png", BytesIO(b"png-bytes"), "application/octet-stream"),
    }


def test_claims_endpoints_post_get_list_flow(
    tmp_path: Path,
    api_config_factory: Callable[..., AppConfig],
    cancellation_analysis_config: AnalysisConfig,
    cancellation_chat_fn: MagicMock,
    mock_description_reader_factory: MockDescriptionReaderFactory,
    mock_document_reader_factory: MockDocumentReaderFactory,
) -> None:
    """POST a claim, GET its decision, then see it on GET /claims."""
    data_dir = tmp_path / "raw"
    data_dir.mkdir()
    config = api_config_factory(
        data_dir,
        preprocessed_dir=tmp_path / "preprocessed",
        results_dir=tmp_path / "results",
        analysis=cancellation_analysis_config,
    )
    artifacts = config.preprocessing.artifacts
    app = create_app(
        config=config,
        chat_fn=cancellation_chat_fn,
        description_reader=mock_description_reader_factory(),
        document_reader=mock_document_reader_factory(
            default=DocumentData(
                raw_text=("I had to cancel my flight to Paris because of a medical emergency."),
                metadata=DocumentMetaData(extraction_probability=0.95),
            )
        ),
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
        assert items[0]["analysis_result"]["coverage_label_codes"] == [TRIP_CANCELLATION]
