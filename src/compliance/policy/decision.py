"""Ordered decision fold and HITL resolution (SR-008).

Pure: state + analysis config + OCR-failure reason in; GroundTruth / HITL
flags out. No filesystem — the caller supplies ``ocr_failure_reason``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import NamedTuple

from compliance.config.settings import AnalysisConfig
from compliance.llm.checker import CheckerMode, CheckOutcome
from compliance.models.claim import GroundTruth
from compliance.models.decisions import (
    DECISION_APPROVE,
    DECISION_DENY,
    DECISION_UNCERTAIN,
)
from compliance.policy.documents import is_missing_documentation
from compliance.policy.state import ClaimAnalysisState

# Checker VIOLATION → legacy DENY explanation key (order matches violated_checkers).
_VIOLATION_LEGACY_KEYS: tuple[tuple[CheckerMode, str], ...] = (
    ("identity", "identity_check"),
    ("healthy", "healthy_check"),
    ("not_authentic", "checker_document_not_authentic"),
    ("incomplete", "checker_incomplete_document"),
    ("contradicts", "checker_contradicts"),
)

# Modes whose ABSTAIN drives UNCERTAIN (identity only; containment ABSTAIN is record-only).
_ABSTAIN_UNCERTAIN_MODES: frozenset[CheckerMode] = frozenset({"identity"})

# Modes whose ERROR drives UNCERTAIN. Containment ERROR is record-only (checker docstring).
_ERROR_DECISION_MODES: frozenset[CheckerMode] = frozenset({
    "contradicts",
    "healthy",
    "not_authentic",
    "incomplete",
    "identity",
})

__all__ = [
    "decision_from_state",
    "human_in_the_loop_provenance",
    "predicted_answer_decision",
    "resolved_human_in_the_loop",
    "violated_checkers",
]


class _DecisionGate(NamedTuple):
    """One ordered fold gate: predicate over state → GroundTruth when true."""

    applies: Callable[[], bool]
    outcome: Callable[[], GroundTruth]


def decision_from_state(
    state: ClaimAnalysisState,
    *,
    analysis: AnalysisConfig,
    ocr_failure_reason: str | None,
) -> GroundTruth:
    """Derive APPROVE/DENY/UNCERTAIN for evaluator-facing predicted_answer.

    Precedence (locked, SR-008):
    1. Supplied OCR-failure reason → UNCERTAIN (explanation is the reason)
    2. Routed coverage abstention → UNCERTAIN ``coverage_false_label``
    3. ``departure_within_days`` → UNCERTAIN
    4. ``checker_suspicious_dating`` → UNCERTAIN
    5. Any VIOLATION (checker or missing-doc / signature) → DENY
    6. Any ERROR (except containment) → UNCERTAIN ``checker_error:<modes>``
    7. Identity ABSTAIN → UNCERTAIN ``identity_unclear``
    8. APPROVE ``checker_consistent``

    :param state: Final graph state.
    :param analysis: Analysis stage configuration for document acceptability.
    :param ocr_failure_reason: Preprocess OCR-failure code when present; the
        caller reads metadata once and passes it in (filesystem-free fold).
    :return: GroundTruth decision written beside analysis_result.
    """

    def _deny_violations() -> GroundTruth:
        return GroundTruth(
            decision=DECISION_DENY,
            explanation=",".join(violated_checkers(state, analysis=analysis)),
        )

    def _uncertain_errors() -> GroundTruth:
        return GroundTruth(
            decision=DECISION_UNCERTAIN,
            explanation="checker_error:" + ",".join(_errored_checkers(state)),
        )

    gates: tuple[_DecisionGate, ...] = (
        _DecisionGate(
            applies=lambda: ocr_failure_reason is not None,
            outcome=lambda: GroundTruth(
                decision=DECISION_UNCERTAIN,
                explanation=ocr_failure_reason if ocr_failure_reason is not None else "",
            ),
        ),
        _DecisionGate(
            applies=lambda: state["routed_coverage"].branch == "abstention",
            outcome=lambda: GroundTruth(decision=DECISION_UNCERTAIN, explanation="coverage_false_label"),
        ),
        _DecisionGate(
            applies=lambda: bool(state.get("departure_within_days")),
            outcome=lambda: GroundTruth(decision=DECISION_UNCERTAIN, explanation="departure_within_days"),
        ),
        _DecisionGate(
            applies=lambda: bool(state.get("checker_suspicious_dating")),
            outcome=lambda: GroundTruth(decision=DECISION_UNCERTAIN, explanation="checker_suspicious_dating"),
        ),
        _DecisionGate(
            applies=lambda: bool(violated_checkers(state, analysis=analysis)),
            outcome=_deny_violations,
        ),
        _DecisionGate(
            applies=lambda: bool(_errored_checkers(state)),
            outcome=_uncertain_errors,
        ),
        _DecisionGate(
            applies=lambda: _identity_abstain_unclear(state),
            outcome=lambda: GroundTruth(decision=DECISION_UNCERTAIN, explanation="identity_unclear"),
        ),
    )
    for gate in gates:
        if gate.applies():
            return gate.outcome()
    return GroundTruth(decision=DECISION_APPROVE, explanation="checker_consistent")


def predicted_answer_decision(
    state: ClaimAnalysisState,
    *,
    analysis: AnalysisConfig,
    ocr_failure_reason: str | None,
) -> GroundTruth:
    """Build evaluator GroundTruth from analysis decision + resolved HITL.

    :param state: Final ClaimAnalysisState after checker (or coverage-only).
    :param analysis: Analysis stage configuration.
    :param ocr_failure_reason: Preprocess OCR-failure code when present.
    :return: Decision with ``human_in_the_loop`` set (``source`` stamped on write).
    """
    return decision_from_state(state, analysis=analysis, ocr_failure_reason=ocr_failure_reason).model_copy(
        update={
            "human_in_the_loop": resolved_human_in_the_loop(
                state,
                analysis=analysis,
                ocr_failure_reason=ocr_failure_reason,
            ),
        },
    )


def resolved_human_in_the_loop(
    state: ClaimAnalysisState,
    *,
    analysis: AnalysisConfig,
    ocr_failure_reason: str | None,
) -> bool:
    """HITL from preprocess, classifier ``False``, or any UNCERTAIN decision.

    Checker gates that emit UNCERTAIN (suspicious dating, far departure,
    identity unclear, coverage abstention, OCR failure) always require
    operator review — same as classifier abstention.

    :param state: Final (or mid-pipeline) graph state.
    :param analysis: Analysis stage configuration.
    :param ocr_failure_reason: Preprocess OCR-failure code when present.
    :return: Whether a human should review the claim.
    """
    if bool(state.get("human_in_the_loop")):
        return True
    if _classifier_returned_false(state):
        return True
    return (
        decision_from_state(state, analysis=analysis, ocr_failure_reason=ocr_failure_reason).decision
        == DECISION_UNCERTAIN
    )


def human_in_the_loop_provenance(
    state: ClaimAnalysisState,
    *,
    analysis: AnalysisConfig,
    ocr_failure_reason: str | None,
) -> str:
    """Return the stable source code that drove HITL for this run.

    Check order (first match wins): ``classifier_false`` when the routed
    coverage or a raw reason/document label is the confident-negative;
    ``preprocess_metadata`` when the flag came in from the metadata read;
    ``uncertain_decision`` when the decision resolves to UNCERTAIN; else
    ``none``.

    :param state: Final graph state after checker (or coverage-only).
    :param analysis: Analysis stage configuration.
    :param ocr_failure_reason: Preprocess OCR-failure code when present.
    :return: One of ``classifier_false``, ``preprocess_metadata``,
        ``uncertain_decision``, or ``none``.
    """
    if _classifier_returned_false(state):
        return "classifier_false"
    if bool(state.get("human_in_the_loop")):
        return "preprocess_metadata"
    if (
        decision_from_state(state, analysis=analysis, ocr_failure_reason=ocr_failure_reason).decision
        == DECISION_UNCERTAIN
    ):
        return "uncertain_decision"
    return "none"


def violated_checkers(state: ClaimAnalysisState, *, analysis: AnalysisConfig) -> list[str]:
    """Return checker / rule keys that failed for the claim.

    Missing documentation is document-type acceptability for the claim path —
    not failed containment (certs rarely contain the claim letter).
    Checker VIOLATIONs are read from ``checker_outcomes`` when present
    (SR-008); otherwise legacy boolean keys are used (date early-exit path).
    ``signature_check`` False means a medical certificate / hospital admission
    lacks ``has_signature`` in ``document_metadata.json`` → DENY.

    :param state: Final graph state after Checker (or coverage-only).
    :param analysis: Analysis stage configuration.
    :return: Ordered list of violated keys that drive DENY.
    """
    violated: list[str] = []
    if is_missing_documentation(state, analysis=analysis):
        violated.append("checker_missing_documentation")
    violated.extend(_checker_violation_keys(state))
    if "signature_check" in state and not bool(state["signature_check"]):
        violated.append("signature_check")
    return _ordered_violated_keys(violated)


def _classifier_returned_false(state: ClaimAnalysisState) -> bool:
    """True when the routed coverage label is ``False``, or a raw reason/document label is.

    Coverage follows the routed winner (P-01): a losing ``False`` in the
    coverage selection has no HITL side effect. Reason and document stages
    keep raw membership (SR-010/SR-004 out-of-scope precedence unchanged).

    :param state: Graph state with routed_coverage and reason/document label codes.
    :return: Whether the routed coverage label, or a raw reason/document
        label, is the confident-negative ``False``.
    """
    if state["routed_coverage"].label == "False":
        return True
    return any("False" in labels for labels in (state.get("reason_labels") or [], state.get("document_labels") or []))


def _checker_violation_keys(state: ClaimAnalysisState) -> list[str]:
    """Legacy DENY keys for checker VIOLATIONs (or legacy bool fallback).

    :param state: Graph state with optional ``checker_outcomes``.
    :return: Unordered DENY explanation keys from checker modes.
    """
    outcomes = state.get("checker_outcomes") or {}
    if outcomes:
        return [key for mode, key in _VIOLATION_LEGACY_KEYS if outcomes.get(mode) is CheckOutcome.VIOLATION]
    keys: list[str] = []
    if "identity_check" in state and not bool(state["identity_check"]) and not bool(state.get("identity_unclear")):
        keys.append("identity_check")
    if "healthy_check" in state and bool(state["healthy_check"]):
        keys.append("healthy_check")
    if "checker_document_not_authentic" in state and bool(state["checker_document_not_authentic"]):
        keys.append("checker_document_not_authentic")
    if "checker_incomplete_document" in state and bool(state["checker_incomplete_document"]):
        keys.append("checker_incomplete_document")
    if "checker_contradicts" in state and bool(state["checker_contradicts"]):
        keys.append("checker_contradicts")
    return keys


def _ordered_violated_keys(violated: list[str]) -> list[str]:
    """Stable DENY explanation key order (matches historical fold).

    :param violated: Unordered or partially ordered violated keys.
    :return: Keys filtered to the canonical order, preserving only those present.
    """
    order = (
        "checker_missing_documentation",
        "identity_check",
        "signature_check",
        "healthy_check",
        "checker_document_not_authentic",
        "checker_incomplete_document",
        "checker_contradicts",
    )
    present = set(violated)
    return [key for key in order if key in present]


def _errored_checkers(state: ClaimAnalysisState) -> list[str]:
    """Modes whose ERROR should drive UNCERTAIN (excludes containment).

    :param state: Graph state with optional ``checker_outcomes``.
    :return: Errored mode names in recorded (insertion) order.
    """
    outcomes = state.get("checker_outcomes") or {}
    return [
        mode for mode, outcome in outcomes.items() if outcome is CheckOutcome.ERROR and mode in _ERROR_DECISION_MODES
    ]


def _identity_abstain_unclear(state: ClaimAnalysisState) -> bool:
    """Whether identity ABSTAIN should yield UNCERTAIN ``identity_unclear``.

    :param state: Graph state with optional ``checker_outcomes`` / legacy flags.
    :return: True when identity abstained (or legacy identity_unclear is set).
    """
    outcomes = state.get("checker_outcomes") or {}
    if outcomes:
        return any(
            mode in _ABSTAIN_UNCERTAIN_MODES and outcome is CheckOutcome.ABSTAIN for mode, outcome in outcomes.items()
        )
    return "identity_unclear" in state and bool(state["identity_unclear"])
