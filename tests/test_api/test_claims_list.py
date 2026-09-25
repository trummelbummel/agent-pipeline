"""Nyquist stubs for GET /claims list (R019) — implemented in 05-02."""

from __future__ import annotations

import pytest

_XFAIL = pytest.mark.xfail(
    strict=False,
    reason="Wave 0 stub — implemented in 05-01/05-02",
)


@_XFAIL
def test_list_claims_empty_results_dir_returns_empty_list() -> None:
    """GET /claims with empty results_dir returns 200 and []."""
    raise NotImplementedError("Wave 0 stub — routes in 05-02")


@_XFAIL
def test_list_claims_includes_optional_artifacts_stable_order() -> None:
    """GET /claims lists results ordered by claim_id with optional artifacts."""
    raise NotImplementedError("Wave 0 stub — routes in 05-02")
