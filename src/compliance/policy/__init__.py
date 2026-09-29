"""Analysis policy: pure functions over claim state (coverage, rules, decisions).

``ClaimPipeline`` is the only production caller. Internals stay module-private;
this package exports a thin ``__all__`` of the contracts and entry points the
pipeline imports.
"""

from __future__ import annotations

from compliance.policy.checks import (
    CheckerRunResult,
    checker_state_updates,
    legacy_booleans_from_outcomes,
    run_checks,
)
from compliance.policy.coverage import CoverageBranch, RoutedCoverage, route_coverage
from compliance.policy.decision import (
    decision_from_state,
    human_in_the_loop_provenance,
    predicted_answer_decision,
    resolved_human_in_the_loop,
    violated_checkers,
)
from compliance.policy.documents import (
    acceptable_document_codes,
    classified_document_codes,
    document_stage_for_coverage,
    is_missing_documentation,
)
from compliance.policy.payload import analysis_result_payload
from compliance.policy.rules import CheckerRuleSet, GatedCheck, rule_set_for_claim
from compliance.policy.state import ClaimAnalysisState

__all__ = [
    "CheckerRuleSet",
    "CheckerRunResult",
    "ClaimAnalysisState",
    "CoverageBranch",
    "GatedCheck",
    "RoutedCoverage",
    "acceptable_document_codes",
    "analysis_result_payload",
    "checker_state_updates",
    "classified_document_codes",
    "decision_from_state",
    "document_stage_for_coverage",
    "human_in_the_loop_provenance",
    "is_missing_documentation",
    "legacy_booleans_from_outcomes",
    "predicted_answer_decision",
    "resolved_human_in_the_loop",
    "route_coverage",
    "rule_set_for_claim",
    "run_checks",
    "violated_checkers",
]
