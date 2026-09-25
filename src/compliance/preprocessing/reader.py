from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from compliance.preprocessing.preprocessing import Preprocessor


class Reader(ABC):
    """Load a file, preprocess raw content, and build a Pydantic model."""

    def __init__(self, preprocessor: Preprocessor) -> None:
        """Attach the preprocessor used inside ``read``.

        :param preprocessor: Preprocessor applied between load and model build.
        """
        self.preprocessor = preprocessor

    def read(self, path: Path) -> BaseModel:
        """Load, preprocess, and convert a file into a structured model.

        :param path: Filesystem path to the source file.
        :return: Pydantic model produced by ``_to_model``.
        """
        raw = self._load(path)
        processed = self.preprocessor.preprocess(raw)
        return self._to_model(processed)

    @abstractmethod
    def _load(self, path: Path) -> Any:
        """Load raw content from ``path``.

        :param path: Filesystem path to the source file.
        :return: Raw content for preprocessing.
        """

    @abstractmethod
    def _to_model(self, processed: Any) -> BaseModel:
        """Build a Pydantic model from preprocessed content.

        :param processed: Output of ``preprocessor.preprocess``.
        :return: Structured model instance.
        """
