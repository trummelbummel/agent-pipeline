from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from compliance.branch_log import log_branch_decision
from compliance.models.claim import GroundTruth, is_nan_scalar

logger = logging.getLogger(__name__)

SOURCE_PREPROCESS = "preprocess"
SOURCE_ANALYSIS = "analysis"

_FRAUD_EXPLANATION_MARKERS = ("fraud", "benford")


def is_preprocess_origin_prediction(data: dict[str, Any]) -> bool:
    """Return whether a predicted_answer payload was authored by preprocess.

    Recognizes an explicit ``source=preprocess`` stamp, or legacy files that
    lack ``source`` but carry a fraud/Benford explanation.

    :param data: Parsed predicted_answer.json object.
    :return: True when preprocess owns the file and may safely remove it.
    """
    source = data.get("source")
    if source == SOURCE_PREPROCESS:
        return True
    if source == SOURCE_ANALYSIS:
        return False
    if source is not None:
        return False
    return _explanation_looks_like_fraud(data.get("explanation"))


def write_preprocess_predicted_answer(path: Path, prediction: GroundTruth) -> Path:
    """Write a preprocess-origin predicted_answer.json under ``path``.

    :param path: Destination path for predicted_answer.json.
    :param prediction: GroundTruth decision from document-level preprocess.
    :return: Path written.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = prediction.model_dump(mode="json")
    payload["source"] = SOURCE_PREPROCESS
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    reason = (
        prediction.explanation
        if isinstance(prediction.explanation, str)
        and not is_nan_scalar(prediction.explanation)
        else "decision"
    )
    log_branch_decision(
        logger,
        branch="predicted_answer",
        outcome="WROTE",
        reason=reason if isinstance(reason, str) else "decision",
        decision=prediction.decision,
        path=str(path),
    )
    return path


def write_analysis_predicted_answer(path: Path, payload: dict[str, Any]) -> Path:
    """Write an analysis-origin predicted_answer.json under ``path``.

    :param path: Destination path for predicted_answer.json.
    :param payload: Decision dict (may already include HITL fields).
    :return: Path written.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    body = dict(payload)
    body["source"] = SOURCE_ANALYSIS
    path.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
    log_branch_decision(
        logger,
        branch="predicted_answer",
        outcome="WROTE",
        reason="analysis_decision",
        decision=body.get("decision"),
        path=str(path),
    )
    return path


def remove_stale_preprocess_prediction(
    predicted_path: Path,
    *,
    analysis_result_path: Path,
) -> bool:
    """Unlink a preprocess-origin predicted_answer when analysis has not run.

    Preserves analysis-authored files and any prediction when
    ``analysis_result.json`` exists. Legacy fraud/Benford files without a
    ``source`` stamp are treated as preprocess-origin.

    :param predicted_path: Path to predicted_answer.json under results_dir.
    :param analysis_result_path: Sibling analysis_result.json path.
    :return: True when the file was unlinked; False when skipped or absent.
    """
    if not predicted_path.is_file():
        log_branch_decision(
            logger,
            branch="predicted_answer",
            outcome="SKIP",
            reason="no_pipeline_decision",
            path=str(predicted_path),
        )
        return False

    if analysis_result_path.is_file():
        log_branch_decision(
            logger,
            branch="predicted_answer",
            outcome="SKIP",
            reason="analysis_result_present",
            path=str(predicted_path),
        )
        return False

    data = _predicted_answer_payload(predicted_path)
    if not is_preprocess_origin_prediction(data):
        log_branch_decision(
            logger,
            branch="predicted_answer",
            outcome="SKIP",
            reason="not_preprocess_origin",
            path=str(predicted_path),
        )
        return False

    predicted_path.unlink()
    log_branch_decision(
        logger,
        branch="predicted_answer",
        outcome="REMOVED",
        reason="stale_no_pipeline_decision",
        path=str(predicted_path),
    )
    return True


def _predicted_answer_payload(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        return raw
    return {}


def _explanation_looks_like_fraud(explanation: object) -> bool:
    if not isinstance(explanation, str):
        return False
    lowered = explanation.lower()
    return any(marker in lowered for marker in _FRAUD_EXPLANATION_MARKERS)
