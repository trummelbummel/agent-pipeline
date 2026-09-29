"""Pydantic response models for the Claims API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ClaimCreated(BaseModel):
    """Response body for a newly submitted claim.

    :param claim_id: Generated claim folder name under config data_dir.
    """

    claim_id: str = Field(description="Generated claim folder name under data_dir")


class ClaimDecision(BaseModel):
    """Published claim generation returned by POST analysis and the read-only GET.

    :param claim_id: Claim folder name under data_dir / results_dir.
    :param analysis_result: Parsed analysis_result.json object (required after success).
    :param predicted_answer: Optional predicted_answer.json when present under results_dir.
    """

    claim_id: str = Field(description="Claim folder name under data_dir")
    analysis_result: dict[str, Any] = Field(description="analysis_result.json body from ClaimPipeline")
    predicted_answer: dict[str, Any] | None = Field(
        default=None,
        description="predicted_answer.json when present under results_dir",
    )


class ClaimListItem(BaseModel):
    """One results_dir claim folder entry for GET /claims.

    An unreadable artifact is reported in ``errors`` rather than dropping the
    claim or failing the whole list.

    :param claim_id: Claim folder name under results_dir.
    :param analysis_result: Optional analysis_result.json when present and readable.
    :param predicted_answer: Optional predicted_answer.json when present and readable.
    :param errors: Maps artifact filename to a stable reason code
        (``artifact_missing``, ``run_id_missing``, ``run_id_mismatch``, ``invalid_json``);
        null when every artifact read cleanly.
    """

    claim_id: str = Field(description="Claim folder name under results_dir")
    analysis_result: dict[str, Any] | None = Field(
        default=None,
        description="analysis_result.json when present",
    )
    predicted_answer: dict[str, Any] | None = Field(
        default=None,
        description="predicted_answer.json when present",
    )
    errors: dict[str, str] | None = Field(
        default=None,
        description=(
            "Maps artifact filename to a stable reason code "
            "(artifact_missing, run_id_missing, run_id_mismatch, invalid_json); "
            "null when every artifact read cleanly"
        ),
    )
