from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from compliance.preprocessing.preprocessing import FormatConverter


def _write_image(path: Path, fmt: str) -> Path:
    image = Image.new("RGB", (8, 8), color=(10, 20, 30))
    image.save(path, format=fmt)
    return path


def test_webp_to_png(tmp_path: Path) -> None:
    src = _write_image(tmp_path / "sample.webp", "WEBP")
    converter = FormatConverter(source_formats=["webp", "jpg", "jpeg", "png"])

    out = converter.to_png(src)

    assert out.suffix.lower() == ".png"
    assert out != src
    assert out.is_file()
    with Image.open(out) as converted:
        assert converted.format == "PNG"
        assert converted.size == (8, 8)


def test_jpg_to_png(tmp_path: Path) -> None:
    src = _write_image(tmp_path / "sample.jpg", "JPEG")
    converter = FormatConverter(source_formats=["webp", "jpg", "jpeg", "png"])

    out = converter.to_png(src)

    assert out.suffix.lower() == ".png"
    assert out.is_file()
    with Image.open(out) as converted:
        assert converted.format == "PNG"


def test_png_passthrough(tmp_path: Path) -> None:
    src = _write_image(tmp_path / "sample.png", "PNG")
    converter = FormatConverter(source_formats=["webp", "jpg", "jpeg", "png"])

    out = converter.to_png(src)

    assert out == src


def test_png_copy_into_output_dir(tmp_path: Path) -> None:
    src = _write_image(tmp_path / "sample.png", "PNG")
    out_dir = tmp_path / "preprocessed"
    converter = FormatConverter(source_formats=["webp", "jpg", "jpeg", "png"])

    out = converter.to_png(src, output_dir=out_dir)

    assert out == out_dir / "sample.png"
    assert out.is_file()
    assert out.read_bytes() == src.read_bytes()


def test_webp_writes_into_output_dir(tmp_path: Path) -> None:
    src = _write_image(tmp_path / "sample.webp", "WEBP")
    out_dir = tmp_path / "preprocessed"
    converter = FormatConverter(source_formats=["webp", "jpg", "jpeg", "png"])

    out = converter.to_png(src, output_dir=out_dir)

    assert out == out_dir / "sample.png"
    assert out.is_file()
    with Image.open(out) as converted:
        assert converted.format == "PNG"


def test_unsupported_suffix_raises(tmp_path: Path) -> None:
    src = tmp_path / "notes.txt"
    src.write_text("not an image", encoding="utf-8")
    converter = FormatConverter(source_formats=["webp", "jpg", "jpeg", "png"])

    with pytest.raises(ValueError, match="Unsupported format"):
        converter.to_png(src)


def test_pdf_in_formats_raises(tmp_path: Path) -> None:
    src = tmp_path / "doc.pdf"
    src.write_bytes(b"%PDF-1.4")
    converter = FormatConverter(source_formats=["webp", "jpg", "jpeg", "png", "pdf"])

    with pytest.raises(ValueError, match="PDF"):
        converter.to_png(src)
