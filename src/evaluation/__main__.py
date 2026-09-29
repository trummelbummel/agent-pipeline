from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from pydantic import BaseModel, Field

from compliance.config.logging_setup import configure_logging
from compliance.config.settings import AppConfig, load_config
from evaluation.analysis_stats import AnalysisStats, aggregate_analysis_stats
from evaluation.evaluator import EvaluationResult, Evaluator
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
        "evaluation complete n_evaluated=%d accuracy=%.4f f1_macro=%.4f "
        "hitl_true=%d hitl_false=%d n_analysis=%d metrics=%s confusion_matrix=%s "
        "visualization=%s analysis_stats=%s analysis_visualization=%s",
        result.n_evaluated,
        result.accuracy,
        result.f1_macro,
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


def _labeled_confusion_matrix(result: EvaluationResult) -> dict[str, dict[str, int]]:
    """Map nested matrix counts onto true x predicted label keys.

    :param result: Aggregate evaluation with ``labels`` and ``confusion_matrix``.
    :return: ``{true_label: {pred_label: count}}`` in config label order.
    """
    labels = result.labels
    return {
        true_label: {pred_label: result.confusion_matrix[i][j] for j, pred_label in enumerate(labels)}
        for i, true_label in enumerate(labels)
    }


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
    labeled = _labeled_confusion_matrix(result)
    metrics_path = results_dir / config.evaluation.metrics_artifact
    metrics_payload = {
        "claim_ids": result.claim_ids,
        "labels": result.labels,
        "confusion_matrix": result.confusion_matrix,
        "confusion_matrix_labeled": labeled,
        "accuracy": result.accuracy,
        "f1_macro": result.f1_macro,
        "n_evaluated": result.n_evaluated,
        "human_in_the_loop_true": result.human_in_the_loop_true,
        "human_in_the_loop_false": result.human_in_the_loop_false,
    }
    metrics_path.write_text(json.dumps(metrics_payload, indent=2) + "\n", encoding="utf-8")
    matrix_path = results_dir / config.evaluation.confusion_matrix_artifact
    matrix_payload = {
        "labels": result.labels,
        "rows": "true_label",
        "cols": "predicted_label",
        "matrix": result.confusion_matrix,
        "labeled": labeled,
    }
    matrix_path.write_text(json.dumps(matrix_payload, indent=2) + "\n", encoding="utf-8")
    viz_path = write_confusion_matrix_png(result, results_dir / config.evaluation.visualization_artifact)
    stats_path = results_dir / config.evaluation.analysis_stats_artifact
    stats_path.write_text(json.dumps(stats.to_dict(), indent=2) + "\n", encoding="utf-8")
    analysis_viz_path = write_analysis_stats_png(stats, results_dir / config.evaluation.analysis_visualization_artifact)
    return metrics_path, matrix_path, viz_path, stats_path, analysis_viz_path


if __name__ == "__main__":
    raise SystemExit(main())
