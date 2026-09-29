from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from compliance.config.logging_setup import configure_logging
from compliance.config.settings import AppConfig, load_config
from compliance.preprocessing.claim_batch import _validate_claim_dir_name, _validate_claim_root
from compliance.workflows.artifact_publication import ClaimAnalysisBusyError
from compliance.workflows.claim_pipeline import ClaimPipeline
from compliance.workflows.orchestration import analyze_claim_exclusively
from compliance.workflows.pipeline import PreprocessingPipeline

logger = logging.getLogger(__name__)

CliMode = Literal["preprocess", "analyze", "both"]


class CliArgs(BaseModel):
    """CLI arguments for preprocess and claim-analysis entrypoints.

    :param config: Path to application YAML config.
    :param mode: Workflow to run — preprocess, analyze, or both (default preprocess).
    :param claim_id: Optional single claim folder segment under data_dir for an
        exclusive end-to-end ``analyze_claim_exclusively`` run (R020 / SR-007).
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
        description="Optional claim folder under data_dir; must be a real directory (not a symlink)",
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
        help="Single claim folder under data_dir (real directory, not a symlink); exclusive analyze",
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
    """Resolve ``claim_id`` under data_dir and run exclusive analyze_claim_exclusively.

    The claim root must be a real directory inside ``data_dir`` (not a symlink).

    :param config: Loaded application configuration.
    :param claim_id: Safe claim folder segment (validated before join).
    :return: ``0`` on success; ``1`` when the claim folder is unsafe, a symlink, or busy.
    """
    data_dir = Path(config.preprocessing.data_dir)
    try:
        # Validate the raw segment before Path join — Path.name drops separators.
        _validate_claim_dir_name(claim_id)
        claim_dir = data_dir / claim_id
        _validate_claim_root(claim_dir, root=data_dir)
    except ValueError:
        logger.exception("Unsafe claim id rejected: %s", claim_id)
        return 1
    try:
        analyze_claim_exclusively(
            claim_dir,
            PreprocessingPipeline(config),
            ClaimPipeline(config),
        )
    except ClaimAnalysisBusyError:
        logger.exception("Analysis already in progress for claim id: %s", claim_id)
        return 1
    logger.info("Single-claim analyze_claim_exclusively complete (%s)", claim_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
