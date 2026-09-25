from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

from compliance.models.classifier import CaseClassifier, ClassificationResult


def _chat_returning(payload: dict[str, Any]) -> MagicMock:
    import json

    response = SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))
    return MagicMock(return_value=response)


TRIP_CANCELLATION = "Trip cancellation or rescheduling"
PERSONAL_EFFECTS = "Personal Effects"
MISSED_DEPARTURE = "Missed Departure or Missed Connection"
OTHER = "Other"

_SAMPLE_LABELS = [TRIP_CANCELLATION, PERSONAL_EFFECTS, MISSED_DEPARTURE]
_SAMPLE_DESCRIPTION = (
    "I had to cancel my flight to Paris because of a medical emergency."
)


def test_case_classifier_happy_path_trip_cancellation() -> None:
    chat = _chat_returning(
        {
            "labels": [TRIP_CANCELLATION],
            "probabilities": {
                TRIP_CANCELLATION: 0.91,
                PERSONAL_EFFECTS: 0.05,
                MISSED_DEPARTURE: 0.02,
                OTHER: 0.02,
            },
        }
    )
    classifier = CaseClassifier(
        labels=_SAMPLE_LABELS,
        model_name="test-model",
        prompt="classify the claim into the provided labels",
        other_label=OTHER,
        chat_fn=chat,
    )

    result = classifier.classify(_SAMPLE_DESCRIPTION)

    assert isinstance(result, ClassificationResult)
    assert TRIP_CANCELLATION in result.labels
    assert isinstance(result.probabilities, dict)
    for label in _SAMPLE_LABELS:
        assert label in result.probabilities
        assert isinstance(result.probabilities[label], float)
    chat.assert_called_once()
    call_kwargs = chat.call_args.kwargs
    assert call_kwargs["model"] == "test-model"
    assert call_kwargs["format"] == "json"
    assert "classify the claim" in call_kwargs["messages"][0]["content"]
