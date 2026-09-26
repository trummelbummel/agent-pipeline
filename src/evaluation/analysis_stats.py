from __future__ import annotations

import json
import logging
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from compliance.branch_log import log_branch_decision
from compliance.config.settings import AppConfig
from compliance.preprocessing.claim_batch import _claim_sort_key
from compliance.workflows.pipeline import _validate_claim_dir_name

logger = logging.getLogger(__name__)

_BOOLEAN_CHECKER_KEYS: tuple[str, ...] = (
    "checker_containment",
    "checker_contradicts",
    "identity_check",
    "identity_unclear",
    "signature_check",
    "healthy_check",
    "checker_missing_documentation",
    "human_in_the_loop",
    "document_has_signature",
)


@dataclass(frozen=True)
class AnalysisStats:
    """Aggregate statistics over ``analysis_result.json`` payloads under results_dir.

    :param claim_ids: Successfully loaded claim folder names in discovery order.
    :param n_claims: Number of successfully loaded analysis payloads.
    :param decision_counts: Frequency of ``decision`` values.
    :param checker_true_counts: True counts for present boolean checker keys.
    :param checker_present_counts: How many payloads included each checker key.
    :param checker_true_rates: ``true_count / present_count`` per checker key.
    :param coverage_label_counts: Flattened ``coverage_labels`` frequencies.
    :param reason_label_counts: Flattened ``reason_labels`` frequencies.
    :param document_label_counts: Flattened ``document_labels`` frequencies.
    :param decision_explanation_counts: Frequency of ``decision_explanation`` values.
    """

    claim_ids: list[str] = field(default_factory=list)
    n_claims: int = 0
    decision_counts: dict[str, int] = field(default_factory=dict)
    checker_true_counts: dict[str, int] = field(default_factory=dict)
    checker_present_counts: dict[str, int] = field(default_factory=dict)
    checker_true_rates: dict[str, float] = field(default_factory=dict)
    coverage_label_counts: dict[str, int] = field(default_factory=dict)
    reason_label_counts: dict[str, int] = field(default_factory=dict)
    document_label_counts: dict[str, int] = field(default_factory=dict)
    decision_explanation_counts: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize stats to a JSON-ready plain dict.

        :return: Mapping with int counts and float rates.
        """
        return asdict(self)


def aggregate_analysis_stats(config: AppConfig) -> AnalysisStats:
    """Aggregate ``analysis_result.json`` statistics under ``results_dir``.

    Soft-skips missing or unreadable payloads with a WARNING branch log.
    Empty discovery yields ``n_claims=0`` with empty count maps.

    :param config: Application config with results_dir and analysis_result filename.
    :return: Frozen ``AnalysisStats`` for the discovered claim folders.
    """
    payloads = _loaded_analysis_payloads(config)
    claim_ids = [claim_id for claim_id, _ in payloads]
    bodies = [body for _, body in payloads]
    true_counts, present_counts, rates = _checker_stats(bodies)
    return AnalysisStats(
        claim_ids=claim_ids,
        n_claims=len(claim_ids),
        decision_counts=_decision_counts(bodies),
        checker_true_counts=true_counts,
        checker_present_counts=present_counts,
        checker_true_rates=rates,
        coverage_label_counts=_label_frequencies(bodies, "coverage_labels"),
        reason_label_counts=_label_frequencies(bodies, "reason_labels"),
        document_label_counts=_label_frequencies(bodies, "document_labels"),
        decision_explanation_counts=_explanation_counts(bodies),
    )


def _loaded_analysis_payloads(config: AppConfig) -> list[tuple[str, dict[str, Any]]]:
    """Discover claim folders and load valid analysis_result JSON bodies.

    :param config: Application config providing results_dir and artifact names.
    :return: ``(claim_id, payload)`` pairs in discovery order.
    """
    results_dir = Path(config.preprocessing.results_dir)
    filename = config.preprocessing.artifacts.analysis_result
    loaded: list[tuple[str, dict[str, Any]]] = []
    for claim_id in _discover_claim_ids(results_dir):
        try:
            _validate_claim_dir_name(claim_id)
        except ValueError as exc:
            log_branch_decision(
                logger,
                branch="analysis_stats",
                outcome="SKIP",
                reason="unsafe_claim_id",
                level=logging.WARNING,
                claim=claim_id,
                error=type(exc).__name__,
            )
            continue
        path = results_dir / claim_id / filename
        payload = _read_analysis_payload(path, claim_id)
        if payload is None:
            continue
        loaded.append((claim_id, payload))
    return loaded


def _discover_claim_ids(results_dir: Path) -> list[str]:
    """List claim folder names under results_dir (same pattern as Evaluator).

    :param results_dir: Root containing claim folders.
    :return: Claim folder names sorted by numeric id, then name.
    """
    if not results_dir.is_dir():
        return []
    folders = [
        path
        for path in results_dir.iterdir()
        if path.is_dir() and path.name.lower().startswith("claim")
    ]
    return [path.name for path in sorted(folders, key=_claim_sort_key)]


def _read_analysis_payload(path: Path, claim_id: str) -> dict[str, Any] | None:
    """Load one analysis_result JSON object, or soft-skip on failure.

    :param path: Absolute path to the analysis_result artifact.
    :param claim_id: Claim folder name for branch logging.
    :return: Parsed object dict, or ``None`` when missing/invalid.
    """
    if not path.is_file():
        log_branch_decision(
            logger,
            branch="analysis_stats",
            outcome="SKIP",
            reason="missing_analysis_result",
            level=logging.WARNING,
            claim=claim_id,
        )
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        log_branch_decision(
            logger,
            branch="analysis_stats",
            outcome="SKIP",
            reason="invalid_analysis_result",
            level=logging.WARNING,
            claim=claim_id,
            error=type(exc).__name__,
        )
        return None
    if not isinstance(raw, dict):
        log_branch_decision(
            logger,
            branch="analysis_stats",
            outcome="SKIP",
            reason="invalid_analysis_result",
            level=logging.WARNING,
            claim=claim_id,
            error="TypeError",
        )
        return None
    return raw


def _decision_counts(payloads: list[dict[str, Any]]) -> dict[str, int]:
    """Count decision values across loaded payloads.

    :param payloads: Successfully loaded analysis_result bodies.
    :return: Decision → count mapping.
    """
    counter: Counter[str] = Counter()
    for body in payloads:
        decision = body.get("decision")
        if isinstance(decision, str) and decision:
            counter[decision] += 1
    return dict(counter)


def _checker_stats(
    payloads: list[dict[str, Any]],
) -> tuple[dict[str, int], dict[str, int], dict[str, float]]:
    """Compute present-only true counts and rates for boolean checker keys.

    :param payloads: Successfully loaded analysis_result bodies.
    :return: ``(true_counts, present_counts, true_rates)`` for keys seen at least once.
    """
    true_counts: dict[str, int] = {}
    present_counts: dict[str, int] = {}
    for body in payloads:
        for key in _BOOLEAN_CHECKER_KEYS:
            if key not in body:
                continue
            present_counts[key] = present_counts.get(key, 0) + 1
            if body[key] is True:
                true_counts[key] = true_counts.get(key, 0) + 1
    rates = {
        key: (true_counts.get(key, 0) / present)
        for key, present in present_counts.items()
        if present > 0
    }
    return true_counts, present_counts, rates


def _label_frequencies(payloads: list[dict[str, Any]], field_name: str) -> dict[str, int]:
    """Flatten list-valued label fields into a frequency map.

    :param payloads: Successfully loaded analysis_result bodies.
    :param field_name: Key whose value is a list of display-name strings.
    :return: Label → count mapping.
    """
    counter: Counter[str] = Counter()
    for body in payloads:
        labels = body.get(field_name)
        if not isinstance(labels, list):
            continue
        for label in labels:
            if isinstance(label, str) and label:
                counter[label] += 1
    return dict(counter)


def _explanation_counts(payloads: list[dict[str, Any]]) -> dict[str, int]:
    """Count decision_explanation string frequencies.

    :param payloads: Successfully loaded analysis_result bodies.
    :return: Explanation → count mapping.
    """
    counter: Counter[str] = Counter()
    for body in payloads:
        explanation = body.get("decision_explanation")
        if isinstance(explanation, str) and explanation:
            counter[explanation] += 1
    return dict(counter)
