from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import numpy as np
import pytest

from compliance.models.claim import DocumentData
from compliance.preprocessing.document import DocumentReader
from compliance.preprocessing.preprocessing import FormatConverter


def _is_nan(value: object) -> bool:
    return isinstance(value, float) and np.isnan(value)


def _mock_converter(text: str, confidence: float) -> MagicMock:
    result = SimpleNamespace(
        document=SimpleNamespace(export_to_markdown=lambda: text),
        confidence=SimpleNamespace(
            layout_score=confidence,
            ocr_score=confidence,
            parse_score=confidence,
        ),
    )
    converter = MagicMock()
    converter.convert.return_value = result
    return converter


def test_to_png_called_before_docling(tmp_path: Path) -> None:
    src = tmp_path / "scan.webp"
    src.write_bytes(b"fake")
    png_path = tmp_path / "scan.png"
    png_path.write_bytes(b"png")

    format_converter = MagicMock(spec=FormatConverter)
    format_converter.source_formats = ["webp", "jpg", "jpeg", "png"]
    format_converter.to_png.return_value = png_path

    call_order: list[str] = []

    def to_png_side_effect(path: Path) -> Path:
        call_order.append("to_png")
        return png_path

    def convert_side_effect(path: Path) -> Any:
        call_order.append("docling")
        assert path == png_path
        return _mock_converter("Name: Ada\nDate: 2024-01-01", 0.9).convert.return_value

    format_converter.to_png.side_effect = to_png_side_effect
    docling = MagicMock()
    docling.convert.side_effect = convert_side_effect

    reader = DocumentReader(
        document_formats=["webp", "jpg", "jpeg", "png", "pdf"],
        confidence_threshold=0.7,
        format_converter=format_converter,
        document_converter=docling,
    )
    result = reader.read(src)

    assert call_order == ["to_png", "docling"]
    assert isinstance(result, DocumentData)
    assert result.person == "Ada"
    assert result.date == "2024-01-01"


def test_formats_filter_rejects_unknown(tmp_path: Path) -> None:
    src = tmp_path / "notes.txt"
    src.write_text("x", encoding="utf-8")
    reader = DocumentReader(
        document_formats=["webp", "png"],
        confidence_threshold=0.7,
        format_converter=FormatConverter(),
        document_converter=_mock_converter("", 1.0),
    )

    with pytest.raises(ValueError, match="Unsupported document format"):
        reader.read(src)


def test_low_confidence_sets_human_in_the_loop(tmp_path: Path) -> None:
    src = tmp_path / "doc.png"
    src.write_bytes(b"png")
    format_converter = MagicMock(spec=FormatConverter)
    format_converter.source_formats = ["png"]
    format_converter.to_png.return_value = src

    reader = DocumentReader(
        document_formats=["png"],
        confidence_threshold=0.7,
        format_converter=format_converter,
        document_converter=_mock_converter("Diagnosis: flu", 0.4),
    )
    result = reader.read(src)

    assert result.human_in_the_loop is True
    assert result.confidence == pytest.approx(0.4)
    assert result.fields.get("diagnosis") == "flu"
    assert _is_nan(result.person)
    assert _is_nan(result.date)


def test_webp_goes_through_converter(tmp_path: Path) -> None:
    src = tmp_path / "medical.webp"
    src.write_bytes(b"webp")
    png_path = tmp_path / "medical.png"
    png_path.write_bytes(b"png")

    format_converter = MagicMock(spec=FormatConverter)
    format_converter.source_formats = ["webp", "png"]
    format_converter.to_png.return_value = png_path
    docling = _mock_converter("ok", 0.95)

    reader = DocumentReader(
        document_formats=["webp", "png"],
        confidence_threshold=0.7,
        format_converter=format_converter,
        document_converter=docling,
    )
    reader.read(src)

    format_converter.to_png.assert_called_once_with(src)
    docling.convert.assert_called_once_with(png_path)


def test_pdf_skips_format_converter(tmp_path: Path) -> None:
    src = tmp_path / "form.pdf"
    src.write_bytes(b"%PDF")
    format_converter = MagicMock(spec=FormatConverter)
    format_converter.source_formats = ["webp", "png", "pdf"]
    docling = _mock_converter("ok", 0.8)

    reader = DocumentReader(
        document_formats=["webp", "png", "pdf"],
        confidence_threshold=0.7,
        format_converter=format_converter,
        document_converter=docling,
    )
    reader.read(src)

    format_converter.to_png.assert_not_called()
    docling.convert.assert_called_once_with(src)


