from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from docling_fakes import mock_docling_converter

from compliance.models.claim import DocumentData, is_nan_scalar
from compliance.preprocessing.document import DocumentReader
from compliance.preprocessing.preprocessing import FormatConverter
from compliance.tools.benford import BenfordResult


def _benford_result(*, conformity: bool, chi_squared: float = 42.0) -> BenfordResult:
    return BenfordResult(
        image_path="scan.png",
        observed_frequencies=dict.fromkeys(range(1, 10), 1 / 9),
        expected_frequencies=dict.fromkeys(range(1, 10), 0.1),
        chi_squared=chi_squared,
        conformity=conformity,
        total_coefficients=100,
    )


def _mock_converter(
    text: str,
    confidence: float,
    *,
    picture_classes: list[str] | None = None,
) -> MagicMock:
    return mock_docling_converter(text, confidence, picture_classes=picture_classes)


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
        format_converter=FormatConverter(source_formats=["webp", "png"]),
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

    assert result.metadata.human_in_the_loop is True
    assert result.metadata.extraction_probability == pytest.approx(0.4)
    assert result.fields.get("diagnosis") == "flu"
    assert is_nan_scalar(result.person)
    assert is_nan_scalar(result.date)


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

    text = (
        "Name: Sam\nDate: 2024-06-01\nSeat: 12A\nAirline: Acme\n"
        "This booking confirmation lists the passenger and travel details clearly."
    )
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
    assert result.metadata.human_in_the_loop is False
    assert result.metadata.faulty_extraction is False


def test_signature_detected_via_figure_classifier(tmp_path: Path) -> None:
    src = tmp_path / "cert.png"
    src.write_bytes(b"png")
    format_converter = MagicMock(spec=FormatConverter)
    format_converter.source_formats = ["png"]
    format_converter.to_png.return_value = src

    text = "CONSTANCIA MÉDICA\nEl paciente fue evaluado en consulta externa y se encuentra estable."
    reader = DocumentReader(
        document_formats=["png"],
        confidence_threshold=0.7,
        format_converter=format_converter,
        document_converter=_mock_converter(text, 0.9, picture_classes=["logo", "signature"]),
    )
    result = reader.read(src)

    assert result.metadata.has_signature is True


def test_signature_absent_when_classifier_finds_no_signature(tmp_path: Path) -> None:
    src = tmp_path / "cert.png"
    src.write_bytes(b"png")
    format_converter = MagicMock(spec=FormatConverter)
    format_converter.source_formats = ["png"]
    format_converter.to_png.return_value = src

    text = "Firmado por Dr. Pérez\nJe soussigné, Docteur Mohamed"
    reader = DocumentReader(
        document_formats=["png"],
        confidence_threshold=0.7,
        format_converter=format_converter,
        document_converter=_mock_converter(text, 0.9, picture_classes=["logo", "stamp"]),
    )
    result = reader.read(src)

    assert result.metadata.has_signature is False


def test_yolo_signature_verify_sets_has_signature_when_docling_misses(
    tmp_path: Path,
) -> None:
    """YOLO fallback can flip has_signature when Docling left it false."""
    from compliance.config.settings import OcrRetryConfig

    src = tmp_path / "cert.png"
    src.write_bytes(b"png")
    format_converter = MagicMock(spec=FormatConverter)
    format_converter.source_formats = ["png"]
    format_converter.to_png.return_value = src
    detect = MagicMock(return_value=0.91)
    reader = DocumentReader(
        document_formats=["png"],
        confidence_threshold=0.7,
        format_converter=format_converter,
        document_converter=_mock_converter("CERTIFICADO MEDICO\nPaciente: Ada", 0.9),
        ocr_retry=OcrRetryConfig(
            enabled=True,
            model="llava",
            prompt="ocr",
            on_faulty_extraction=False,
            on_low_confidence=False,
            on_human_in_the_loop=False,
            on_missing_signature=True,
            signature_model="tech4humans/yolov8s-signature-detector",
            signature_weights="yolov8s.pt",
            signature_confidence=0.25,
        ),
        signature_detect_fn=detect,
    )
    result = reader.read(src)

    assert result.metadata.has_signature is True
    assert result.metadata.signature_verify_used is True
    assert result.metadata.signature_probability == pytest.approx(0.91)
    detect.assert_called_once_with(src)


