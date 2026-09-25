from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from pydantic import BaseModel, Field

from compliance.config.settings import AppConfig, load_config
from evaluation.evaluator import EvaluationResult, Evaluator

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
    """Load config, run batch evaluation, and write metrics JSON.

    :param argv: Optional CLI arguments; defaults to ``sys.argv[1:]``.
    :return: ``0`` on success; ``2`` when the config file is missing.
    """
    args = _cli_args(argv)
    try:
        config = load_config(args.config)
    except FileNotFoundError:
        logger.error("Config file not found: %s", args.config)
        return 2
    _configure_logging(config)
    result = Evaluator(config).evaluate()
    metrics_path = _write_metrics(config, result)
    logger.info(
        "evaluation complete n_evaluated=%d accuracy=%.4f f1_macro=%.4f path=%s",
        result.n_evaluated,
        result.accuracy,
        result.f1_macro,
        metrics_path,
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


def _configure_logging(config: AppConfig) -> None:
    level_name = config.logging.level.upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(level=level, format=config.logging.format)


def _write_metrics(config: AppConfig, result: EvaluationResult) -> Path:
    """Serialize aggregate metrics under results_dir (A13).

    :param config: Application config with results_dir and metrics_artifact.
    :param result: Aggregate EvaluationResult from batch evaluate.
    :return: Path of the written metrics JSON file.
    """
    results_dir = Path(config.preprocessing.results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    path = results_dir / config.evaluation.metrics_artifact
    payload = {
        "claim_ids": result.claim_ids,
        "labels": result.labels,
        "confusion_matrix": result.confusion_matrix,
        "accuracy": result.accuracy,
        "f1_macro": result.f1_macro,
        "n_evaluated": result.n_evaluated,
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


if __name__ == "__main__":
    raise SystemExit(main())
