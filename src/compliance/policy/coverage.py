"""Single authoritative coverage router (SR-004).

Pure: config in, routing decision out — no filesystem and no LLM. Selection
order is irrelevant; the highest-probability selected label wins, with
config-order tie-break (positive labels, then ``other_label``, then ``False``).
"""

from __future__ import annotations

from typing import Literal, NamedTuple

from compliance.config.settings import CoverageClassificationConfig, CoverageRoute
from compliance.llm.classifier import ClassificationResult

CoverageBranch = CoverageRoute | Literal["abstention"]

__all__ = [
    "CoverageBranch",
    "RoutedCoverage",
    "route_coverage",
]


class RoutedCoverage(NamedTuple):
    """Single authoritative coverage routing decision (SR-004).

    :param branch: Which coverage-specific policy path this claim follows.
    :param label: The winning coverage classifier code (may be an abstention code).
    """

    branch: CoverageBranch
    label: str


def route_coverage(
    result: ClassificationResult,
    coverage: CoverageClassificationConfig,
) -> RoutedCoverage:
    """Compute the single authoritative coverage route from classifier output.

    With multiple selected labels (D-01) or a positive-vs-abstention conflict
    (D-02), the label with the highest probability wins (missing entries count
    as 0.0, D-06). Exact ties break by config order — positive labels first,
    then ``other_label``, then ``False`` (D-05) — so a positive label beats
    abstention on a tie. The winning label picks the branch; a winner outside
    the configured positive labels routes to abstention (P-03).

    :param result: Classifier output with selected labels and probabilities.
    :param coverage: Coverage stage config with branches and label vocabulary.
    :return: The routed branch and its winning coverage code.
    """
    label = _winning_coverage_label(result, coverage)
    return RoutedCoverage(branch=_coverage_branch(label, coverage), label=label)


def _winning_coverage_label(
    result: ClassificationResult,
    coverage: CoverageClassificationConfig,
) -> str:
    """Pick the highest-probability selected label, ties by config order.

    Only labels the classifier selected (``result.labels``) are candidates
    (D-04); a selected label with no probability entry counts as 0.0 (D-06).

    :param result: Classifier output; ``result.labels`` are the candidates.
    :param coverage: Coverage stage config for tie-break rank.
    :return: The winning coverage code.
    """
    rank = _coverage_label_rank(coverage)
    return min(
        result.labels,
        key=lambda label: (-result.probabilities.get(label, 0.0), rank.get(label, len(rank))),
    )


def _coverage_label_rank(coverage: CoverageClassificationConfig) -> dict[str, int]:
    """Config-order tie-break rank: positive labels, then other_label, then False.

    :param coverage: Coverage stage config whose vocabulary defines rank order.
    :return: Map from coverage code to rank (lower rank wins an exact-probability tie).
    """
    ordered: list[str] = []
    for label in [*coverage.positive_labels(), coverage.other_label, "False"]:
        if label not in ordered:
            ordered.append(label)
    return {label: index for index, label in enumerate(ordered)}


def _coverage_branch(label: str, coverage: CoverageClassificationConfig) -> CoverageBranch:
    """Map a winning coverage code to its routing branch from config (D-01).

    The branch comes from the configured ``analysis.coverage.branches`` map.
    Unmapped or abstention codes route to abstention.

    :param label: Winning coverage code from ``_winning_coverage_label``.
    :param coverage: Coverage stage config with the authoritative branches map.
    :return: The routed branch; a code outside the map abstains.
    """
    return coverage.branches.get(label, "abstention")
