from __future__ import annotations

from compliance.config.settings import AnalysisConfig
from compliance.policy.coverage import RoutedCoverage
from compliance.policy.documents import acceptable_document_codes, is_missing_documentation
from compliance.policy.state import ClaimAnalysisState


def _state(
    *,
    branch: str,
    label: str,
    document_labels: list[str],
    reason_labels: list[str] | None = None,
) -> ClaimAnalysisState:
    return ClaimAnalysisState(
        claim_id="claim-x",
        routed_coverage=RoutedCoverage(branch=branch, label=label),  # type: ignore[arg-type]
        document_labels=document_labels,
        reason_labels=reason_labels or [],
    )


def test_acceptable_cancellation_reason_mapped(analysis_config: AnalysisConfig) -> None:
    """Reason-mapped cancellation codes win when the reason has a mapping."""
    state = _state(branch="cancellation", label="1", document_labels=["1"], reason_labels=["2"])
    assert acceptable_document_codes(state, analysis=analysis_config) == {"1", "4"}


def test_acceptable_cancellation_union_fallback(analysis_config: AnalysisConfig) -> None:
    """With only abstention reasons, fall back to the union of every mapping."""
    state = _state(branch="cancellation", label="1", document_labels=["2"], reason_labels=["False"])
    acceptable = acceptable_document_codes(state, analysis=analysis_config)
    assert acceptable == {"1", "2", "3", "4"}


def test_acceptable_personal_effects_stage_fallback(analysis_config: AnalysisConfig) -> None:
    """Empty PE required list would fall back to stage positives; config has codes."""
    state = _state(branch="personal_effects", label="2", document_labels=["1"])
    assert acceptable_document_codes(state, analysis=analysis_config) == {"1"}


def test_is_missing_documentation_empty_classification(analysis_config: AnalysisConfig) -> None:
    """No classified document codes means missing documentation."""
    state = _state(branch="cancellation", label="1", document_labels=["False"], reason_labels=["2"])
    assert is_missing_documentation(state, analysis=analysis_config) is True


def test_is_missing_documentation_disjoint(analysis_config: AnalysisConfig) -> None:
    """Classified codes outside the acceptable set are missing documentation."""
    state = _state(branch="cancellation", label="1", document_labels=["2"], reason_labels=["2"])
    assert is_missing_documentation(state, analysis=analysis_config) is True


def test_is_missing_documentation_acceptable(analysis_config: AnalysisConfig) -> None:
    """An intersecting acceptable code is not missing documentation."""
    state = _state(branch="cancellation", label="1", document_labels=["1"], reason_labels=["2"])
    assert is_missing_documentation(state, analysis=analysis_config) is False
