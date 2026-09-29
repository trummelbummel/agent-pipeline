"""Unit tests for chunked upload writer byte caps (SR-009)."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest
from fastapi import UploadFile
from starlette.datastructures import Headers

from api.uploads import UploadTooLargeError, write_upload_stream


def _upload(data: bytes, *, filename: str = "part.bin") -> UploadFile:
    return UploadFile(
        file=BytesIO(data),
        filename=filename,
        headers=Headers({"content-type": "application/octet-stream"}),
    )


def test_write_upload_stream_returns_byte_count(tmp_path: Path) -> None:
    """Writer reports the number of bytes it copied."""
    dest = tmp_path / "out.bin"
    payload = b"abc" * 100
    written = write_upload_stream(
        _upload(payload),
        dest,
        max_file_bytes=10_000,
        remaining_bytes=10_000,
    )
    assert written == len(payload)
    assert dest.read_bytes() == payload


def test_write_upload_stream_rejects_file_too_large(tmp_path: Path) -> None:
    """A stream past the per-file cap raises file_too_large and leaves no partial."""
    dest = tmp_path / "out.bin"
    with pytest.raises(UploadTooLargeError) as exc_info:
        write_upload_stream(
            _upload(b"x" * 101),
            dest,
            max_file_bytes=100,
            remaining_bytes=10_000,
        )
    assert exc_info.value.reason == "file_too_large"
    assert not dest.exists()


def test_write_upload_stream_rejects_request_too_large(tmp_path: Path) -> None:
    """A stream past the remaining request allowance raises request_too_large."""
    dest = tmp_path / "out.bin"
    with pytest.raises(UploadTooLargeError) as exc_info:
        write_upload_stream(
            _upload(b"y" * 51),
            dest,
            max_file_bytes=10_000,
            remaining_bytes=50,
        )
    assert exc_info.value.reason == "request_too_large"
    assert not dest.exists()


def test_write_upload_stream_accepts_exact_file_cap(tmp_path: Path) -> None:
    """A stream exactly at the per-file cap is accepted byte-identical."""
    dest = tmp_path / "out.bin"
    payload = b"z" * 100
    written = write_upload_stream(
        _upload(payload),
        dest,
        max_file_bytes=100,
        remaining_bytes=100,
    )
    assert written == 100
    assert dest.read_bytes() == payload
