from __future__ import annotations

from compliance.config.settings import AnalysisConfig
from compliance.llm.checker import CheckOutcome
from compliance.models.decisions import DECISION_APPROVE, DECISION_DENY, DECISION_UNCERTAIN
from compliance.policy.coverage import RoutedCoverage
from compliance.policy.decision import decision_from_state
from compliance.policy.state import ClaimAnalysisState


def _base_state(**overrides: object) -> ClaimAnalysisState:
    state: ClaimAnalysisState = {
        "claim_id": "claim-x",
        "routed_coverage": RoutedCoverage(branch="cancellation", label="1"),
        "document_labels": ["1"],
        "reason_labels": ["2"],
        "document_has_signature": True,
        "signature_check": True,
        "checker_outcomes": {
            "containment": CheckOutcome.PASS,
            "contradicts": CheckOutcome.PASS,
            "identity": CheckOutcome.PASS,
            "healthy": CheckOutcome.PASS,
            "not_authentic": CheckOutcome.PASS,
            "incomplete": CheckOutcome.PASS,
        },
        "identity_check": True,
        "identity_unclear": False,
        "checker_contradicts": False,
        "healthy_check": False,
        "checker_document_not_authentic": False,
        "checker_incomplete_document": False,
    }
    state.update(overrides)  # type: ignore[typeddict-item]
    return state


def test_ocr_reason_beats_abstention(analysis_config: AnalysisConfig) -> None:
    """Supplied OCR-failure reason beats coverage abstention."""
    state = _base_state(routed_coverage=RoutedCoverage(branch="abstention", label="False"))
    decision = decision_from_state(state, analysis=analysis_config, ocr_failure_reason="ocr_failure")
    assert decision.decision == DECISION_UNCERTAIN
    assert decision.explanation == "ocr_failure"


def test_abstention_beats_date_gates(analysis_config: AnalysisConfig) -> None:
    """Routed abstention beats departure / suspicious-dating flags."""
    state = _base_state(
        routed_coverage=RoutedCoverage(branch="abstention", label="False"),
        departure_within_days=True,
        checker_suspicious_dating=True,
    )
    decision = decision_from_state(state, analysis=analysis_config, ocr_failure_reason=None)
    assert decision.decision == DECISION_UNCERTAIN
    assert decision.explanation == "coverage_false_label"


def test_departure_within_days(analysis_config: AnalysisConfig) -> None:
    """Far-departure gate yields UNCERTAIN with departure_within_days."""
    state = _base_state(departure_within_days=True)
    decision = decision_from_state(state, analysis=analysis_config, ocr_failure_reason=None)
    assert decision.decision == DECISION_UNCERTAIN
    assert decision.explanation == "departure_within_days"


def test_suspicious_dating(analysis_config: AnalysisConfig) -> None:
    """Suspicious-dating gate yields UNCERTAIN with checker_suspicious_dating."""
    state = _base_state(checker_suspicious_dating=True)
    decision = decision_from_state(state, analysis=analysis_config, ocr_failure_reason=None)
    assert decision.decision == DECISION_UNCERTAIN
    assert decision.explanation == "checker_suspicious_dating"


def test_violation_beats_checker_error(analysis_config: AnalysisConfig) -> None:
    """A VIOLATION DENY beats an ERROR that would otherwise be UNCERTAIN."""
    state = _base_state(
        checker_outcomes={
            "containment": CheckOutcome.PASS,
            "contradicts": CheckOutcome.VIOLATION,
            "identity": CheckOutcome.ERROR,
        },
        checker_contradicts=True,
    )
    decision = decision_from_state(state, analysis=analysis_config, ocr_failure_reason=None)
    assert decision.decision == DECISION_DENY
    assert decision.explanation == "checker_contradicts"


def test_checker_error_beats_identity_abstain(analysis_config: AnalysisConfig) -> None:
    """Decision-relevant ERROR beats identity ABSTAIN."""
    state = _base_state(
        checker_outcomes={
            "containment": CheckOutcome.PASS,
            "contradicts": CheckOutcome.ERROR,
            "identity": CheckOutcome.ABSTAIN,
        },
        identity_check=False,
        identity_unclear=True,
    )
    decision = decision_from_state(state, analysis=analysis_config, ocr_failure_reason=None)
    assert decision.decision == DECISION_UNCERTAIN
    assert decision.explanation == "checker_error:contradicts"


def test_identity_abstain(analysis_config: AnalysisConfig) -> None:
    """Identity ABSTAIN alone yields UNCERTAIN identity_unclear."""
    state = _base_state(
        checker_outcomes={
            "containment": CheckOutcome.PASS,
            "contradicts": CheckOutcome.PASS,
            "identity": CheckOutcome.ABSTAIN,
        },
        identity_check=False,
        identity_unclear=True,
    )
    decision = decision_from_state(state, analysis=analysis_config, ocr_failure_reason=None)
    assert decision.decision == DECISION_UNCERTAIN
    assert decision.explanation == "identity_unclear"


def test_clean_path_approves(analysis_config: AnalysisConfig) -> None:
    """A clean medical path with no gates yields APPROVE checker_consistent."""
    decision = decision_from_state(_base_state(), analysis=analysis_config, ocr_failure_reason=None)
    assert decision.decision == DECISION_APPROVE
    assert decision.explanation == "checker_consistent"


def test_legacy_boolean_fallback_path(analysis_config: AnalysisConfig) -> None:
    """Without checker_outcomes, the fold uses legacy boolean keys (date early-exit)."""
    state = _base_state()
    del state["checker_outcomes"]
    state["checker_contradicts"] = True
    decision = decision_from_state(state, analysis=analysis_config, ocr_failure_reason=None)
    assert decision.decision == DECISION_DENY
    assert decision.explanation == "checker_contradicts"
