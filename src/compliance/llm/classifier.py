from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Annotated, NamedTuple

import ollama
from pydantic import BaseModel, ConfigDict, Field

from compliance.llm.chat import ChatFn, parse_llm_json_object, response_content


class _ClassificationPayload(NamedTuple):
    labels: list[str]
    probabilities: dict[str, float]


class _LabelSelection(NamedTuple):
    labels: list[str]
    used_other_fallback: bool


class ClassificationResult(BaseModel):
    """Result of case-type classification.

    Probability values are estimates in [0, 1]; callers should not treat them
    as calibrated probabilities.

    :param labels: Selected coverage label(s).
    :param probabilities: Per-label probability estimates keyed by label name.
    """

    model_config = ConfigDict(strict=True)

    labels: list[str] = Field(description="Selected coverage label(s)")
    probabilities: dict[str, Annotated[float, Field(ge=0, le=1)]] = Field(
        description="Per-label probability estimates in [0, 1]"
    )


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
        :param other_label: Abstain label when no positive class applies (``False``).
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
        response = self._chat(
            model=self.model_name,
            messages=self._classification_messages(text),
            format="json",
        )
        content = response_content(response)
        payload = self._parse_classification_payload(content)
        if payload is None:
            return self._normalized_classification([], {})
        return self._normalized_classification(payload.labels, payload.probabilities)

    def _classification_messages(self, text: str) -> list[dict[str, str]]:
        label_list = ", ".join(self._label_vocabulary())
        prompt = self.prompt.replace("{other_label}", self.other_label)
        system_prompt = f"{prompt}\n\nAllowed labels: {label_list}"
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text},
        ]

    def _label_vocabulary(self) -> list[str]:
        return [*self.labels, self.other_label]

    def _normalized_classification(
        self,
        raw_labels: list[str],
        raw_probabilities: dict[str, float],
    ) -> ClassificationResult:
        selection = self._selected_labels(raw_labels)
        probabilities = self._normalized_probabilities(
            raw_probabilities,
            used_other_fallback=selection.used_other_fallback,
        )
        return ClassificationResult(
            labels=selection.labels,
            probabilities=probabilities,
        )

    def _selected_labels(self, raw_labels: list[str]) -> _LabelSelection:
        allowed = set(self.labels) | {self.other_label}
        selected: list[str] = []
        seen: set[str] = set()
        for label in raw_labels:
            if label in allowed and label not in seen:
                selected.append(label)
                seen.add(label)
        if selected:
            return _LabelSelection(labels=selected, used_other_fallback=False)
        return _LabelSelection(labels=[self.other_label], used_other_fallback=True)

    def _normalized_probabilities(
        self,
        raw_probabilities: dict[str, float],
        *,
        used_other_fallback: bool,
    ) -> dict[str, float]:
        probabilities: dict[str, float] = {
            label: self._clamped_probability(raw_probabilities.get(label, 0.0)) for label in self._label_vocabulary()
        }
        if used_other_fallback:
            probabilities[self.other_label] = 1.0
        return probabilities

    @staticmethod
    def _clamped_probability(value: float) -> float:
        return max(0.0, min(1.0, float(value)))

    @staticmethod
    def _parse_classification_payload(content: str) -> _ClassificationPayload | None:
        parsed = parse_llm_json_object(content, context="classification")
        if parsed is None:
            return None
        return _ClassificationPayload(
            labels=CaseClassifier._coerced_labels(parsed.get("labels", [])),
            probabilities=CaseClassifier._coerced_probabilities(parsed.get("probabilities", {})),
        )

    @staticmethod
    def _coerced_labels(raw: object) -> list[str]:
        if not isinstance(raw, list):
            return []
        return [str(item) for item in raw]

    @staticmethod
    def _coerced_probabilities(raw: object) -> dict[str, float]:
        if not isinstance(raw, dict):
            return {}
        return {str(key): float(value) for key, value in raw.items() if isinstance(value, (int, float))}
