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
    """Decision payload for GET /claims/{claim_id} after process_then_analyze.

    :param claim_id: Claim folder name under data_dir / results_dir.
    :param analysis_result: Parsed analysis_result.json object (required after success).
    :param predicted_answer: Optional predicted_answer.json when present under results_dir.
    """

    claim_id: str = Field(description="Claim folder name under data_dir")
    analysis_result: dict[str, Any] = Field(
        description="analysis_result.json body from ClaimPipeline"
    )
    predicted_answer: dict[str, Any] | None = Field(
        default=None,
        description="predicted_answer.json when present under results_dir",
    )


class ClaimListItem(BaseModel):
    """One results_dir claim folder entry for GET /claims.

    :param claim_id: Claim folder name under results_dir.
    :param analysis_result: Optional analysis_result.json when present.
    :param predicted_answer: Optional predicted_answer.json when present.
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
