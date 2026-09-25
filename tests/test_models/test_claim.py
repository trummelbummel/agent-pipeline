from __future__ import annotations

import json

import numpy as np

from compliance.models import (
    BookingData,
    ClaimBundle,
    DocumentData,
    GroundTruth,
    SourceFiles,
)


def _is_nan(value: object) -> bool:
    return isinstance(value, float) and np.isnan(value)


def test_ground_truth_minimal_fills_nan() -> None:
    gt = GroundTruth(decision="APPROVE")
    assert gt.decision == "APPROVE"
    assert _is_nan(gt.explanation)
    assert _is_nan(gt.acceptable_decision)


def test_booking_data_all_nan_by_default() -> None:
    booking = BookingData()
    for field_name in BookingData.model_fields:
        assert _is_nan(getattr(booking, field_name)), field_name


def test_booking_data_partial_fields() -> None:
    booking = BookingData(name="Ada Lovelace", booking_ref="ABC123")
    assert booking.name == "Ada Lovelace"
    assert booking.booking_ref == "ABC123"
    assert _is_nan(booking.origin)
    assert _is_nan(booking.destination)


def test_document_data_core_person_date_defaults() -> None:
    doc = DocumentData()
    assert _is_nan(doc.person)
    assert _is_nan(doc.date)
    assert _is_nan(doc.raw_text)
    assert _is_nan(doc.confidence)
    assert doc.human_in_the_loop is False
    assert doc.fields == {}


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
    assert _is_nan(restored.booking_data.origin)
    assert _is_nan(restored.source_files.answer_path)
    assert restored.description_text == "I missed my flight"
