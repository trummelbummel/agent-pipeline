from __future__ import annotations

import logging
from typing import Final

_ALLOWED_FIELD_KEYS: Final[frozenset[str]] = frozenset({
    "artifacts",
    "chi_squared",
    "claim",
    "coefficients",
    "confidence",
    "decision",
    "documents",
    "error",
    "extracted",
    "faulty",
    "file",
    "fraud_deny",
    "hitl",
    "label",
    "markdown",
    "model",
    "next_step",
    "path",
    "pictures",
    "png",
    "routed_branch",
    "routed_label",
    "threshold",
    "total",
    "written",
})


def log_branch_decision(
    log: logging.Logger,
    *,
    branch: str,
    outcome: str,
    reason: str,
    level: int = logging.INFO,
    **fields: object,
) -> None:
    """Log a pipeline branching decision in a consistent key=value form.

    :param log: Logger to write to (typically the caller's module logger).
    :param branch: Decision point name (e.g. ``benford``, ``ocr_confidence``).
    :param outcome: Chosen path (e.g. ``DENY``, ``PASS``, ``HITL``, ``SKIP``).
    :param reason: Why that path was taken (e.g. ``fraud``, ``below_threshold``).
    :param level: Logging level; use WARNING for deny / soft-fail paths.
    :param fields: Extra context keys from the allowlist (claim, file, scores, …).
        Unknown keys are dropped; values must not contain PII.
    """
    parts = [f"branch={branch}", f"outcome={outcome}", f"reason={reason}"]
    for key in sorted(fields):
        if key not in _ALLOWED_FIELD_KEYS:
            continue
        value = fields[key]
        if value is None:
            continue
        parts.append(f"{key}={value}")
    log.log(level, " ".join(parts))