def test_yolo_signature_verify_keeps_false_when_detector_finds_none(
    tmp_path: Path,
) -> None:
    from compliance.config.settings import OcrRetryConfig

    src = tmp_path / "cert.png"
    src.write_bytes(b"png")
    format_converter = MagicMock(spec=FormatConverter)
    format_converter.source_formats = ["png"]
    format_converter.to_png.return_value = src
    detect = MagicMock(return_value=None)
    reader = DocumentReader(
        document_formats=["png"],
        confidence_threshold=0.7,
        format_converter=format_converter,
        document_converter=_mock_converter("unsigned note", 0.9),
        ocr_retry=OcrRetryConfig(
            enabled=True,
            model="llava",
            prompt="ocr",
            on_faulty_extraction=False,
            on_low_confidence=False,
            on_human_in_the_loop=False,
            on_missing_signature=True,
            signature_model="tech4humans/yolov8s-signature-detector",
        ),
        signature_detect_fn=detect,
    )
    result = reader.read(src)

    assert result.metadata.has_signature is False
    assert result.metadata.signature_verify_used is True
    assert result.metadata.human_in_the_loop is True
    detect.assert_called_once_with(src)


def test_yolo_signature_below_threshold_sets_hitl(tmp_path: Path) -> None:
    """Weak YOLO score below signature_confidence → HITL, has_signature false."""
    from compliance.config.settings import OcrRetryConfig

    src = tmp_path / "cert.png"
    src.write_bytes(b"png")
    format_converter = MagicMock(spec=FormatConverter)
    format_converter.source_formats = ["png"]
    format_converter.to_png.return_value = src
    detect = MagicMock(return_value=0.12)
    reader = DocumentReader(
        document_formats=["png"],
        confidence_threshold=0.7,
        format_converter=format_converter,
        document_converter=_mock_converter("faint mark", 0.9),
        ocr_retry=OcrRetryConfig(
            enabled=True,
            model="llava",
            prompt="ocr",
            on_faulty_extraction=False,
            on_low_confidence=False,
            on_human_in_the_loop=False,
            on_missing_signature=True,
            signature_model="tech4humans/yolov8s-signature-detector",
            signature_confidence=0.25,
        ),
        signature_detect_fn=detect,
    )
    result = reader.read(src)

    assert result.metadata.has_signature is False
    assert result.metadata.signature_verify_used is True
    assert result.metadata.signature_probability == pytest.approx(0.12)
    assert result.metadata.human_in_the_loop is True
    assert not is_nan_scalar(result.metadata.signature_probability)


def test_yolo_signature_verify_skipped_when_docling_already_detected(
    tmp_path: Path,
) -> None:
    from compliance.config.settings import OcrRetryConfig

    src = tmp_path / "cert.png"
    src.write_bytes(b"png")
    format_converter = MagicMock(spec=FormatConverter)
    format_converter.source_formats = ["png"]
    format_converter.to_png.return_value = src
    detect = MagicMock(return_value=0.9)
    reader = DocumentReader(
        document_formats=["png"],
        confidence_threshold=0.7,
        format_converter=format_converter,
        document_converter=_mock_converter("signed", 0.9, picture_classes=["signature"]),
        ocr_retry=OcrRetryConfig(
            enabled=True,
            model="llava",
            prompt="ocr",
            on_faulty_extraction=False,
            on_low_confidence=False,
            on_human_in_the_loop=False,
            on_missing_signature=True,
            signature_model="tech4humans/yolov8s-signature-detector",
        ),
        signature_detect_fn=detect,
    )
    result = reader.read(src)

    assert result.metadata.has_signature is True
    assert result.metadata.signature_verify_used is False
    detect.assert_not_called()


def test_yolo_signature_verify_errors_without_fallback(tmp_path: Path) -> None:
    """Missing YOLO / HF auth must raise — no soft has_signature=false fallback."""
    from compliance.config.settings import OcrRetryConfig
    from compliance.preprocessing.document import SignatureDetectionError

    src = tmp_path / "cert.png"
    src.write_bytes(b"png")
    format_converter = MagicMock(spec=FormatConverter)
    format_converter.source_formats = ["png"]
    format_converter.to_png.return_value = src
    detect = MagicMock(side_effect=SignatureDetectionError("Cannot download gated YOLO weights. Set HF_TOKEN."))
    reader = DocumentReader(
        document_formats=["png"],
        confidence_threshold=0.7,
        format_converter=format_converter,
        document_converter=_mock_converter("unsigned note", 0.9),
        ocr_retry=OcrRetryConfig(
            enabled=True,
            model="llava",
            prompt="ocr",
            on_faulty_extraction=False,
            on_low_confidence=False,
            on_human_in_the_loop=False,
            on_missing_signature=True,
            signature_model="tech4humans/yolov8s-signature-detector",
        ),
        signature_detect_fn=detect,
    )

    with pytest.raises(SignatureDetectionError, match="HF_TOKEN"):
        reader.read(src)


