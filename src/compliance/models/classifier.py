from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from typing import Any, Callable

import ollama
from pydantic import BaseModel

logger = logging.getLogger(__name__)

ChatFn = Callable[..., Any]


class ClassificationResult(BaseModel):
    """Result of case-type classification.

    Probability values are estimates in [0, 1]; callers should not treat them
    as calibrated probabilities.

    :param labels: Selected coverage label(s).
    :param probabilities: Per-label probability estimates keyed by label name.
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
    """Classify claim descriptions into config-driven coverage labels via LLM."""

    def __init__(
        self,
        labels: list[str],
        model_name: str,
        prompt: str,
        other_label: str,
        chat_fn: ChatFn | None = None,
    ) -> None:
        """Bind label vocabulary, model, prompt, and optional chat seam.

        :param labels: Configured coverage class names (from config, never hardcoded here).
        :param model_name: LLM model name from config.
        :param prompt: Classification instruction prompt from config.
        :param other_label: Fallback label when no class fits.
        :param chat_fn: Optional chat callable for tests; defaults to ollama.chat.
        """
        self.labels = list(labels)
        self.model_name = model_name
        self.prompt = prompt
        self.other_label = other_label
        self._chat: ChatFn = chat_fn or ollama.chat

    def classify(self, text: str) -> ClassificationResult:
        """Call the LLM and parse labels with probability estimates.

        :param text: Free-text claim description.
        :return: ClassificationResult with selected labels and probabilities.
        """
        label_list = ", ".join([*self.labels, self.other_label])
        system_prompt = f"{self.prompt}\n\nAllowed labels: {label_list}"
        response = self._chat(
            model=self.model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ],
            format="json",
        )
        content = self._response_content(response)
        payload = self._parse_classification_payload(content)
        return ClassificationResult.model_validate(payload)

    @staticmethod
    def _response_content(response: Any) -> str:
        """Pull message content from an ollama-style chat response.

        :param response: Chat response object or mapping.
        :return: Message content string.
        """
        if hasattr(response, "message"):
            message = response.message
            return str(getattr(message, "content", "") or "")
        if isinstance(response, dict):
            message = response.get("message", {})
            if isinstance(message, dict):
                return str(message.get("content", "") or "")
        return str(response or "")

    @staticmethod
    def _parse_classification_payload(content: str) -> dict[str, Any]:
        """Parse LLM JSON into a ClassificationResult-shaped dict.

        :param content: Raw model output expected to be JSON.
        :return: Dict with labels and probabilities for model_validate.
        """
        content = content.strip()
        if not content:
            logger.warning("Empty LLM classification response")
            return {"labels": [], "probabilities": {}}
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            logger.warning("Failed to parse LLM classification JSON")
            return {"labels": [], "probabilities": {}}
        if not isinstance(parsed, dict):
            logger.warning("LLM classification JSON was not an object")
            return {"labels": [], "probabilities": {}}
        labels = parsed.get("labels", [])
        probabilities = parsed.get("probabilities", {})
        if not isinstance(labels, list):
            labels = []
        if not isinstance(probabilities, dict):
            probabilities = {}
        return {
            "labels": [str(item) for item in labels],
            "probabilities": {
                str(key): float(value)
                for key, value in probabilities.items()
                if isinstance(value, (int, float))
            },
        }
