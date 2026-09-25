from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from pydantic import BaseModel

from compliance.models.claim import BookingData
from compliance.preprocessing.extractor import InformationExtractor
from compliance.preprocessing.preprocessing import Preprocessor
from compliance.preprocessing.reader import Reader

_MISSING = np.nan


class DescriptionPreprocessor(Preprocessor):
    """Extract BookingData from free-text descriptions via InformationExtractor."""

    def __init__(self, extractor: InformationExtractor) -> None:
        """Attach the extractor used during preprocess.

        :param extractor: InformationExtractor targeting BookingData.
        """
        self.extractor = extractor

    def preprocess(self, raw: Any) -> dict[str, Any]:
        """Run LLM extraction on description text.

        :param raw: UTF-8 description letter text.
        :return: Dict of BookingData fields (missing → np.nan).
        :raises TypeError: If raw is not a string.
        """
        if not isinstance(raw, str):
            msg = f"Description content must be str, got {type(raw).__name__}"
            raise TypeError(msg)

        model = self.extractor.extract(raw)
        return model.model_dump()


class DescriptionReader(Reader):
    """Read description.txt into BookingData via config-driven LLM extraction."""

    def __init__(
        self,
        extractor: InformationExtractor,
        preprocessor: Preprocessor | None = None,
    ) -> None:
        """Create a reader that extracts BookingData from description text.

        :param extractor: InformationExtractor configured for BookingData.
        :param preprocessor: Optional override; defaults to DescriptionPreprocessor.
        """
        super().__init__(preprocessor or DescriptionPreprocessor(extractor))
        self.extractor = extractor
        self.last_raw_text: str | float = _MISSING

    def _load(self, path: Path) -> Any:
        """Read description.txt and retain raw text for ClaimBundle.

        :param path: Path to description.txt.
        :return: UTF-8 text contents.
        """
        text = path.read_text(encoding="utf-8")
        self.last_raw_text = text
        return text

    def _to_model(self, processed: Any) -> BaseModel:
        """Build BookingData from extracted fields.

        :param processed: Dict of BookingData field values.
        :return: BookingData instance.
        """
        fields = {name: _MISSING for name in BookingData.model_fields}
        fields.update(processed)
        return BookingData.model_validate(fields)