def test_no_signature_when_no_pictures(tmp_path: Path) -> None:
    src = tmp_path / "cert.png"
    src.write_bytes(b"png")
    format_converter = MagicMock(spec=FormatConverter)
    format_converter.source_formats = ["png"]
    format_converter.to_png.return_value = src

    text = "CERTIFICACION DE HOSPITALIZACION\nEl paciente fue admitido por dolor abdominal agudo en urgencias."
    reader = DocumentReader(
        document_formats=["png"],
        confidence_threshold=0.7,
        format_converter=format_converter,
        document_converter=_mock_converter(text, 0.9),
    )
    result = reader.read(src)

    assert result.metadata.has_signature is False


def test_timestamps_extracted(tmp_path: Path) -> None:
    src = tmp_path / "cert.png"
    src.write_bytes(b"png")
    format_converter = MagicMock(spec=FormatConverter)
    format_converter.source_formats = ["png"]
    format_converter.to_png.return_value = src

    text = "Name: Ada\nAdmitted: 14-04-2017\nDischarged: 18/04/2017\nDate: 2017-04-20\nSigned by Dr. García"
    reader = DocumentReader(
        document_formats=["png"],
        confidence_threshold=0.7,
        format_converter=format_converter,
        document_converter=_mock_converter(text, 0.9, picture_classes=["signature"]),
    )
    result = reader.read(src)

    assert "14-04-2017" in result.timestamps
    assert "18/04/2017" in result.timestamps
    assert "2017-04-20" in result.timestamps
    assert result.metadata.has_signature is True


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


def test_benford_violation_returns_deny_fraud_skips_docling(tmp_path: Path) -> None:
    src = tmp_path / "suspect.png"
    src.write_bytes(b"png")
    png_path = tmp_path / "suspect_converted.png"
    png_path.write_bytes(b"png")

    format_converter = MagicMock(spec=FormatConverter)
    format_converter.source_formats = ["png"]
    format_converter.to_png.return_value = png_path
    docling = _mock_converter("should not run", 0.99)

    benford_checker = MagicMock()
    benford_checker.check.return_value = _benford_result(conformity=False, chi_squared=99.0)

    reader = DocumentReader(
        document_formats=["png"],
        confidence_threshold=0.7,
        format_converter=format_converter,
        document_converter=docling,
        benford_checker=benford_checker,
    )
    result = reader.read(src)

    format_converter.to_png.assert_called_once_with(src)
    benford_checker.check.assert_called_once_with(png_path)
    docling.convert.assert_not_called()
    assert result.decision == "DENY"  # type: ignore[attr-defined]
    assert result.reason == "fraud"  # type: ignore[attr-defined]
    assert result.fields["decision"] == "DENY"
    assert result.fields["reason"] == "fraud"
    assert result.fields["benford_conformity"] is False
    assert result.fields["benford_chi_squared"] == pytest.approx(99.0)
    assert is_nan_scalar(result.raw_text)


def test_benford_conformity_continues_to_docling(tmp_path: Path) -> None:
    src = tmp_path / "ok.png"
    src.write_bytes(b"png")
    format_converter = MagicMock(spec=FormatConverter)
    format_converter.source_formats = ["png"]
    format_converter.to_png.return_value = src
    docling = _mock_converter("Name: Ada\nDate: 2024-01-01", 0.9)

    benford_checker = MagicMock()
    benford_checker.check.return_value = _benford_result(conformity=True, chi_squared=3.0)

    reader = DocumentReader(
        document_formats=["png"],
        confidence_threshold=0.7,
        format_converter=format_converter,
        document_converter=docling,
        benford_checker=benford_checker,
    )
    result = reader.read(src)

    benford_checker.check.assert_called_once_with(src)
    docling.convert.assert_called_once_with(src)
    assert result.person == "Ada"
    assert not hasattr(result, "decision") or getattr(result, "decision", None) != "DENY"


def test_pdf_skips_benford_check(tmp_path: Path) -> None:
    src = tmp_path / "form.pdf"
    src.write_bytes(b"%PDF")
    format_converter = MagicMock(spec=FormatConverter)
    format_converter.source_formats = ["png", "pdf"]
    docling = _mock_converter("ok", 0.8)
    benford_checker = MagicMock()

    reader = DocumentReader(
        document_formats=["png", "pdf"],
        confidence_threshold=0.7,
        format_converter=format_converter,
        document_converter=docling,
        benford_checker=benford_checker,
    )
    reader.read(src)

    benford_checker.check.assert_not_called()
    docling.convert.assert_called_once_with(src)
