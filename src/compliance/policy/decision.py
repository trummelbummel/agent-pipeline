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
    ("incomplete", "checker_incomplete_document"),
    ("contradicts", "checker_contradicts"),
)

# Modes whose ABSTAIN drives UNCERTAIN (identity only; containment ABSTAIN is record-only).
_ABSTAIN_UNCERTAIN_MODES: frozenset[CheckerMode] = frozenset({"identity"})

# Modes whose ERROR drives UNCERTAIN. Containment ERROR is record-only (checker docstring).
_ERROR_DECISION_MODES: frozenset[CheckerMode] = frozenset({
    "contradicts",
    "healthy",
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


_INCOMPLETE_DENY_KEY = "checker_incomplete_document"


def decision_from_state(
    state: ClaimAnalysisState,
    *,
    analysis: AnalysisConfig,
    ocr_failure_reason: str | None,
) -> GroundTruth:
    """Derive APPROVE/DENY/UNCERTAIN for evaluator-facing predicted_answer.

    Precedence (locked, SR-008 + OCR-aware incomplete):
    1. Supplied OCR-failure reason → UNCERTAIN (explanation is the reason)
    2. Routed coverage abstention → UNCERTAIN ``coverage_false_label``
    3. ``departure_within_days`` → UNCERTAIN
    4. ``checker_suspicious_dating`` → UNCERTAIN
    5. Incomplete VIOLATION alone when OCR/YOLO already flagged HITL → UNCERTAIN
       ``checker_incomplete_document`` (soft polarity; clean OCR still DENYs)
    6. Any hard VIOLATION (checker or missing-doc / signature; incomplete
       excluded under OCR HITL) → DENY
    7. Any ERROR (except containment) → UNCERTAIN ``checker_error:<modes>``
    8. Legacy ``identity_unclear`` (identity ERROR / pre-VIOLATION unclear flag)
       → UNCERTAIN ``identity_unclear``
    9. APPROVE ``checker_consistent``

    :param state: Final graph state.
    :param analysis: Analysis stage configuration for document acceptability.
    :param ocr_failure_reason: Preprocess OCR-failure code when present; the
        caller reads metadata once and passes it in (filesystem-free fold).
    :return: GroundTruth decision written beside analysis_result.
    """
    all_violated = violated_checkers(state, analysis=analysis)
    hard_violated = _hard_deny_keys(
        all_violated,
        ocr_uncertain=_ocr_uncertain(state, ocr_failure_reason),
    )

    def _deny_violations() -> GroundTruth:
        return GroundTruth(
            decision=DECISION_DENY,
            explanation=",".join(hard_violated),
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
            applies=lambda: (
                _INCOMPLETE_DENY_KEY in all_violated and not hard_violated and _ocr_uncertain(state, ocr_failure_reason)
            ),
            outcome=lambda: GroundTruth(
                decision=DECISION_UNCERTAIN,
                explanation=_INCOMPLETE_DENY_KEY,
            ),
        ),
        _DecisionGate(
            applies=lambda: bool(hard_violated),
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
    """HITL only when preprocess OCR/YOLO already flagged uncertainty.

    Classifier abstention and analysis UNCERTAIN decisions (dating gates,
    identity unclear, coverage ``False``, checker ERROR) do **not** set HITL —
    those remain machine outcomes. Operator review is reserved for weak OCR
    (low confidence / faulty extraction / OCR failure) and uncertain YOLO
    signature verify, carried in from ``document_metadata.json``.

    :param state: Final (or mid-pipeline) graph state.
    :param analysis: Analysis stage configuration (unused; kept for call-site stability).
    :param ocr_failure_reason: Preprocess OCR-failure code when present.
    :return: Whether a human should review because OCR/YOLO was uncertain.
    """
    return bool(state.get("human_in_the_loop")) or ocr_failure_reason is not None


def human_in_the_loop_provenance(
    state: ClaimAnalysisState,
    *,
    analysis: AnalysisConfig,
    ocr_failure_reason: str | None,
) -> str:
    """Return the stable source code that drove HITL for this run.

    Only ``preprocess_metadata`` (OCR/YOLO uncertainty from the metadata read,
    or an OCR-failure reason) or ``none``. Classifier abstention and analysis
    UNCERTAIN no longer contribute.

    :param state: Final graph state after checker (or coverage-only).
    :param analysis: Analysis stage configuration (unused; kept for call-site stability).
    :param ocr_failure_reason: Preprocess OCR-failure code when present.
    :return: ``preprocess_metadata`` or ``none``.
    """
    if bool(state.get("human_in_the_loop")) or ocr_failure_reason is not None:
        return "preprocess_metadata"
    return "none"


def violated_checkers(state: ClaimAnalysisState, *, analysis: AnalysisConfig) -> list[str]:
    """Return checker / rule keys that failed for the claim.

    Missing documentation is document-type acceptability for the claim path —
    not failed containment (certs rarely contain the claim letter).
    Checker VIOLATIONs are read from ``checker_outcomes`` when present
    (SR-008); otherwise legacy boolean keys are used (date early-exit path).
    ``signature_check`` False means a medical certificate / hospital admission
    lacks ``has_signature`` in ``document_metadata.json`` → DENY.

    Includes ``checker_incomplete_document`` even when OCR-aware polarity later
    softens that key to UNCERTAIN — callers that need hard DENY keys only should
    use :func:`_hard_deny_keys`.

    :param state: Final graph state after Checker (or coverage-only).
    :param analysis: Analysis stage configuration.
    :return: Ordered list of violated keys (including softenable incomplete).
    """
    violated: list[str] = []
    if is_missing_documentation(state, analysis=analysis):
        violated.append("checker_missing_documentation")
    violated.extend(_checker_violation_keys(state))
    if "signature_check" in state and not bool(state["signature_check"]):
        violated.append("signature_check")
    return _ordered_violated_keys(violated)


def _ocr_uncertain(state: ClaimAnalysisState, ocr_failure_reason: str | None) -> bool:
    """Whether preprocess already flagged OCR/YOLO uncertainty for this run.

    :param state: Graph state carrying preprocess ``human_in_the_loop``.
    :param ocr_failure_reason: Preprocess OCR-failure code when present.
    :return: True when operator review was requested for OCR/signature quality.
    """
    return bool(state.get("human_in_the_loop")) or ocr_failure_reason is not None


def _hard_deny_keys(violated: list[str], *, ocr_uncertain: bool) -> list[str]:
    """DENY keys after OCR-aware incomplete softening.

    When OCR/YOLO is uncertain, incomplete VIOLATION is not a hard DENY — it
    alone becomes UNCERTAIN. Clean OCR keeps incomplete as DENY.

    :param violated: Full violated key list from :func:`violated_checkers`.
    :param ocr_uncertain: Whether preprocess OCR/YOLO flagged review.
    :return: Keys that still drive DENY under current OCR confidence.
    """
    if not ocr_uncertain:
        return list(violated)
    return [key for key in violated if key != _INCOMPLETE_DENY_KEY]


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
