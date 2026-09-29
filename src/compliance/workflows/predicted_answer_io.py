from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from compliance.branch_log import log_branch_decision
from compliance.models.claim import GroundTruth

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
    if source is not None:
        return False
    return _explanation_looks_like_fraud(data.get("explanation"))


def write_preprocess_predicted_answer(path: Path, prediction: GroundTruth) -> Path:
    """Write a preprocess-origin predicted_answer.json under ``path``.

    :param path: Destination path for predicted_answer.json.
    :param prediction: GroundTruth decision from document-level preprocess.
    :return: Path written.
    """
    return _write_sourced_predicted_answer(
        path,
        prediction,
        source=SOURCE_PREPROCESS,
        reason=_log_reason_from_prediction(prediction),
    )


def write_analysis_predicted_answer(path: Path, prediction: GroundTruth) -> Path:
    """Write an analysis-origin predicted_answer.json under ``path``.

    :param path: Destination path for predicted_answer.json.
    :param prediction: GroundTruth decision from analysis (may include HITL).
    :return: Path written.
    """
    return _write_sourced_predicted_answer(
        path,
        prediction,
        source=SOURCE_ANALYSIS,
        reason="analysis_decision",
    )


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
    skip_reason = _stale_skip_reason(predicted_path, analysis_result_path)
    if skip_reason is not None:
        _log_predicted_answer_outcome(
            outcome="SKIP",
            reason=skip_reason,
            path=predicted_path,
        )
        return False

    predicted_path.unlink()
    _log_predicted_answer_outcome(
        outcome="REMOVED",
        reason="stale_no_pipeline_decision",
        path=predicted_path,
    )
    return True


def _write_sourced_predicted_answer(
    path: Path,
    prediction: GroundTruth,
    *,
    source: str,
    reason: str,
) -> Path:
    payload = json.loads(prediction.model_dump_json())
    payload["source"] = source
    _write_predicted_answer_file(path, payload)
    log_branch_decision(
        logger,
        branch="predicted_answer",
        outcome="WROTE",
        reason=reason,
        decision=prediction.decision,
        path=str(path),
    )
    return path


def _stale_skip_reason(
    predicted_path: Path,
    analysis_result_path: Path,
) -> str | None:
    if not predicted_path.is_file():
        return "no_pipeline_decision"
    if analysis_result_path.is_file():
        return "analysis_result_present"
    data = _predicted_answer_payload(predicted_path)
    if not is_preprocess_origin_prediction(data):
        return "not_preprocess_origin"
    return None


def _write_predicted_answer_file(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _log_reason_from_prediction(prediction: GroundTruth) -> str:
    explanation = prediction.explanation
    if isinstance(explanation, str):
        return explanation
    return "decision"


def _log_predicted_answer_outcome(
    *,
    outcome: str,
    reason: str,
    path: Path,
) -> None:
    log_branch_decision(
        logger,
        branch="predicted_answer",
        outcome=outcome,
        reason=reason,
        path=str(path),
    )


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
