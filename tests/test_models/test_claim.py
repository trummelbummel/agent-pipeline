from __future__ import annotations

import json

from compliance.models import (
    BookingData,
    ClaimBundle,
    DocumentData,
    DocumentMetaData,
    GroundTruth,
    SourceFiles,
    is_nan_scalar,
)


def test_ground_truth_minimal_fills_nan() -> None:
    gt = GroundTruth(decision="APPROVE")
    assert gt.decision == "APPROVE"
    assert is_nan_scalar(gt.explanation)
    assert is_nan_scalar(gt.acceptable_decision)


def test_booking_data_all_nan_by_default() -> None:
    booking = BookingData()
    for field_name in BookingData.model_fields:
        assert is_nan_scalar(getattr(booking, field_name)), field_name


def test_booking_data_partial_fields() -> None:
    booking = BookingData(name="Ada Lovelace", booking_ref="ABC123")
    assert booking.name == "Ada Lovelace"
    assert booking.booking_ref == "ABC123"
    assert is_nan_scalar(booking.origin)
    assert is_nan_scalar(booking.destination)


def test_document_data_core_person_date_defaults() -> None:
    doc = DocumentData()
    assert is_nan_scalar(doc.person)
    assert is_nan_scalar(doc.date)
    assert is_nan_scalar(doc.raw_text)
    assert is_nan_scalar(doc.metadata.extraction_probability)
    assert doc.metadata.human_in_the_loop is False
    assert doc.metadata.faulty_extraction is False
    assert doc.metadata.has_signature is False
    assert doc.fields == {}


def test_document_metadata_model() -> None:
    meta = DocumentMetaData(
        source_file="scan.png",
        has_signature=True,
        extraction_probability=0.88,
        faulty_extraction=True,
        human_in_the_loop=True,
        failure_reasons=["insufficient_substantive_text"],
        retry_used=True,
        retry_model="llava",
    )
    assert meta.has_signature is True
    assert meta.faulty_extraction is True
    assert meta.human_in_the_loop is True
    assert meta.failure_reasons == ["insufficient_substantive_text"]
    assert meta.retry_used is True
    assert meta.retry_model == "llava"


def test_document_data_arbitrary_fields_dict() -> None:
    doc = DocumentData(person="Pat", fields={"diagnosis": "flu", "facility": "ER"})
    assert doc.person == "Pat"
    assert doc.fields["diagnosis"] == "flu"
    assert doc.fields["facility"] == "ER"


def test_document_data_extra_allow_unknown_keys() -> None:
    doc = DocumentData.model_validate({"person": "Sam", "airline": "XY", "seat": "12A"})
    assert doc.person == "Sam"
    assert doc.airline == "XY"  # type: ignore[attr-defined]
    assert doc.seat == "12A"  # type: ignore[attr-defined]


def test_claim_bundle_round_trip() -> None:
    bundle = ClaimBundle(
        claim_id="claim-1",
        ground_truth=GroundTruth(decision="DENY", explanation="late"),
        booking_data=BookingData(name="Ada"),
        description_booking=BookingData(),
        description_text="I missed my flight",
        source_files=SourceFiles(description_path="description.txt"),
    )
    payload = json.loads(bundle.model_dump_json())
    assert payload["ground_truth"]["explanation"] == "late"
    assert payload["booking_data"]["origin"] is None
    assert payload["description_text"] == "I missed my flight"
    assert payload["source_files"]["answer_path"] is None

    restored = ClaimBundle.model_validate_json(bundle.model_dump_json())
    assert restored.claim_id == "claim-1"
    assert restored.ground_truth.decision == "DENY"
    assert restored.booking_data.name == "Ada"
    assert is_nan_scalar(restored.booking_data.origin)
    assert is_nan_scalar(restored.source_files.answer_path)
    assert restored.description_text == "I missed my flight"
