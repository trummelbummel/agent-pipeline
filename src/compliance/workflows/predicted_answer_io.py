from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from compliance.models.claim import GroundTruth

SOURCE_PREPROCESS = "preprocess"
SOURCE_ANALYSIS = "analysis"


def is_preprocess_origin_prediction(data: dict[str, Any]) -> bool:
    """Stub: treat every prediction as preprocess-origin (intentional RED)."""
    return True


def write_preprocess_predicted_answer(path: Path, prediction: GroundTruth) -> Path:
    """Stub write without source stamp (intentional RED)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(prediction.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return path


def write_analysis_predicted_answer(path: Path, payload: dict[str, Any]) -> Path:
    """Stub write without source stamp (intentional RED)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def remove_stale_preprocess_prediction(
    predicted_path: Path,
    *,
    analysis_result_path: Path,
) -> bool:
    """Stub: blind unlink like the pre-fix pipeline (intentional RED)."""
    if predicted_path.is_file():
        predicted_path.unlink()
        return True
    return False
