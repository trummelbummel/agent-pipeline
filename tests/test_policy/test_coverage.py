from __future__ import annotations

import pytest

from compliance.config.settings import CoverageClassificationConfig
from compliance.llm.classifier import ClassificationResult
from compliance.policy.coverage import RoutedCoverage, route_coverage


def test_route_coverage_selection_order_independent(
    coverage_config: CoverageClassificationConfig,
) -> None:
    """["1","2"] and ["2","1"] with the same probabilities yield the same route."""
    probabilities = {"1": 0.4, "2": 0.8}
    forward = route_coverage(
        ClassificationResult(labels=["1", "2"], probabilities=probabilities),
        coverage_config,
    )
    reverse = route_coverage(
        ClassificationResult(labels=["2", "1"], probabilities=probabilities),
        coverage_config,
    )
    assert forward == reverse == RoutedCoverage(branch="personal_effects", label="2")


def test_route_coverage_positive_vs_abstention_by_probability(
    coverage_config: CoverageClassificationConfig,
) -> None:
    """A positive and an abstention label resolve by probability (SR-004 D-02)."""
    abstention_wins = route_coverage(
        ClassificationResult(
            labels=["False", "1"],
            probabilities={"False": 0.7, "1": 0.3},
        ),
        coverage_config,
    )
    assert abstention_wins == RoutedCoverage(branch="abstention", label="False")

    positive_wins = route_coverage(
        ClassificationResult(
            labels=["1", "False"],
            probabilities={"False": 0.3, "1": 0.7},
        ),
        coverage_config,
    )
    assert positive_wins == RoutedCoverage(branch="cancellation", label="1")


def test_route_coverage_tie_breaks_by_config_order(
    coverage_config: CoverageClassificationConfig,
) -> None:
    """Exact probability ties break by config order; positive beats abstention."""
    positive_tie = route_coverage(
        ClassificationResult(
            labels=["3", "2"],
            probabilities={"2": 0.5, "3": 0.5},
        ),
        coverage_config,
    )
    assert positive_tie == RoutedCoverage(branch="personal_effects", label="2")

    positive_beats_abstention = route_coverage(
        ClassificationResult(
            labels=["False", "3"],
            probabilities={"False": 0.5, "3": 0.5},
        ),
        coverage_config,
    )
    assert positive_beats_abstention == RoutedCoverage(branch="missed_departure", label="3")


def test_route_coverage_missing_probability_counts_as_zero(
    coverage_config: CoverageClassificationConfig,
) -> None:
    """A selected label absent from the probability map counts as 0.0 (D-06)."""
    routed = route_coverage(
        ClassificationResult(labels=["1", "3"], probabilities={"3": 0.2}),
        coverage_config,
    )
    assert routed == RoutedCoverage(branch="missed_departure", label="3")


def test_route_coverage_unmapped_label_abstains(
    coverage_config: CoverageClassificationConfig,
) -> None:
    """A winning label outside the configured branches map routes to abstention."""
    routed = route_coverage(
        ClassificationResult(labels=["99"], probabilities={"99": 0.9}),
        coverage_config,
    )
    assert routed == RoutedCoverage(branch="abstention", label="99")


@pytest.mark.parametrize(
    ("labels", "probabilities", "branch", "label"),
    [
        (["2", "3"], {"2": 0.4, "3": 0.8}, "missed_departure", "3"),
        (["1", "2"], {"1": 0.8, "2": 0.4}, "cancellation", "1"),
    ],
)
def test_route_coverage_highest_probability_wins(
    coverage_config: CoverageClassificationConfig,
    labels: list[str],
    probabilities: dict[str, float],
    branch: str,
    label: str,
) -> None:
    """Highest-probability selected label and its configured branch win."""
    routed = route_coverage(
        ClassificationResult(labels=labels, probabilities=probabilities),
        coverage_config,
    )
    assert routed == RoutedCoverage(branch=branch, label=label)  # type: ignore[arg-type]
