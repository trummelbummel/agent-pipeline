from __future__ import annotations

from compliance.config.settings import AnalysisConfig
from compliance.policy.coverage import RoutedCoverage
from compliance.policy.documents import (
    acceptable_document_codes,
    description_mentions_medical,
    is_missing_documentation,
)
from compliance.policy.state import ClaimAnalysisState


def _state(
    *,
    branch: str,
    label: str,
    document_labels: list[str],
    reason_labels: list[str] | None = None,
    description_text: str = "",
) -> ClaimAnalysisState:
    return ClaimAnalysisState(
        claim_id="claim-x",
        routed_coverage=RoutedCoverage(branch=branch, label=label),  # type: ignore[arg-type]
        document_labels=document_labels,
        reason_labels=reason_labels or [],
        description_text=description_text,
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


def test_missed_departure_full_acceptable_without_medical_mention(analysis_config: AnalysisConfig) -> None:
    """Non-medical missed-departure narrative keeps incident/booking/medical codes."""
    state = _state(
        branch="missed_departure",
        label="3",
        document_labels=["2"],
        description_text="I missed my connection due to a delay.",
    )
    assert acceptable_document_codes(state, analysis=analysis_config) == {"1", "2", "3"}
    assert is_missing_documentation(state, analysis=analysis_config) is False


def test_missed_departure_medical_mention_requires_medical_doc(analysis_config: AnalysisConfig) -> None:
    """Medical mention on missed-departure narrows acceptable to medical codes only."""
    state = _state(
        branch="missed_departure",
        label="3",
        document_labels=["2"],
        description_text=(
            "I am writing to request reimbursement for a prepaid medical appointment "
            "that I was unable to attend due to international travel."
        ),
    )
    assert acceptable_document_codes(state, analysis=analysis_config) == {"3"}
    assert is_missing_documentation(state, analysis=analysis_config) is True


def test_missed_departure_medical_mention_with_medical_doc_ok(analysis_config: AnalysisConfig) -> None:
    """Medical mention + medical supporting document is not missing documentation."""
    state = _state(
        branch="missed_departure",
        label="3",
        document_labels=["3"],
        description_text="Missed flight after a hospital visit for acute illness.",
    )
    assert acceptable_document_codes(state, analysis=analysis_config) == {"3"}
    assert is_missing_documentation(state, analysis=analysis_config) is False


def test_description_mentions_medical_keywords() -> None:
    """Keyword detector catches common medical cues and ignores unrelated text."""
    assert description_mentions_medical("prepaid medical appointment") is True
    assert description_mentions_medical("hospitalisation en urgence") is True
    assert description_mentions_medical("I missed my connection due to a delay.") is False
