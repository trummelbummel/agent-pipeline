"""analysis_result.json payload builder.

Pure: state + analysis config + OCR-failure reason + metadata run id in;
JSON-serializable body out. No filesystem.
"""

from __future__ import annotations

from compliance.config.settings import AnalysisConfig
from compliance.policy.decision import (
    decision_from_state,
    human_in_the_loop_provenance,
    resolved_human_in_the_loop,
)
from compliance.policy.documents import document_stage_for_coverage, is_missing_documentation
from compliance.policy.state import ClaimAnalysisState

# Checker and gate booleans copied into analysis_result.json, in payload key order.
_STATE_BOOLEAN_KEYS: tuple[str, ...] = (
    "checker_containment",
    "checker_contradicts",
    "identity_check",
    "identity_unclear",
    "document_has_signature",
    "signature_check",
    "healthy_check",
    "checker_incomplete_document",
    "departure_within_days",
    "checker_suspicious_dating",
)

__all__ = ["analysis_result_payload"]


def analysis_result_payload(
    state: ClaimAnalysisState,
    *,
    analysis: AnalysisConfig,
    ocr_failure_reason: str | None,
    metadata_run_id: str | None,
) -> dict[str, object]:
    """Build the structured analysis_result.json body from graph state.

    ``*_labels`` hold semantic names from ``config.analysis.*.label_names``;
    numeric classifier codes are written alongside as ``*_label_codes``.
    Also records the evaluator-facing ``decision`` derived from checker flags.

    :param state: Final ClaimAnalysisState after checker (or coverage-only).
    :param analysis: Analysis stage configuration.
    :param ocr_failure_reason: Preprocess OCR-failure code when present.
    :param metadata_run_id: Preprocess ``run_id`` from document_metadata.json,
        or None when absent.
    :return: JSON-serializable analysis payload. Checker keys are omitted when
        the Checker node did not run (coverage other_label path).
    """
    coverage_codes = list(state.get("coverage_labels") or [])
    reason_codes = list(state.get("reason_labels") or [])
    document_codes = list(state.get("document_labels") or [])
    routed = state["routed_coverage"]
    document_stage = document_stage_for_coverage(analysis, routed)
    payload: dict[str, object] = {
        "claim_id": state["claim_id"],
        "coverage_labels": analysis.coverage.resolve_label_names(coverage_codes),
        "coverage_label_codes": coverage_codes,
        "routed_coverage_label": analysis.coverage.resolve_label_names([routed.label])[0],
        "routed_coverage_label_code": routed.label,
        "coverage_probabilities": dict(state.get("coverage_probabilities") or {}),
        "reason_labels": analysis.cancellation_reason.resolve_label_names(reason_codes),
        "reason_label_codes": reason_codes,
        "document_labels": document_stage.resolve_label_names(document_codes),
        "document_label_codes": document_codes,
    }
    payload.update(_state_boolean_flags(state))
    if state.get("checker_outcomes"):
        payload["checker_outcomes"] = {mode: outcome.value for mode, outcome in state["checker_outcomes"].items()}
    if "checker_rule_set" in state:
        payload["checker_rule_set"] = state["checker_rule_set"]
    if "checker_skipped" in state:
        payload["checker_skipped"] = list(state["checker_skipped"])
    if "document_labels" in state:
        payload["checker_missing_documentation"] = is_missing_documentation(state, analysis=analysis)
    hitl = resolved_human_in_the_loop(state, analysis=analysis, ocr_failure_reason=ocr_failure_reason)
    payload["human_in_the_loop"] = hitl
    payload["human_in_the_loop_source"] = human_in_the_loop_provenance(
        state,
        analysis=analysis,
        ocr_failure_reason=ocr_failure_reason,
    )
    if metadata_run_id is not None:
        payload["document_metadata_run_id"] = metadata_run_id
    decision = decision_from_state(state, analysis=analysis, ocr_failure_reason=ocr_failure_reason)
    payload["decision"] = decision.decision
    payload["decision_explanation"] = decision.explanation if isinstance(decision.explanation, str) else None
    payload["run_id"] = state["run_id"]
    return payload


def _state_boolean_flags(state: ClaimAnalysisState) -> dict[str, bool]:
    """Checker and gate booleans present in state, in analysis_result.json key order.

    :param state: Graph state to read boolean flags from.
    :return: Dict of ``_STATE_BOOLEAN_KEYS`` present in ``state``, cast to bool.
    """
    return {key: bool(state.get(key)) for key in _STATE_BOOLEAN_KEYS if key in state}
