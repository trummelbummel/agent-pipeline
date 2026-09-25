from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable

from pydantic import BaseModel

ChatFn = Callable[..., Any]


class ClassificationResult(BaseModel):
    """Result of case-type classification.

    :param labels: Selected coverage label(s).
    :param probabilities: Per-label probability estimates in [0, 1].
    """

    labels: list[str]
    probabilities: dict[str, float]


class Classifier(ABC):
    """Abstract classifier interface for claim case types."""

    @abstractmethod
    def classify(self, text: str) -> ClassificationResult:
        """Classify free-text claim narrative into coverage labels.

        :param text: Claim description text.
        :return: Labels and probability estimates.
        """


class CaseClassifier(Classifier):
    """Classify claim descriptions into config-driven coverage labels via LLM.

    Stub for RED — returns empty result so happy-path assertions fail.
    """

    def __init__(
        self,
        labels: list[str],
        model_name: str,
        prompt: str,
        other_label: str,
        chat_fn: ChatFn | None = None,
    ) -> None:
        """Bind label vocabulary, model, prompt, and optional chat seam.

        :param labels: Configured coverage class names.
        :param model_name: LLM model name from config.
        :param prompt: Classification instruction prompt from config.
        :param other_label: Fallback label when no class fits.
        :param chat_fn: Optional chat callable for tests; defaults unused in stub.
        """
        self.labels = labels
        self.model_name = model_name
        self.prompt = prompt
        self.other_label = other_label
        self._chat = chat_fn

    def classify(self, text: str) -> ClassificationResult:
        """Return empty stub result (RED phase).

        :param text: Claim description text (ignored in stub).
        :return: Empty ClassificationResult so happy-path tests fail.
        """
        return ClassificationResult(labels=[], probabilities={})
