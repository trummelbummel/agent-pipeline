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
from compliance.policy.rules import CheckerRuleSet, GatedCheck, rule_set_for_claim
from compliance.policy.state import ClaimAnalysisState

__all__ = [
    "CheckerRuleSet",
    "CheckerRunResult",
    "ClaimAnalysisState",
    "CoverageBranch",
    "GatedCheck",
    "RoutedCoverage",
    "checker_state_updates",
    "legacy_booleans_from_outcomes",
    "route_coverage",
    "rule_set_for_claim",
    "run_checks",
]
