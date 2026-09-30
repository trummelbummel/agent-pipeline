"""Document-acceptability policy for claim analysis.

Pure: analysis config + state labels in; acceptable codes / missing-doc verdict
out. No filesystem.
"""

from __future__ import annotations

from compliance.config.settings import AnalysisConfig, ClassificationConfig
from compliance.policy.coverage import RoutedCoverage
from compliance.policy.state import ClaimAnalysisState
from compliance.text_cues import DEFAULT_MEDICAL_MENTION_CUES, text_mentions_any

__all__ = [
    "acceptable_document_codes",
    "classified_document_codes",
    "description_mentions_medical",
    "document_stage_for_coverage",
    "is_missing_documentation",
]


def document_stage_for_coverage(
    analysis: AnalysisConfig,
    routed: RoutedCoverage,
) -> ClassificationConfig:
    """Pick the document-stage config for the routed coverage branch.

    :param analysis: Analysis stage configuration.
    :param routed: Single authoritative coverage routing decision.
    :return: Document ClassificationConfig for semantic name resolution
        (abstention has no document labels; it keeps today's cancellation
        fallback for label-name resolution only).
    """
    if routed.branch == "personal_effects":
        return analysis.personal_effects_document
    if routed.branch == "missed_departure":
        return analysis.missed_departure_document
    return analysis.cancellation_document


def classified_document_codes(state: ClaimAnalysisState, *, analysis: AnalysisConfig) -> set[str]:
    """Return non-abstention document codes from the document classifier stage.

    :param state: Graph state with routed coverage and document_labels.
    :param analysis: Analysis stage configuration.
    :return: Classified document codes excluding ``False`` / ``other_label``.
    """
    stage = document_stage_for_coverage(analysis, state["routed_coverage"])
    abstention = stage.abstention_labels()
    return {code for code in (state.get("document_labels") or []) if code not in abstention}


def acceptable_document_codes(state: ClaimAnalysisState, *, analysis: AnalysisConfig) -> set[str]:
    """Return document codes allowed for this claim's routed coverage path.

    On missed-departure, when the claim description mentions a medical reason,
    only ``missed_departure_medical_codes`` are acceptable — proof of booking or
    an incident report alone is treated as missing medical documentation.

    :param state: Graph state with routed coverage and reason label codes.
    :param analysis: Analysis stage configuration.
    :return: Acceptable document-type codes from ``required_documents`` config
        (falls back to the document-stage label list when a mapping is empty).
    """
    required = analysis.required_documents
    routed = state["routed_coverage"]
    stage = document_stage_for_coverage(analysis, routed)
    stage_positive = set(stage.positive_labels())

    if routed.branch == "personal_effects":
        return set(required.personal_effects) or stage_positive
    if routed.branch == "missed_departure":
        return _missed_departure_acceptable_codes(state, analysis, stage_positive)
    return _cancellation_acceptable_codes(state, analysis, stage_positive)


def is_missing_documentation(state: ClaimAnalysisState, *, analysis: AnalysisConfig) -> bool:
    """True when no classified document type is acceptable for this claim.

    :param state: Final graph state after document classification.
    :param analysis: Analysis stage configuration.
    :return: Whether the supporting document type fails the required-doc check.
    """
    classified = classified_document_codes(state, analysis=analysis)
    if not classified:
        return True
    acceptable = acceptable_document_codes(state, analysis=analysis)
    return classified.isdisjoint(acceptable)


def description_mentions_medical(
    text: str,
    cues: list[str] | None = None,
) -> bool:
    """True when claim narrative cues a medical reason for the miss/cancel.

    :param text: Claim description artifact text.
    :param cues: Vocabulary from ``analysis.medical_mention_cues``; defaults to
        the built-in list when omitted (unit tests).
    :return: Whether medical / hospital / clinical language is present.
    """
    return text_mentions_any(text, cues if cues is not None else DEFAULT_MEDICAL_MENTION_CUES)


def _missed_departure_acceptable_codes(
    state: ClaimAnalysisState,
    analysis: AnalysisConfig,
    stage_positive: set[str],
) -> set[str]:
    """Acceptable missed-departure codes, narrowed when medical is mentioned.

    :param state: Graph state with ``description_text`` and document labels.
    :param analysis: Analysis stage configuration.
    :param stage_positive: Fallback codes when no required mapping is configured.
    :return: Medical-only codes when the narrative mentions medical; else the
        full missed-departure acceptable set (or stage positives).
    """
    required = analysis.required_documents
    full = set(required.missed_departure) or stage_positive
    medical_only = set(required.missed_departure_medical_codes)
    if medical_only and description_mentions_medical(
        state.get("description_text") or "",
        analysis.medical_mention_cues,
    ):
        return medical_only & full if full else medical_only
    return full


def _cancellation_acceptable_codes(
    state: ClaimAnalysisState,
    analysis: AnalysisConfig,
    stage_positive: set[str],
) -> set[str]:
    """Acceptable cancellation-document codes from the reason stage (or fallback).

    Fallback chain: reason-mapped codes, then the union of every mapping, then
    stage positives.

    :param state: Graph state with reason label codes.
    :param analysis: Analysis stage configuration.
    :param stage_positive: Fallback codes when no reason-based mapping applies.
    :return: Union of ``cancellation_by_reason`` codes for classified reasons;
        else the union of every configured reason mapping; else stage positives.
    """
    required = analysis.required_documents
    reason_abstention = analysis.cancellation_reason.abstention_labels()
    reason_codes = [code for code in (state.get("reason_labels") or []) if code not in reason_abstention]
    by_reason = required.cancellation_by_reason
    if reason_codes and by_reason:
        acceptable: set[str] = set()
        for reason in reason_codes:
            acceptable.update(by_reason.get(reason, []))
        if acceptable:
            return acceptable
    if by_reason:
        return {code for codes in by_reason.values() for code in codes}
    return stage_positive
