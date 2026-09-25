from __future__ import annotations

from pathlib import Path
from typing import Any

from compliance.config.settings import AppConfig


def process_claim_to_preprocessed(
    claim_dir: Path,
    output_root: Path,
    config: AppConfig,
    **reader_overrides: Any,
) -> Path:
    """Project one claim folder into a mirrored preprocessed artifact tree.

    :param claim_dir: Source claim folder path.
    :param output_root: Root directory for mirrored claim outputs.
    :param config: Application config (readers use preprocessing settings).
    :param reader_overrides: Optional injected readers for tests.
    :return: Path to the written claim output directory.
    """
    claim_out = output_root / claim_dir.name
    claim_out.mkdir(parents=True, exist_ok=True)
    return claim_out
