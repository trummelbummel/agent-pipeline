"""Checker runner and legacy-boolean mapping (SR-008).

Pure over texts + rule set + checking config + chat seam: deterministic date
gates first, then gated Checker modes in fixed order. No filesystem.
"""

from __future__ import annotations

from datetime import date
from typing import NamedTuple

from compliance.claim_dates import (
    _departure_beyond_days,
    _reference_today,
    _suspicious_dating,
)
from compliance.config.settings import CheckingConfig
from compliance.llm.chat import ChatFn
from compliance.llm.checker import Checker, CheckerMode, CheckOutcome
from compliance.policy.rules import CheckerRuleSet

__all__ = [
    "CheckerRunResult",
    "checker_state_updates",
    "legacy_booleans_from_outcomes",
    "run_checks",
]


class CheckerRunResult(NamedTuple):
    """Structured output of ``run_checks`` (SR-008).

    :param departure_within_days: Deterministic far-departure UNCERTAIN gate.
    :param suspicious_dating: Deterministic suspicious-dating UNCERTAIN gate.
    :param outcomes: Per-mode ``CheckOutcome`` for every LLM checker that ran
        (empty when a date gate short-circuits before constructing ``Checker``).
    :param legacy_booleans: Analysis-result-compatible booleans derived from
        ``outcomes`` (empty when outcomes are empty).
    """

    departure_within_days: bool
    suspicious_dating: bool
    outcomes: dict[CheckerMode, CheckOutcome]
    legacy_booleans: dict[str, bool]


def legacy_booleans_from_outcomes(
    outcomes: dict[CheckerMode, CheckOutcome],
) -> dict[str, bool]:
    """Derive analysis_result.json boolean keys from typed checker outcomes.

    Polarity is already resolved inside ``Checker``; this only maps outcome →
    the legacy boolean contract (P-02 / P-03 of SR-008).

    :param outcomes: Modes that actually ran, keyed by CheckerMode.
    :return: Legacy boolean flags for persistence and DENY explanations.
    """
    flags: dict[str, bool] = {}
    if "containment" in outcomes:
        flags["checker_containment"] = outcomes["containment"] is CheckOutcome.PASS
    if "contradicts" in outcomes:
        flags["checker_contradicts"] = outcomes["contradicts"] is CheckOutcome.VIOLATION
    if "identity" in outcomes:
        identity = outcomes["identity"]
        flags["identity_check"] = identity is CheckOutcome.PASS
        flags["identity_unclear"] = identity is CheckOutcome.ERROR
    else:
        flags["identity_check"] = True
        flags["identity_unclear"] = False
    if "healthy" in outcomes:
        flags["healthy_check"] = outcomes["healthy"] is CheckOutcome.VIOLATION
    if "incomplete" in outcomes:
        flags["checker_incomplete_document"] = outcomes["incomplete"] is CheckOutcome.VIOLATION
    return flags


def run_checks(
    *,
    description_text: str,
    supporting_document_text: str,
    supporting_documents_text: str,
    rule_set: CheckerRuleSet,
    checking: CheckingConfig,
    chat_fn: ChatFn | None,
) -> CheckerRunResult:
    """Run deterministic date checks, then Checker LLM modes when needed.

    Computes ``departure_within_days`` and ``suspicious_dating`` only when
    those checks are in ``rule_set.applicable`` (and departure also requires
    ``departure_uncertain_enabled``). When either flag is True, returns early
    without constructing ``Checker`` / calling chat — ``outcomes`` stays empty.

    :param description_text: Claim narrative for containment / contradicts.
    :param supporting_document_text: Medical/supporting OCR markdown.
    :param supporting_documents_text: Booking/internal markdown with ``name``.
    :param rule_set: Per-claim medical rule set gating date checks and modes.
    :param checking: Checking config (prompts, date windows, transport retry).
    :param chat_fn: Optional shared chat seam for Checker (tests).
    :return: Date flags, per-mode outcomes, and derived legacy booleans.
    """
    today = _reference_today(supporting_documents_text, fallback=date.today())
    departure_flag = (
        "departure" in rule_set.applicable
        and checking.departure_uncertain_enabled
        and _departure_beyond_days(
            supporting_documents_text=supporting_documents_text,
            description_text=description_text,
            today=today,
            within_days=checking.departure_uncertain_within_days,
        )
    )
    suspicious_dating_flag = "suspicious_dating" in rule_set.applicable and _suspicious_dating(
        supporting_document_text,
        today=today,
        max_month_delta=checking.suspicious_dating_max_month_delta,
        consider_within_years=checking.suspicious_dating_consider_within_years,
    )
    if departure_flag or suspicious_dating_flag:
        return CheckerRunResult(
            departure_within_days=departure_flag,
            suspicious_dating=suspicious_dating_flag,
            outcomes={},
            legacy_booleans={},
        )

    outcomes = _checker_outcomes(
        description_text,
        supporting_document_text,
        supporting_documents_text,
        rule_set=rule_set,
        checking=checking,
        chat_fn=chat_fn,
    )
    return CheckerRunResult(
        departure_within_days=False,
        suspicious_dating=False,
        outcomes=outcomes,
        legacy_booleans=legacy_booleans_from_outcomes(outcomes),
    )


