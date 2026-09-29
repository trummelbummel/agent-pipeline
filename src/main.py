from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from compliance.config.logging_setup import configure_logging
from compliance.config.settings import AppConfig, load_config
from compliance.preprocessing.claim_batch import _validate_claim_dir_name
from compliance.workflows.claim_pipeline import ClaimPipeline
from compliance.workflows.orchestration import process_then_analyze
from compliance.workflows.pipeline import PreprocessingPipeline

logger = logging.getLogger(__name__)

CliMode = Literal["preprocess", "analyze", "both"]


class CliArgs(BaseModel):
    """CLI arguments for preprocess and claim-analysis entrypoints.

    :param config: Path to application YAML config.
    :param mode: Workflow to run — preprocess, analyze, or both (default preprocess).
    :param claim_id: Optional single claim folder segment under data_dir for
        end-to-end ``process_then_analyze`` (R020).
    """

    config: str = Field(
        default="config.yaml",
        description="Path to application YAML config",
    )
    mode: CliMode = Field(
        default="preprocess",
        description="Workflow mode: preprocess, analyze, or both",
    )
    claim_id: str | None = Field(
        default=None,
        description="Optional claim folder name under data_dir for single-claim e2e",
    )


def main(argv: list[str] | None = None) -> int:
    """Load config and run the selected workflow (preprocess, analyze, or both).

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
    return _workflow_exit_code(config, mode=args.mode, claim_id=args.claim_id)


def _cli_args(argv: list[str] | None) -> CliArgs:
    parser = argparse.ArgumentParser(prog="main")
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Path to application YAML config (default: config.yaml)",
    )
    parser.add_argument(
        "--mode",
        choices=["preprocess", "analyze", "both"],
        default="preprocess",
        help="Workflow to run: preprocess, analyze, or both (default: preprocess)",
    )
    parser.add_argument(
        "--claim-id",
        default=None,
        help="Single claim folder under data_dir; runs process_then_analyze (R020)",
    )
    return CliArgs.model_validate(vars(parser.parse_args(argv)))


def _workflow_exit_code(config: AppConfig, *, mode: CliMode, claim_id: str | None = None) -> int:
    if claim_id is not None:
        return _single_claim_exit_code(config, claim_id=claim_id)
    if mode in ("preprocess", "both"):
        written = PreprocessingPipeline(config).run(None)
        logger.info("Preprocessing workflow complete (%d claims written)", len(written))
        if mode == "preprocess":
            return 0
    if mode in ("analyze", "both"):
        written = ClaimPipeline(config).run(None)
        logger.info("Analysis workflow complete (%d claims written)", len(written))
        return 0
    logger.error("Invalid mode: %s", mode)
    return 1


def _single_claim_exit_code(config: AppConfig, *, claim_id: str) -> int:
    """Resolve ``claim_id`` under data_dir and run shared process_then_analyze.

    :param config: Loaded application configuration.
    :param claim_id: Safe claim folder segment (validated before join).
    :return: ``0`` on success; ``1`` when the claim folder name is unsafe.
    """
    try:
        _validate_claim_dir_name(claim_id)
    except ValueError:
        logger.exception("Unsafe claim id rejected: %s", claim_id)
        return 1
    claim_dir = Path(config.preprocessing.data_dir) / claim_id
    process_then_analyze(
        claim_dir,
        PreprocessingPipeline(config),
        ClaimPipeline(config),
    )
    logger.info("Single-claim process_then_analyze complete (%s)", claim_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
