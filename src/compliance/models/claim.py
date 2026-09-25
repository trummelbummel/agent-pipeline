from __future__ import annotations

from typing import Annotated, Any

import numpy as np
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

_MISSING = np.nan


def is_nan_scalar(value: object) -> bool:
    """Return True when ``value`` is a float NaN sentinel.

    :param value: Arbitrary value that may be a NanStr/NanFloat missing marker.
    :return: Whether the value is float NaN.
    """
    return isinstance(value, float) and np.isnan(value)


def _none_to_nan(value: Any) -> Any:
    """Map JSON null to np.nan for optional scalar fields.

    :param value: Raw inbound value before type coercion.
    :return: np.nan when value is None, otherwise the original value.
    """
    return _MISSING if value is None else value


NanStr = Annotated[str | float, BeforeValidator(_none_to_nan)]
NanFloat = Annotated[float, BeforeValidator(_none_to_nan)]


class NanAwareModel(BaseModel):
    """Base model that serializes float NaN as JSON null."""

    model_config = ConfigDict(ser_json_inf_nan="null")


class GroundTruth(NanAwareModel):
    """Ground-truth decision from answer.json.

    :param decision: Required approve/deny/uncertain decision string.
    :param explanation: Optional rationale; missing values are np.nan.
    :param acceptable_decision: Alternate acceptable decision when uncertain.
    """

    decision: str
    explanation: NanStr = _MISSING
    acceptable_decision: NanStr = _MISSING


class BookingData(NanAwareModel):
    """Maximal booking/travel fields across claim markdown and descriptions.

    All scalar fields default to np.nan when absent.
    """

    current_date: NanStr = _MISSING
    name: NanStr = _MISSING
    booking_ref: NanStr = _MISSING
    price: NanStr = _MISSING
    operator: NanStr = _MISSING
    service: NanStr = _MISSING
    departure: NanStr = _MISSING
    origin: NanStr = _MISSING
    destination: NanStr = _MISSING
    seat: NanStr = _MISSING
    fare_type: NanStr = _MISSING
    booked_on: NanStr = _MISSING
    check_out: NanStr = _MISSING
    guests: NanStr = _MISSING
    venue: NanStr = _MISSING
    bib_number: NanStr = _MISSING
    booking_platform: NanStr = _MISSING
    cancellation: NanStr = _MISSING


class DocumentData(NanAwareModel):
    """Extensible document extraction target (D008) — not medical-specific.

    Core person/date plus pipeline metadata; other keys go in ``fields``
    or as top-level extras via ``extra='allow'``.
    """

    model_config = ConfigDict(ser_json_inf_nan="null", extra="allow")

    person: NanStr = _MISSING
    date: NanStr = _MISSING
    raw_text: NanStr = _MISSING
    confidence: NanFloat = _MISSING
    human_in_the_loop: bool = False
    has_signature: bool = False
    timestamps: list[str] = Field(default_factory=list)
    fields: dict[str, Any] = Field(default_factory=dict)


class SourceFiles(NanAwareModel):
    """Filesystem paths discovered for a claim folder."""

    description_path: NanStr = _MISSING
    answer_path: NanStr = _MISSING
    markdown_paths: list[str] = Field(default_factory=list)
    document_paths: list[str] = Field(default_factory=list)


class ClaimBundle(NanAwareModel):
    """Full structured claim payload written to processed.json.

    :param claim_id: Claim folder identifier.
    :param ground_truth: Parsed answer.json decision.
    :param booking_data: Primary booking record (supporting markdown).
    :param description_booking: Booking fields extracted from description.txt.
    :param internal_data: Additional internal markdown booking records.
    :param documents: Docling-extracted document entries.
    :param description_text: Raw description letter text.
    :param source_files: Paths of inputs used to build this bundle.
    """

    claim_id: str
    ground_truth: GroundTruth
    booking_data: BookingData
    description_booking: BookingData
    internal_data: list[BookingData] = Field(default_factory=list)
    documents: list[DocumentData] = Field(default_factory=list)
    description_text: NanStr = _MISSING
    source_files: SourceFiles
