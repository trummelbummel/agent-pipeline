from __future__ import annotations

from dataclasses import dataclass, field

from compliance.config.settings import AppConfig


@dataclass(frozen=True)
class AnalysisStats:
    """Aggregate statistics over analysis_result.json payloads (stub for RED)."""

    claim_ids: list[str] = field(default_factory=list)
    n_claims: int = 0
    decision_counts: dict[str, int] = field(default_factory=dict)
    checker_true_counts: dict[str, int] = field(default_factory=dict)
    checker_present_counts: dict[str, int] = field(default_factory=dict)
    checker_true_rates: dict[str, float] = field(default_factory=dict)
    coverage_label_counts: dict[str, int] = field(default_factory=dict)
    reason_label_counts: dict[str, int] = field(default_factory=dict)
    document_label_counts: dict[str, int] = field(default_factory=dict)
    decision_explanation_counts: dict[str, int] = field(default_factory=dict)


def aggregate_analysis_stats(config: AppConfig) -> AnalysisStats:
    """Aggregate analysis_result.json stats under results_dir (stub for RED).

    :param config: Application config with results_dir and artifact names.
    :return: Empty AnalysisStats until implemented.
    """
    return AnalysisStats()
