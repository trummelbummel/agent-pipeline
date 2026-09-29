"""Shared LangGraph / policy data contract for one-shot claim analysis."""

from __future__ import annotations

from typing import TypedDict

from compliance.llm.checker import CheckerMode, CheckOutcome
from compliance.policy.coverage import RoutedCoverage

__all__ = ["ClaimAnalysisState"]


class ClaimAnalysisState(TypedDict, total=False):
    """LangGraph state for one-shot claim analysis.

    :param claim_id: Safe claim folder segment (validated at analyze_claim boundary).
    :param input_root: Absolute path to the preprocessed claim folder to load from.
    :param description_text: Contents of the configured description artifact.
    :param supporting_document_text: Docling markdown for the primary supporting document.
    :param supporting_documents_text: Booking/internal markdown artifact text.
    :param coverage_labels: Raw labels from the coverage classifier stage
        (selection order; not the routing decision).
    :param coverage_probabilities: Per-label probability estimates from the
        coverage classifier stage, keyed by coverage code.
    :param routed_coverage: Single authoritative coverage routing decision
        (SR-004), computed once in ``_classify_coverage_node`` from
        ``coverage_labels`` + ``coverage_probabilities``. Every branch-specific
        rule reads this instead of the raw coverage label list.
    :param reason_labels: Labels from the cancellation-reason stage.
    :param document_labels: Labels from the cancellation-document stage.
    :param checker_outcomes: Per-mode ``CheckOutcome`` for every Checker mode
        that ran (SR-008). Legacy boolean keys below are derived from this map.
    :param checker_rule_set: Name of the per-claim medical rule set that ran
        (SR-010); paired with ``checker_skipped``.
    :param checker_skipped: Gated check names that did not run; a listed check
        has no recorded result (P-02).
    :param checker_containment: True when containment outcome is PASS.
    :param checker_contradicts: True when contradicts outcome is VIOLATION.
    :param identity_check: True when identity outcome is PASS, or identity was
        skipped (non-medical document).
    :param identity_unclear: True when identity outcome is ERROR (transport /
        parse failure). Missing/null patient names are VIOLATION → DENY, not unclear.
    :param document_has_signature: True when document_metadata reports has_signature.
    :param signature_check: True when signature requirement passes; absent when
        the signature check is skipped.
    :param healthy_check: True when healthy outcome is VIOLATION; absent when
        the healthy check is skipped.
    :param checker_incomplete_document: True when incomplete outcome is VIOLATION
        (medical/hospital docs only).
    :param departure_within_days: True on the medical path when an upcoming
        departure is farther than the configured day window ahead of today
        (deterministic UNCERTAIN — recovery / ability-to-fly still unclear);
        absent when the departure check is skipped.
    :param checker_suspicious_dating: True when OCR dating is implausible
        (year skew vs reference today, or issue/stamp before care window);
        absent when the suspicious-dating check is skipped.
    :param human_in_the_loop: True when OCR/YOLO metadata already flagged review for
        this run's inputs (low confidence, faulty extraction, OCR failure, or
        uncertain signature verify). Analysis UNCERTAIN / classifier ``False`` do
        not set this flag — provenance on published artifacts is
        ``preprocess_metadata`` or ``none``.
    :param run_id: Generation id stamped into every artifact published for this
        claim in the current run.
    """

    claim_id: str
    input_root: str
    description_text: str
    supporting_document_text: str
    supporting_documents_text: str
    coverage_labels: list[str]
    coverage_probabilities: dict[str, float]
    routed_coverage: RoutedCoverage
    reason_labels: list[str]
    document_labels: list[str]
    checker_outcomes: dict[CheckerMode, CheckOutcome]
    checker_rule_set: str
    checker_skipped: list[str]
    checker_containment: bool
    checker_contradicts: bool
    identity_check: bool
    identity_unclear: bool
    document_has_signature: bool
    signature_check: bool
    healthy_check: bool
    checker_incomplete_document: bool
    departure_within_days: bool
    checker_suspicious_dating: bool
    human_in_the_loop: bool
    run_id: str
