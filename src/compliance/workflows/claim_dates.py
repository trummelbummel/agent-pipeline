"""Compatibility re-export — date gates live in ``compliance.claim_dates``.

Kept so existing imports of ``compliance.workflows.claim_dates`` (including the
untouched graph-level regression suite) resolve without editing callers.
"""

from __future__ import annotations

from compliance.claim_dates import (
    _departure_beyond_days,
    _reference_today,
    _suspicious_dating,
    _unique_calendar_dates,
)

__all__ = [
    "_departure_beyond_days",
    "_reference_today",
    "_suspicious_dating",
    "_unique_calendar_dates",
]