def checker_state_updates(
    rule_set: CheckerRuleSet,
    results: CheckerRunResult,
    *,
    document_has_signature: bool,
) -> dict[str, object]:
    """Assemble run_checker state updates from the rule set and checker results.

    :param rule_set: Per-claim medical rule set that gated the run.
    :param results: Structured checker/date-gate output.
    :param document_has_signature: Preprocess signature flag for the signature gate.
    :return: Payload with rule-set trace keys and applicable result fields only.
    """
    early_uncertain = results.departure_within_days or results.suspicious_dating
    payload: dict[str, object] = {
        "checker_rule_set": rule_set.name,
        "checker_skipped": list(rule_set.skipped),
    }
    if "departure" in rule_set.applicable:
        payload["departure_within_days"] = results.departure_within_days
    if "signature" in rule_set.applicable:
        payload["signature_check"] = document_has_signature
    if results.suspicious_dating and "suspicious_dating" in rule_set.applicable:
        payload["checker_suspicious_dating"] = True
    if not early_uncertain:
        payload["checker_outcomes"] = results.outcomes
        payload.update(results.legacy_booleans)
        if "suspicious_dating" in rule_set.applicable:
            payload["checker_suspicious_dating"] = results.suspicious_dating
    return payload


def _build_checker(checking: CheckingConfig, chat_fn: ChatFn | None) -> Checker:
    """Construct a ``Checker`` from checking config and the shared chat seam.

    :param checking: Checking config for prompts and retry.
    :param chat_fn: Optional shared chat seam for tests.
    :return: Configured Checker instance for this run.
    """
    return Checker(
        model_name=checking.model,
        containment_prompt=checking.containment_prompt,
        contradicts_prompt=checking.contradicts_prompt,
        identity_prompt=checking.identity_prompt,
        healthy_prompt=checking.healthy_prompt,
        incomplete_prompt=checking.incomplete_prompt,
        chat_fn=chat_fn,
        identity_max_edit_distance=checking.identity_max_edit_distance,
        transport_retry=checking.transport_retry,
    )


def _checker_outcomes(
    description_text: str,
    supporting_document_text: str,
    supporting_documents_text: str,
    *,
    rule_set: CheckerRuleSet,
    checking: CheckingConfig,
    chat_fn: ChatFn | None,
) -> dict[CheckerMode, CheckOutcome]:
    """Run Checker modes in fixed order; record only modes that ran.

    Order: containment → contradicts → identity (optional) → healthy
    (optional) → incomplete (optional). Do not reorder — MagicMock
    side_effect sequences in tests depend on it. Containment and
    contradicts are never gated (P-06).

    :param description_text: Claim narrative text.
    :param supporting_document_text: Supporting OCR markdown.
    :param supporting_documents_text: Booking/internal markdown.
    :param rule_set: Per-claim medical rule set gating optional modes.
    :param checking: Checking config for Checker construction.
    :param chat_fn: Optional shared chat seam for tests.
    :return: Mode → CheckOutcome for every mode that executed.
    """
    checker = _build_checker(checking, chat_fn)
    outcomes: dict[CheckerMode, CheckOutcome] = {
        "containment": checker.check(description_text, supporting_document_text, mode="containment"),
        "contradicts": checker.check(description_text, supporting_document_text, mode="contradicts"),
    }
    if "identity" in rule_set.applicable:
        outcomes["identity"] = checker.check_identity(
            supporting_documents_text,
            supporting_document_text,
        )
    if "healthy" in rule_set.applicable:
        outcomes["healthy"] = checker.check(
            description_text,
            supporting_document_text,
            mode="healthy",
        )
    if "incomplete" in rule_set.applicable:
        outcomes["incomplete"] = checker.check(
            description_text,
            supporting_document_text,
            mode="incomplete",
        )
    return outcomes
