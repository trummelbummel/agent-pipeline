"""Nyquist stubs for lifespan DI (R021) — implemented in 05-01."""

from __future__ import annotations

import pytest

_XFAIL = pytest.mark.xfail(
    strict=False,
    reason="Wave 0 stub — implemented in 05-01/05-02",
)


@_XFAIL
def test_lifespan_exposes_pipelines_via_depends() -> None:
    """Lifespan yields PreprocessingPipeline and ClaimPipeline accessible via Depends."""
    raise NotImplementedError("Wave 0 stub — create_app in 05-01")
