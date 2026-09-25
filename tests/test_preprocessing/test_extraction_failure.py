from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np

from compliance.config.settings import OcrRetryConfig
from compliance.preprocessing.document import DocumentReader
from compliance.preprocessing.extraction_failure import ExtractionFailure
from compliance.preprocessing.preprocessing import FormatConverter


def _mock_converter(text: str, confidence: float) -> MagicMock:
    result = SimpleNamespace(
        document=SimpleNamespace(
            export_to_markdown=lambda: text,
            pictures=[],
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


def test_empty_text_is_faulty() -> None:
    detector = ExtractionFailure()
    result = detector.evaluate("_none_")
    assert result.faulty is True
    assert "empty_text" in result.reasons


def test_nan_text_is_faulty() -> None:
    detector = ExtractionFailure()
    result = detector.evaluate(np.nan)
    assert result.faulty is True
    assert "empty_text" in result.reasons


def test_claim5_style_figure_noise_is_faulty() -> None:
    detector = ExtractionFailure()
    text = "\n".join(
        [
            "31. X. 20u",
            "<!-- image -->",
            "Signature",
            "<!-- image -->",
            "Signature",
        ]
    )
    result = detector.evaluate(text)
    assert result.faulty is True
    assert result.reasons


def test_substantive_certificate_is_ok() -> None:
    detector = ExtractionFailure()
    text = (
        "## CERTIFICAT D'HOSPITALISATION\n"
        "Je soussigné, Docteur Kurtneh Mohamed, Praticien Hospitalier dans le service "
        "de Médecine Physique, atteste que Monsieur KOUADRI a été pris en charge."
    )
    result = detector.evaluate(text)
    assert result.faulty is False
    assert result.reasons == []


def test_document_reader_marks_faulty_extraction_as_hitl(tmp_path: Path) -> None:
    src = tmp_path / "Italian_medical_2a.png"
    src.write_bytes(b"png")
    format_converter = MagicMock(spec=FormatConverter)
    format_converter.source_formats = ["png"]
    format_converter.to_png.return_value = src

    garbage = "31. X. 20u\n<!-- image -->\nSignature\n<!-- image -->\nSignature"
    reader = DocumentReader(
        document_formats=["png"],
        confidence_threshold=0.7,
        format_converter=format_converter,
        document_converter=_mock_converter(garbage, 0.95),
        ocr_retry=OcrRetryConfig(enabled=False, model="llava", prompt="ocr"),
    )
    result = reader.read(src)

    assert result.metadata.faulty_extraction is True
    assert result.metadata.human_in_the_loop is True
    assert result.metadata.extraction_probability == 0.95
    assert result.metadata.failure_reasons


def test_faulty_extraction_invokes_vision_retry_and_clears_faulty(tmp_path: Path) -> None:
    src = tmp_path / "Italian_medical_2a.png"
    src.write_bytes(b"png")
    format_converter = MagicMock(spec=FormatConverter)
    format_converter.source_formats = ["png"]
    format_converter.to_png.return_value = src

    garbage = "31. X. 20u\n<!-- image -->\nSignature\n<!-- image -->\nSignature"
    certificate = (
        "## CERTIFICAT D'HOSPITALISATION\n"
        "Je soussigné, Docteur Kurtneh Mohamed, Praticien Hospitalier dans le service "
        "de Médecine Physique, atteste que Monsieur KOUADRI a été pris en charge."
    )
    retry_chat = MagicMock(
        return_value=SimpleNamespace(message=SimpleNamespace(content=certificate))
    )
    ocr_retry = OcrRetryConfig(
        enabled=True,
        model="llava",
        prompt="Transcribe the document image into clean markdown.",
    )
    reader = DocumentReader(
        document_formats=["png"],
        confidence_threshold=0.7,
        format_converter=format_converter,
        document_converter=_mock_converter(garbage, 0.95),
        ocr_retry=ocr_retry,
        retry_chat_fn=retry_chat,
    )
    result = reader.read(src)

    assert result.metadata.faulty_extraction is False
    assert result.metadata.human_in_the_loop is False
    assert result.metadata.retry_used is True
    assert result.metadata.retry_model == "llava"
    assert retry_chat.call_count == 1


def test_faulty_extraction_retry_still_faulty_keeps_hitl(tmp_path: Path) -> None:
    src = tmp_path / "scan.png"
    src.write_bytes(b"png")
    format_converter = MagicMock(spec=FormatConverter)
    format_converter.source_formats = ["png"]
    format_converter.to_png.return_value = src

    garbage = "31. X. 20u\n<!-- image -->\nSignature\n<!-- image -->\nSignature"
    retry_chat = MagicMock(
        return_value=SimpleNamespace(message=SimpleNamespace(content="_none_"))
    )
    reader = DocumentReader(
        document_formats=["png"],
        confidence_threshold=0.7,
        format_converter=format_converter,
        document_converter=_mock_converter(garbage, 0.95),
        ocr_retry=OcrRetryConfig(enabled=True, model="llava", prompt="ocr"),
        retry_chat_fn=retry_chat,
    )
    result = reader.read(src)

    assert result.metadata.faulty_extraction is True
    assert result.metadata.human_in_the_loop is True
    assert result.metadata.retry_used is True
    assert result.metadata.retry_model == "llava"
    assert retry_chat.call_count == 1


def test_faulty_extraction_retry_invoked_when_enabled(tmp_path: Path) -> None:
    src = tmp_path / "scan.png"
    src.write_bytes(b"png")
    format_converter = MagicMock(spec=FormatConverter)
    format_converter.source_formats = ["png"]
    format_converter.to_png.return_value = src

    garbage = "31. X. 20u\n<!-- image -->\nSignature\n<!-- image -->\nSignature"
    retry_chat = MagicMock(
        return_value=SimpleNamespace(message=SimpleNamespace(content="_none_"))
    )
    reader = DocumentReader(
        document_formats=["png"],
        confidence_threshold=0.7,
        format_converter=format_converter,
        document_converter=_mock_converter(garbage, 0.9),
        ocr_retry=OcrRetryConfig(enabled=True, model="llava", prompt="ocr"),
        retry_chat_fn=retry_chat,
    )
    reader.read(src)
    assert retry_chat.call_count == 1


def test_clean_extraction_skips_retry(tmp_path: Path) -> None:
    src = tmp_path / "scan.png"
    src.write_bytes(b"png")
    format_converter = MagicMock(spec=FormatConverter)
    format_converter.source_formats = ["png"]
    format_converter.to_png.return_value = src

    certificate = (
        "## CERTIFICAT D'HOSPITALISATION\n"
        "Je soussigné, Docteur Kurtneh Mohamed, Praticien Hospitalier dans le service "
        "de Médecine Physique, atteste que Monsieur KOUADRI a été pris en charge."
    )
    retry_chat = MagicMock()
    reader = DocumentReader(
        document_formats=["png"],
        confidence_threshold=0.7,
        format_converter=format_converter,
        document_converter=_mock_converter(certificate, 0.95),
        ocr_retry=OcrRetryConfig(enabled=True, model="llava", prompt="ocr"),
        retry_chat_fn=retry_chat,
    )
    result = reader.read(src)

    assert result.metadata.faulty_extraction is False
    assert result.metadata.retry_used is False
    retry_chat.assert_not_called()


def test_ocr_retry_disabled_skips_chat(tmp_path: Path) -> None:
    src = tmp_path / "scan.png"
    src.write_bytes(b"png")
    format_converter = MagicMock(spec=FormatConverter)
    format_converter.source_formats = ["png"]
    format_converter.to_png.return_value = src

    garbage = "31. X. 20u\n<!-- image -->\nSignature\n<!-- image -->\nSignature"
    retry_chat = MagicMock()
    reader = DocumentReader(
        document_formats=["png"],
        confidence_threshold=0.7,
        format_converter=format_converter,
        document_converter=_mock_converter(garbage, 0.95),
        ocr_retry=OcrRetryConfig(enabled=False, model="llava", prompt="ocr"),
        retry_chat_fn=retry_chat,
    )
    result = reader.read(src)

    assert result.metadata.faulty_extraction is True
    assert result.metadata.human_in_the_loop is True
    assert result.metadata.retry_used is False
    retry_chat.assert_not_called()


def test_faulty_extraction_retry_error_keeps_hitl(tmp_path: Path) -> None:
    src = tmp_path / "scan.png"
    src.write_bytes(b"png")
    format_converter = MagicMock(spec=FormatConverter)
    format_converter.source_formats = ["png"]
    format_converter.to_png.return_value = src

    garbage = "31. X. 20u\n<!-- image -->\nSignature\n<!-- image -->\nSignature"
    retry_chat = MagicMock(side_effect=RuntimeError("vision unavailable"))
    reader = DocumentReader(
        document_formats=["png"],
        confidence_threshold=0.7,
        format_converter=format_converter,
        document_converter=_mock_converter(garbage, 0.95),
        ocr_retry=OcrRetryConfig(enabled=True, model="llava", prompt="ocr"),
        retry_chat_fn=retry_chat,
    )
    result = reader.read(src)

    assert result.metadata.faulty_extraction is True
    assert result.metadata.human_in_the_loop is True
    assert result.metadata.retry_used is True
    assert result.metadata.retry_model == "llava"
    assert retry_chat.call_count == 1
