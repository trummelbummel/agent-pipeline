from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from compliance.llm.classifier import CaseClassifier, ClassificationResult

if TYPE_CHECKING:
    from conftest import ChatReturningFactory

TRIP_CANCELLATION = "1"
PERSONAL_EFFECTS = "2"
MISSED_DEPARTURE = "3"
OTHER = "Other"

_SAMPLE_LABELS = [TRIP_CANCELLATION, PERSONAL_EFFECTS, MISSED_DEPARTURE]
_SAMPLE_DESCRIPTION = "I had to cancel my flight to Paris because of a medical emergency."


def test_case_classifier_happy_path_trip_cancellation(
    chat_returning_factory: ChatReturningFactory,
) -> None:
    chat = chat_returning_factory({
        "labels": [TRIP_CANCELLATION],
        "probabilities": {
            TRIP_CANCELLATION: 0.91,
            PERSONAL_EFFECTS: 0.05,
            MISSED_DEPARTURE: 0.02,
            OTHER: 0.02,
        },
    })
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


def _make_classifier(chat: MagicMock) -> CaseClassifier:
    return CaseClassifier(
        labels=_SAMPLE_LABELS,
        model_name="test-model",
        prompt="classify",
        other_label=OTHER,
        chat_fn=chat,
    )


def test_case_classifier_empty_labels_uses_other(
    chat_returning_factory: ChatReturningFactory,
) -> None:
    chat = chat_returning_factory({"labels": [], "probabilities": {}})
    result = _make_classifier(chat).classify("unrelated narrative")

    assert result.labels == [OTHER]
    assert result.probabilities[OTHER] == 1.0


def test_case_classifier_unknown_label_mapped_to_other(
    chat_returning_factory: ChatReturningFactory,
) -> None:
    chat = chat_returning_factory({
        "labels": ["Not A Real Coverage Type"],
        "probabilities": {"Not A Real Coverage Type": 0.8},
    })
    result = _make_classifier(chat).classify("something odd")

    assert result.labels == [OTHER]
    assert OTHER in result.probabilities


def test_case_classifier_probabilities_cover_configured_labels(
    chat_returning_factory: ChatReturningFactory,
) -> None:
    chat = chat_returning_factory({
        "labels": [PERSONAL_EFFECTS],
        "probabilities": {PERSONAL_EFFECTS: 0.7},
    })
    result = _make_classifier(chat).classify("my bag was stolen")

    expected_keys = set(_SAMPLE_LABELS) | {OTHER}
    assert expected_keys <= set(result.probabilities)
    for value in result.probabilities.values():
        assert isinstance(value, float)
        assert 0.0 <= value <= 1.0
