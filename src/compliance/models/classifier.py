from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from typing import Any

import ollama
from pydantic import BaseModel

from compliance.llm.chat import ChatFn, response_content

logger = logging.getLogger(__name__)


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

        Invalid or empty model output falls back to ``other_label``. Probability
        values are clamped to [0, 1] and treated as estimates (not calibrated).

        :param text: Free-text claim description.
        :return: ClassificationResult with selected labels and probabilities.
        """
        label_list = ", ".join([*self.labels, self.other_label])
        prompt = self.prompt.replace("{other_label}", self.other_label)
        system_prompt = f"{prompt}\n\nAllowed labels: {label_list}"
        response = self._chat(
            model=self.model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ],
            format="json",
        )
        content = response_content(response)
        payload = self._parse_classification_payload(content)
        return self._normalized_classification(
            raw_labels=payload["labels"],
            raw_probabilities=payload["probabilities"],
        )

    def _normalized_classification(
        self,
        raw_labels: list[str],
        raw_probabilities: dict[str, float],
    ) -> ClassificationResult:
        """Filter labels to the configured set and fill probability coverage.

        :param raw_labels: Labels parsed from the LLM JSON payload.
        :param raw_probabilities: Probability map parsed from the LLM JSON payload.
        :return: ClassificationResult with Other fallback and full key coverage.
        """
        allowed = set(self.labels) | {self.other_label}
        selected: list[str] = []
        seen: set[str] = set()
        for label in raw_labels:
            if label in allowed and label not in seen:
                selected.append(label)
                seen.add(label)
        used_other_fallback = False
        if not selected:
            selected = [self.other_label]
            used_other_fallback = True

        probabilities: dict[str, float] = {}
        for label in [*self.labels, self.other_label]:
            if label in probabilities:
                continue
            raw_value = raw_probabilities.get(label, 0.0)
            probabilities[label] = self._clamped_probability(raw_value)

        if used_other_fallback:
            probabilities[self.other_label] = 1.0

        return ClassificationResult(labels=selected, probabilities=probabilities)

    @staticmethod
    def _clamped_probability(value: float) -> float:
        """Clamp a probability estimate into [0, 1].

        :param value: Raw numeric probability from the model.
        :return: Value restricted to the unit interval.
        """
        return max(0.0, min(1.0, float(value)))

    @staticmethod
    def _parse_classification_payload(content: str) -> dict[str, Any]:
        """Parse LLM JSON into a ClassificationResult-shaped dict.

        :param content: Raw model output expected to be JSON.
        :return: Dict with labels and probabilities for normalization.
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