def test_document_data_arbitrary_fields(tmp_path: Path) -> None:
    src = tmp_path / "pass.png"
    src.write_bytes(b"png")
    format_converter = MagicMock(spec=FormatConverter)
    format_converter.source_formats = ["png"]
    format_converter.to_png.return_value = src

    text = "Name: Sam\nDate: 2024-06-01\nSeat: 12A\nAirline: Acme"
    reader = DocumentReader(
        document_formats=["png"],
        confidence_threshold=0.7,
        format_converter=format_converter,
        document_converter=_mock_converter(text, 0.9),
    )
    result = reader.read(src)

    assert result.person == "Sam"
    assert result.date == "2024-06-01"
    assert result.fields["seat"] == "12A"
    assert result.fields["airline"] == "Acme"
    assert result.human_in_the_loop is False


def test_signature_detected_spanish(tmp_path: Path) -> None:
    src = tmp_path / "cert.png"
    src.write_bytes(b"png")
    format_converter = MagicMock(spec=FormatConverter)
    format_converter.source_formats = ["png"]
    format_converter.to_png.return_value = src

    text = "CONSTANCIA MÉDICA\nFirmado por Dr. Pérez\nDate: 2024-01-15"
    reader = DocumentReader(
        document_formats=["png"],
        confidence_threshold=0.7,
        format_converter=format_converter,
        document_converter=_mock_converter(text, 0.9),
    )
    result = reader.read(src)

    assert result.has_signature is True


def test_signature_detected_french(tmp_path: Path) -> None:
    src = tmp_path / "cert.png"
    src.write_bytes(b"png")
    format_converter = MagicMock(spec=FormatConverter)
    format_converter.source_formats = ["png"]
    format_converter.to_png.return_value = src

    text = "CERTIFICAT D'HOSPITALISATION\nJe soussigné, Docteur Mohamed"
    reader = DocumentReader(
        document_formats=["png"],
        confidence_threshold=0.7,
        format_converter=format_converter,
        document_converter=_mock_converter(text, 0.9),
    )
    result = reader.read(src)

    assert result.has_signature is True


def test_no_signature_detected(tmp_path: Path) -> None:
    src = tmp_path / "cert.png"
    src.write_bytes(b"png")
    format_converter = MagicMock(spec=FormatConverter)
    format_converter.source_formats = ["png"]
    format_converter.to_png.return_value = src

    text = "CERTIFICACION DE HOSPITALIZACION\nEl paciente fue admitido"
    reader = DocumentReader(
        document_formats=["png"],
        confidence_threshold=0.7,
        format_converter=format_converter,
        document_converter=_mock_converter(text, 0.9),
    )
    result = reader.read(src)

    assert result.has_signature is False


def test_timestamps_extracted(tmp_path: Path) -> None:
    src = tmp_path / "cert.png"
    src.write_bytes(b"png")
    format_converter = MagicMock(spec=FormatConverter)
    format_converter.source_formats = ["png"]
    format_converter.to_png.return_value = src

    text = (
        "Name: Ada\n"
        "Admitted: 14-04-2017\n"
        "Discharged: 18/04/2017\n"
        "Date: 2017-04-20\n"
        "Signed by Dr. García"
    )
    reader = DocumentReader(
        document_formats=["png"],
        confidence_threshold=0.7,
        format_converter=format_converter,
        document_converter=_mock_converter(text, 0.9),
    )
    result = reader.read(src)

    assert "14-04-2017" in result.timestamps
    assert "18/04/2017" in result.timestamps
    assert "2017-04-20" in result.timestamps
    assert result.has_signature is True


def test_timestamps_with_month_names(tmp_path: Path) -> None:
    src = tmp_path / "cert.png"
    src.write_bytes(b"png")
    format_converter = MagicMock(spec=FormatConverter)
    format_converter.source_formats = ["png"]
    format_converter.to_png.return_value = src

    text = "Ingresando el día 13 de Agosto de 2015\nFecha: 22 de Abril 2020"
    reader = DocumentReader(
        document_formats=["png"],
        confidence_threshold=0.7,
        format_converter=format_converter,
        document_converter=_mock_converter(text, 0.9),
    )
    result = reader.read(src)

    assert len(result.timestamps) >= 2
    assert any("Agosto" in t for t in result.timestamps)
    assert any("Abril" in t for t in result.timestamps)


def test_timestamps_deduplication(tmp_path: Path) -> None:
    src = tmp_path / "cert.png"
    src.write_bytes(b"png")
    format_converter = MagicMock(spec=FormatConverter)
    format_converter.source_formats = ["png"]
    format_converter.to_png.return_value = src

    text = "Date: 2024-01-15\nAdmission: 2024-01-15\nDischarge: 2024-01-20"
    reader = DocumentReader(
        document_formats=["png"],
        confidence_threshold=0.7,
        format_converter=format_converter,
        document_converter=_mock_converter(text, 0.9),
    )
    result = reader.read(src)

    assert result.timestamps.count("2024-01-15") == 1
    assert "2024-01-20" in result.timestamps
