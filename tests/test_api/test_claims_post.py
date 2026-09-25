"""Nyquist stubs for POST /claims (R017) — implemented in 05-01."""

from __future__ import annotations

import pytest

_XFAIL = pytest.mark.xfail(
    strict=False,
    reason="Wave 0 stub — implemented in 05-01/05-02",
)


@_XFAIL
def test_post_claims_writes_raw_folder() -> None:
    """POST multipart writes description.txt, supporting_documents.md, and image under data_dir/{claim_id}."""
    raise NotImplementedError("Wave 0 stub — create_app in 05-01")


@_XFAIL
def test_post_claims_rejects_disallowed_image_extension() -> None:
    """POST rejects image suffix not in config document_formats with 422."""
    raise NotImplementedError("Wave 0 stub — create_app in 05-01")


@_XFAIL
def test_post_claims_conflict_when_folder_exists() -> None:
    """POST returns 409 when the next claim folder already exists."""
    raise NotImplementedError("Wave 0 stub — create_app in 05-01")


@_XFAIL
def test_post_rejects_path_traversal_image_filename() -> None:
    """POST stores only basename for traversal-like filenames (or 422)."""
    raise NotImplementedError("Wave 0 stub — create_app in 05-01")
