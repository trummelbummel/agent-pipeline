from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock


from compliance.models.claim import BookingData, is_nan_scalar
from compliance.preprocessing.description import DescriptionReader
from compliance.preprocessing.extractor import InformationExtractor


def _mock_extractor(fields: dict[str, Any]) -> InformationExtractor:
    import json

    chat = MagicMock(
        return_value=SimpleNamespace(message=SimpleNamespace(content=json.dumps(fields)))
    )
    return InformationExtractor(
        target_model=BookingData,
        model_name="test-model",
        prompt="extract",
        chat_fn=chat,
    )


def test_description_reader_extracts_booking_data(tmp_path: Path) -> None:
    path = tmp_path / "description.txt"
    path.write_text("I booked flight XY123 under ref REF99.", encoding="utf-8")

    extractor = _mock_extractor({"name": "Jordan", "service": "XY123", "booking_ref": "REF99"})
    reader = DescriptionReader(extractor=extractor)

    result = reader.read(path)

    assert isinstance(result, BookingData)
    assert result.name == "Jordan"
    assert result.service == "XY123"
    assert result.booking_ref == "REF99"
    assert is_nan_scalar(result.price)
    assert reader.last_raw_text == "I booked flight XY123 under ref REF99."


def test_description_reader_retains_raw_text(tmp_path: Path) -> None:
    path = tmp_path / "description.txt"
    text = "Please refund my train ticket."
    path.write_text(text, encoding="utf-8")

    reader = DescriptionReader(extractor=_mock_extractor({}))
    reader.read(path)

    assert reader.last_raw_text == text
