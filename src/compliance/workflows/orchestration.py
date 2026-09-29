"""Shared single-claim orchestration used by API and CLI (D-09 / SR-007)."""

from __future__ import annotations

import logging
from pathlib import Path

from compliance.branch_log import log_branch_decision
from compliance.workflows.artifact_publication import (
    ClaimAnalysisBusyError,
    claim_analysis_lock,
)
from compliance.workflows.claim_pipeline import ClaimPipeline
from compliance.workflows.pipeline import PreprocessingPipeline

logger = logging.getLogger(__name__)


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


def analyze_claim_exclusively(
    claim_dir: Path,
    preprocessing: PreprocessingPipeline,
    claims: ClaimPipeline,
) -> Path:
    """Preprocess and analyse one claim under a non-blocking per-claim lock.

    The lock spans preprocessing as well as analysis so a duplicate request
    cannot re-run OCR before serialising on analysis.

    :param claim_dir: Raw claim directory under data_dir (name = claim_id).
    :param preprocessing: Injected PreprocessingPipeline.
    :param claims: Injected ClaimPipeline.
    :return: Path to the written analysis_result.json.
    :raises ClaimAnalysisBusyError: When another analysis already holds the lock.
    """
    claim_id = claim_dir.name
    try:
        with claim_analysis_lock(claims.results_root, claim_id):
            return process_then_analyze(claim_dir, preprocessing, claims)
    except ClaimAnalysisBusyError:
        log_branch_decision(
            logger,
            branch="claim_analysis_lock",
            outcome="BUSY",
            reason="already_running",
            level=logging.WARNING,
            claim=claim_id,
        )
        raise
