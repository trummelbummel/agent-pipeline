from __future__ import annotations

from typing import TYPE_CHECKING

from compliance.models.claim import BookingData, is_nan_scalar
from compliance.preprocessing.extractor import InformationExtractor

if TYPE_CHECKING:
    from conftest import ChatReturningFactory


def test_extractor_schema_constrained_booking_data(
    chat_returning_factory: ChatReturningFactory,
) -> None:
    chat = chat_returning_factory({"name": "Ada Lovelace", "booking_ref": "ABC123"})
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


def test_extractor_missing_fields_are_nan(
    chat_returning_factory: ChatReturningFactory,
) -> None:
    chat = chat_returning_factory({"name": "Sam"})
    extractor = InformationExtractor(
        target_model=BookingData,
        model_name="test-model",
        prompt="prompt",
        chat_fn=chat,
    )

    result = extractor.extract("Sam wrote a letter")

    assert result.name == "Sam"
    assert is_nan_scalar(result.booking_ref)
    assert is_nan_scalar(result.price)
    assert is_nan_scalar(result.operator)


def test_extractor_null_fields_become_nan(
    chat_returning_factory: ChatReturningFactory,
) -> None:
    chat = chat_returning_factory({"name": "Sam", "price": None, "origin": None})
    extractor = InformationExtractor(
        target_model=BookingData,
        model_name="m",
        prompt="p",
        chat_fn=chat,
    )

    result = extractor.extract("text")

    assert result.name == "Sam"
    assert is_nan_scalar(result.price)
    assert is_nan_scalar(result.origin)
