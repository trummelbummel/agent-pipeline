from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import numpy as np

from compliance.models.claim import BookingData
from compliance.preprocessing.extractor import InformationExtractor


def _is_nan(value: object) -> bool:
    return isinstance(value, float) and np.isnan(value)


def _chat_returning(payload: dict[str, Any]) -> MagicMock:
    import json

    response = SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))
    return MagicMock(return_value=response)


def test_extractor_schema_constrained_booking_data() -> None:
    chat = _chat_returning({"name": "Ada Lovelace", "booking_ref": "ABC123"})
    extractor = InformationExtractor(
        target_model=BookingData,
        model_name="test-model",
        prompt="extract booking fields",
        chat_fn=chat,
    )

    result = extractor.extract("My name is Ada Lovelace, booking ABC123")

    assert isinstance(result, BookingData)
    assert result.name == "Ada Lovelace"
    assert result.booking_ref == "ABC123"
    chat.assert_called_once()
    call_kwargs = chat.call_args.kwargs
    assert call_kwargs["model"] == "test-model"
    assert call_kwargs["format"] == "json"
    assert "extract booking fields" in call_kwargs["messages"][0]["content"]


def test_extractor_missing_fields_are_nan() -> None:
    chat = _chat_returning({"name": "Sam"})
    extractor = InformationExtractor(
        target_model=BookingData,
        model_name="test-model",
        prompt="prompt",
        chat_fn=chat,
    )

    result = extractor.extract("Sam wrote a letter")

    assert result.name == "Sam"
    assert _is_nan(result.booking_ref)
    assert _is_nan(result.price)
    assert _is_nan(result.operator)


def test_extractor_null_fields_become_nan() -> None:
    chat = _chat_returning({"name": "Sam", "price": None, "origin": None})
    extractor = InformationExtractor(
        target_model=BookingData,
        model_name="m",
        prompt="p",
        chat_fn=chat,
    )

    result = extractor.extract("text")

    assert result.name == "Sam"
    assert _is_nan(result.price)
    assert _is_nan(result.origin)
