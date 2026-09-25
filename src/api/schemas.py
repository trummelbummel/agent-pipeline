"""Pydantic response models for the Claims API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ClaimCreated(BaseModel):
    """Response body for a newly submitted claim.

    :param claim_id: Generated claim folder name under config data_dir.
    """

    claim_id: str = Field(description="Generated claim folder name under data_dir")
