"""Analysis policy: pure functions over claim state (coverage, rules, decisions).

``ClaimPipeline`` is the only production caller. Internals stay module-private;
this package exports a thin ``__all__`` of the contracts and entry points the
pipeline imports.
"""

from __future__ import annotations

from compliance.policy.coverage import CoverageBranch, RoutedCoverage, route_coverage

__all__ = [
    "CoverageBranch",
    "RoutedCoverage",
    "route_coverage",
]
