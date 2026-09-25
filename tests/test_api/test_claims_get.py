"""Nyquist stubs for GET /claims/{claim_id} (R018) — implemented in 05-02."""

from __future__ import annotations

import pytest

_XFAIL = pytest.mark.xfail(
    strict=False,
    reason="Wave 0 stub — implemented in 05-01/05-02",
)


@_XFAIL
def test_get_claim_runs_process_then_analyze_returns_decision() -> None:
    """GET /claims/{id} runs process_then_analyze and returns decision JSON."""
    raise NotImplementedError("Wave 0 stub — routes in 05-02")


@_XFAIL
def test_get_claim_missing_raw_folder_returns_404() -> None:
    """GET unknown claim_id returns 404 when raw folder is missing."""
    raise NotImplementedError("Wave 0 stub — routes in 05-02")


@_XFAIL
def test_get_claim_unsafe_id_returns_422() -> None:
    """GET with path-unsafe claim_id returns 422 before filesystem escape."""
    raise NotImplementedError("Wave 0 stub — routes in 05-02")
