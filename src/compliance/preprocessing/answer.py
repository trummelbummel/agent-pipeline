from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from compliance.models.claim import _MISSING, GroundTruth
from compliance.preprocessing.preprocessing import Preprocessor
from compliance.preprocessing.reader import Reader


class AnswerPreprocessor(Preprocessor):
    """Light cleanup of answer.json dict keys before GroundTruth construction."""

    def preprocess(self, raw: Any) -> dict[str, Any]:
        """Normalize JSON object keys (strip whitespace).

        :param raw: Parsed JSON object from answer.json.
        :return: Dict with stripped string keys.
        :raises TypeError: If raw is not a mapping.
        """
        if not isinstance(raw, dict):
            msg = f"Answer JSON must be an object, got {type(raw).__name__}"
            raise TypeError(msg)
        return {str(key).strip(): value for key, value in raw.items()}


class AnswerReader(Reader):
    """Read answer.json into a GroundTruth model."""

    def __init__(self, preprocessor: Preprocessor | None = None) -> None:
        """Create a reader with an AnswerPreprocessor by default.

        :param preprocessor: Optional override; defaults to AnswerPreprocessor.
        """
        super().__init__(preprocessor or AnswerPreprocessor())

    def _load(self, path: Path) -> Any:
        """Parse answer.json from disk.

        :param path: Path to answer.json.
        :return: Parsed JSON value.
        """
        return json.loads(path.read_text(encoding="utf-8"))

    def _to_model(self, processed: Any) -> BaseModel:
        """Build GroundTruth; absent optional fields become np.nan.

        :param processed: Preprocessed answer dict.
        :return: GroundTruth instance covering all three schema variants.
        """
        data = dict(processed)
        if "explanation" not in data:
            data["explanation"] = _MISSING
        if "acceptable_decision" not in data:
            data["acceptable_decision"] = _MISSING
        return GroundTruth.model_validate(data)
