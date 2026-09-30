"""Check runner and legacy-boolean mapping (SR-008).

Pure over claim texts + rule set + prebuilt gates and check suite:
deterministic date gates first, then the suite's selected checks in fixed
order. No filesystem.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import NamedTuple

from compliance.claim_dates import _reference_today
from compliance.llm.checks import CheckContext, CheckerMode, CheckOutcome, CheckSuite
from compliance.policy.gates import Gate
from compliance.policy.rules import CheckerRuleSet

# Containment and contradicts are never gated (P-06).
_UNGATED_MODES: frozenset[CheckerMode] = frozenset({"containment", "contradicts"})
_GATED_MODES: frozenset[CheckerMode] = frozenset({"identity", "healthy", "incomplete"})

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
    :param outcomes: Per-mode ``CheckOutcome`` for every check that ran
        (empty when a date gate short-circuits before any check runs).
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

    Polarity is already resolved inside each check; this only maps outcome →
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
    context: CheckContext,
    rule_set: CheckerRuleSet,
    gates: Sequence[Gate],
    suite: CheckSuite,
) -> CheckerRunResult:
    """Run applicable date gates, then the suite's selected checks.

    A gate is evaluated only when its name is in ``rule_set.applicable``. When
    any gate fires, returns early without calling any check — ``outcomes``
    stays empty. Otherwise runs containment and contradicts plus the gated
    checks the rule set enables, in suite order.

    :param context: Claim texts (description, supporting OCR, booking).
    :param rule_set: Per-claim medical rule set gating gates and checks.
    :param gates: Date gates built once from checking config.
    :param suite: Check suite built once from checking config.
    :return: Date flags, per-mode outcomes, and derived legacy booleans.
    """
    fired = _fired_gates(context, rule_set=rule_set, gates=gates)
    if fired:
        return CheckerRunResult(
            departure_within_days="departure" in fired,
            suspicious_dating="suspicious_dating" in fired,
            outcomes={},
            legacy_booleans={},
        )

    modes = _UNGATED_MODES | (_GATED_MODES & rule_set.applicable)
    outcomes = suite.run(modes, context)
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


def _fired_gates(
    context: CheckContext,
    *,
    rule_set: CheckerRuleSet,
    gates: Sequence[Gate],
) -> set[str]:
    """Names of applicable gates that fire for this claim.

    :param context: Claim texts.
    :param rule_set: Rule set deciding which gates apply.
    :param gates: Configured date gates.
    :return: Names of the gates that fired (empty when none).
    """
    today = _reference_today(context.booking, fallback=date.today())
    return {gate.name for gate in gates if gate.name in rule_set.applicable and gate.fires(context, today=today)}
