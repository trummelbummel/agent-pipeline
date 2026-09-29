from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock


def mock_docling_converter(
    text: str,
    confidence: float,
    *,
    picture_classes: list[str] | None = None,
) -> MagicMock:
    """Build a Docling ``DocumentConverter`` double for preprocessing tests.

    :param text: Markdown/text returned by ``export_to_markdown``.
    :param confidence: Layout/OCR/parse score applied to all confidence fields.
    :param picture_classes: Optional figure-classifier top-class names (e.g. signature).
    :return: Mock converter whose ``convert`` returns a Docling-like result.
    """
    pictures: list[Any] = []
    for class_name in picture_classes or []:
        prediction = SimpleNamespace(class_name=class_name, confidence=0.9)
        classification = SimpleNamespace(predictions=[prediction])
        pictures.append(SimpleNamespace(meta=SimpleNamespace(classification=classification)))
    result = SimpleNamespace(
        document=SimpleNamespace(
            export_to_markdown=lambda: text,
            pictures=pictures,
        ),
        confidence=SimpleNamespace(
            layout_score=confidence,
            ocr_score=confidence,
            parse_score=confidence,
        ),
    )
    converter = MagicMock()
    converter.convert.return_value = result
    return converter
