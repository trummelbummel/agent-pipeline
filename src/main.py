from __future__ import annotations

import argparse
import logging
from typing import Literal

from pydantic import BaseModel, Field

from compliance.config.settings import AppConfig, load_config
from compliance.workflows.claim_pipeline import ClaimPipeline
from compliance.workflows.pipeline import PreprocessingPipeline

logger = logging.getLogger(__name__)

CliMode = Literal["preprocess", "analyze"]


class CliArgs(BaseModel):
    """CLI arguments for preprocess and claim-analysis entrypoints.

    :param config: Path to application YAML config.
    :param mode: Workflow to run — preprocess (default) or analyze.
    """

    config: str = Field(
        default="config.yaml",
        description="Path to application YAML config",
    )
    mode: CliMode = Field(
        default="preprocess",
        description="Workflow mode: preprocess or analyze",
    )


def main(argv: list[str] | None = None) -> int:
    """Load config and run the selected workflow (preprocess or analyze).

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
    return _workflow_exit_code(config, mode=args.mode)


def _configure_logging(config: AppConfig) -> None:
    level_name = config.logging.level.upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(level=level, format=config.logging.format)


def _cli_args(argv: list[str] | None) -> CliArgs:
    parser = argparse.ArgumentParser(prog="main")
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Path to application YAML config (default: config.yaml)",
    )
    parser.add_argument(
        "--mode",
        choices=["preprocess", "analyze"],
        default="preprocess",
        help="Workflow to run (default: preprocess)",
    )
    return CliArgs.model_validate(vars(parser.parse_args(argv)))


def _workflow_exit_code(config: AppConfig, *, mode: CliMode) -> int:
    if mode == "analyze":
        written = ClaimPipeline(config).run()
        logger.info("Analysis workflow complete (%d claims written)", len(written))
        return 0
    written = PreprocessingPipeline(config).run()
    logger.info("Preprocessing workflow complete (%d claims written)", len(written))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
