"""Shared single-claim orchestration used by API and CLI (D-09)."""

from __future__ import annotations

from pathlib import Path

from compliance.workflows.claim_pipeline import ClaimPipeline
from compliance.workflows.pipeline import PreprocessingPipeline


def process_then_analyze(
    claim_dir: Path,
    preprocessing: PreprocessingPipeline,
    claims: ClaimPipeline,
) -> Path:
    """Preprocess one raw claim folder then run ClaimPipeline analysis.

    :param claim_dir: Raw claim directory under data_dir (name = claim_id).
    :param preprocessing: Injected PreprocessingPipeline.
    :param claims: Injected ClaimPipeline.
    :return: Path to the written analysis_result.json.
    """
    preprocessing.process_claim(claim_dir)
    return claims.analyze_claim(claim_dir)
