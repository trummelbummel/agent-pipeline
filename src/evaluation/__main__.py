from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from pydantic import BaseModel, Field

from compliance.config.logging_setup import configure_logging
from compliance.config.settings import AppConfig, load_config
from evaluation.analysis_stats import AnalysisStats, aggregate_analysis_stats
from evaluation.evaluator import EvaluationResult, Evaluator, MetricSet
from evaluation.visualization import write_analysis_stats_png, write_confusion_matrix_png

logger = logging.getLogger(__name__)


class CliArgs(BaseModel):
    """CLI arguments for the evaluation entrypoint.

    :param config: Path to application YAML config.
    """

    config: str = Field(
        default="config.yaml",
        description="Path to application YAML config",
    )


def main(argv: list[str] | None = None) -> int:
    """Load config, run batch evaluation, and write metrics JSON + visualization PNG.

    :param argv: Optional CLI arguments; defaults to ``sys.argv[1:]``.
    :return: ``0`` on success; ``2`` when the config file is missing.
    """
    args = _cli_args(argv)
    try:
        config = load_config(args.config)
    except FileNotFoundError:
        logger.exception("Config file not found: %s", args.config)
        return 2
    configure_logging(config)
    result = Evaluator(config).evaluate()
    stats = aggregate_analysis_stats(config)
    metrics_path, matrix_path, viz_path, stats_path, analysis_viz_path = _write_artifacts(config, result, stats)
    logger.info(
        "evaluation complete n_ground_truth=%d n_scored=%d coverage_rate=%.4f "
        "raw_accuracy=%.4f policy_accuracy=%.4f hitl_true=%d hitl_false=%d "
        "n_analysis_stats=%d metrics=%s confusion_matrix=%s visualization=%s "
        "analysis_stats=%s analysis_visualization=%s",
        result.population.n_ground_truth,
        result.population.n_scored,
        result.population.coverage_rate,
        result.raw.accuracy,
        result.policy.accuracy,
        result.human_in_the_loop_true,
        result.human_in_the_loop_false,
        stats.n_claims,
        metrics_path,
        matrix_path,
        viz_path,
        stats_path,
        analysis_viz_path,
    )
    return 0


def _cli_args(argv: list[str] | None) -> CliArgs:
    parser = argparse.ArgumentParser(prog="evaluation")
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Path to application YAML config (default: config.yaml)",
    )
    return CliArgs.model_validate(vars(parser.parse_args(argv)))


def _labeled_confusion_matrix(
    matrix: list[list[int]],
    row_labels: list[str],
    column_labels: list[str],
) -> dict[str, dict[str, int]]:
    """Map nested matrix counts onto true x predicted label keys.

    :param matrix: Counts with ``len(row_labels)`` rows and ``len(column_labels)`` cols.
    :param row_labels: Ground-truth axis labels.
    :param column_labels: Predicted axis labels (labels plus unscored column).
    :return: ``{true_label: {pred_label: count}}`` in axis order.
    """
    return {
        true_label: {pred_label: matrix[i][j] for j, pred_label in enumerate(column_labels)}
        for i, true_label in enumerate(row_labels)
    }


def _metric_block(
    metric: MetricSet,
    row_labels: list[str],
    column_labels: list[str],
) -> dict[str, object]:
    """Serialize one named MetricSet for the metrics / matrix artifacts.

    :param metric: Named matrix-derived metric set.
    :param row_labels: Ground-truth axis.
    :param column_labels: Predicted axis including the unscored column.
    :return: JSON-ready metric block.
    """
    return {
        "accuracy": metric.accuracy,
        "f1_macro": metric.f1_macro,
        "n": metric.n,
        "confusion_matrix": metric.confusion_matrix,
        "confusion_matrix_labeled": _labeled_confusion_matrix(metric.confusion_matrix, row_labels, column_labels),
    }


def _population_dict(result: EvaluationResult) -> dict[str, object]:
    """Flatten EvaluationPopulation for the metrics artifact.

    :param result: Aggregate evaluation result.
    :return: Population counts including coverage_rate.
    """
    pop = result.population
    return {
        "n_ground_truth": pop.n_ground_truth,
        "n_scored": pop.n_scored,
        "n_missing_prediction": pop.n_missing_prediction,
        "n_invalid_prediction": pop.n_invalid_prediction,
        "n_invalid_ground_truth": pop.n_invalid_ground_truth,
        "n_unmatched_prediction": pop.n_unmatched_prediction,
        "coverage_rate": pop.coverage_rate,
    }


def _outcomes_payload(result: EvaluationResult) -> list[dict[str, object]]:
    """Compact per-claim outcome objects for the metrics artifact.

    :param result: Aggregate evaluation with typed outcomes.
    :return: List of compact outcome dicts (no narrative claim text).
    """
    return [
        {
            "claim_id": outcome.claim_id,
            "status": outcome.status.value,
            "ground_truth": outcome.ground_truth,
            "prediction": outcome.prediction,
            "reason": outcome.reason,
        }
        for outcome in result.outcomes
    ]


def _write_artifacts(
    config: AppConfig,
    result: EvaluationResult,
    stats: AnalysisStats,
) -> tuple[Path, Path, Path, Path, Path]:
    """Serialize metrics, matrix, confusion PNG, analysis stats JSON, and bar PNG.

    :param config: Application config with results_dir and evaluation artifact names.
    :param result: Aggregate EvaluationResult from batch evaluate.
    :param stats: Aggregated analysis_result statistics for the same results_dir.
    :return: ``(metrics, matrix, confusion_png, stats_json, analysis_png)`` paths.
    """
    results_dir = Path(config.preprocessing.results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    column_labels = [*result.labels, result.unscored_label]
    raw_block = _metric_block(result.raw, result.labels, column_labels)
    policy_block = _metric_block(result.policy, result.labels, column_labels)
    metrics_path = results_dir / config.evaluation.metrics_artifact
    metrics_payload = {
        "claim_ids": result.claim_ids,
        "labels": result.labels,
        "column_labels": column_labels,
        "population": _population_dict(result),
        "raw": raw_block,
        "policy": policy_block,
        "human_in_the_loop_true": result.human_in_the_loop_true,
        "human_in_the_loop_false": result.human_in_the_loop_false,
        "outcomes": _outcomes_payload(result),
    }
    metrics_path.write_text(json.dumps(metrics_payload, indent=2) + "\n", encoding="utf-8")
    matrix_path = results_dir / config.evaluation.confusion_matrix_artifact
    matrix_payload = {
        "labels": result.labels,
        "column_labels": column_labels,
        "rows": "true_label",
        "cols": "predicted_label",
        "raw": {
            "matrix": result.raw.confusion_matrix,
            "labeled": raw_block["confusion_matrix_labeled"],
        },
        "policy": {
            "matrix": result.policy.confusion_matrix,
            "labeled": policy_block["confusion_matrix_labeled"],
        },
    }
    matrix_path.write_text(json.dumps(matrix_payload, indent=2) + "\n", encoding="utf-8")
    viz_path = write_confusion_matrix_png(result, results_dir / config.evaluation.visualization_artifact)
    stats_path = results_dir / config.evaluation.analysis_stats_artifact
    stats_path.write_text(json.dumps(stats.to_dict(), indent=2) + "\n", encoding="utf-8")
    analysis_viz_path = write_analysis_stats_png(stats, results_dir / config.evaluation.analysis_visualization_artifact)
    return metrics_path, matrix_path, viz_path, stats_path, analysis_viz_path


if __name__ == "__main__":
    raise SystemExit(main())
