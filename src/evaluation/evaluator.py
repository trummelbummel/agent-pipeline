from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from compliance.branch_log import log_branch_decision
from compliance.config.settings import AppConfig
from compliance.models.claim import GroundTruth, is_nan_scalar
from compliance.preprocessing.answer import AnswerReader
from compliance.workflows.pipeline import _validate_claim_dir_name

logger = logging.getLogger(__name__)

_CLAIM_NUM = re.compile(r"(\d+)")


@dataclass(frozen=True)
class EvaluationResult:
    """Structured metrics for one or more evaluated claims.

    :param claim_ids: Claim folder identifiers evaluated.
    :param y_true: Ground-truth decision labels in claim order.
    :param y_pred: Predicted decision labels in claim order.
    :param matches: Per-claim match booleans (A4).
    :param confusion_matrix: Rows=true labels, cols=predicted; axis order = labels.
    :param labels: Decision vocabulary used for the matrix axes.
    :param accuracy: Mean of matches over all GT-backed samples (failed preds count as wrong).
    :param f1_macro: Macro-averaged F1 over all labels (scored pairs only).
    :param n_evaluated: Number of GT-backed samples in the accuracy denominator.
    """

    claim_ids: list[str]
    y_true: list[str]
    y_pred: list[str]
    matches: list[bool]
    confusion_matrix: list[list[int]]
    labels: list[str]
    accuracy: float
    f1_macro: float
    n_evaluated: int


class Evaluator:
    """Score predicted_answer.json against ground-truth answer.json.

    :param config: Application config providing paths and evaluation labels.
    """

    def __init__(self, config: AppConfig) -> None:
        """Store config and answer reader for claim evaluation.

        :param config: Typed application configuration.
        """
        self._config = config
        self._reader = AnswerReader()

    def evaluate_claim(self, claim_id: str) -> EvaluationResult:
        """Evaluate a single claim's prediction against ground truth.

        :param claim_id: Claim folder name under data_dir / results_dir.
        :return: Structured EvaluationResult for the one-claim batch.
        :raises ValueError: When claim_id is unsafe or a decision is outside labels.
        :raises FileNotFoundError: When predicted or ground-truth JSON is missing.
        """
        _validate_claim_dir_name(claim_id)
        pred = self._read_predicted(claim_id)
        gt = self._read_ground_truth(claim_id)
        labels = list(self._config.evaluation.labels)
        self._require_known_labels(pred.decision, gt.decision, labels)
        match = self._match_decision(pred, gt)
        y_true = [gt.decision]
        y_pred = [pred.decision]
        matches = [match]
        effective_pred = [self._effective_pred_label(pred.decision, gt.decision, match)]
        matrix = self._confusion_matrix(y_true, effective_pred, labels)
        accuracy = sum(matches) / len(matches)
        f1_macro = self._macro_f1(y_true, effective_pred, labels)
        result = EvaluationResult(
            claim_ids=[claim_id],
            y_true=y_true,
            y_pred=y_pred,
            matches=matches,
            confusion_matrix=matrix,
            labels=labels,
            accuracy=accuracy,
            f1_macro=f1_macro,
            n_evaluated=1,
        )
        logger.info(
            "evaluated claim_id=%s n=%d accuracy=%.4f f1_macro=%.4f",
            claim_id,
            result.n_evaluated,
            result.accuracy,
            result.f1_macro,
        )
        return result

    def evaluate(self) -> EvaluationResult:
        """Evaluate all discoverable claim pairs under results_dir × data_dir.

        Soft-skips still log and omit incomplete pairs from the confusion
        matrix / F1, but accuracy is always mean(matches) over every sample
        that has ground truth — a missing/invalid prediction counts as wrong.

        Empty set yields n_evaluated=0 with accuracy/f1 0.0.

        :return: Aggregate EvaluationResult; accuracy over all GT-backed samples.
        """
        labels = list(self._config.evaluation.labels)
        claim_ids: list[str] = []
        y_true: list[str] = []
        y_pred: list[str] = []
        scored_matches: list[bool] = []
        all_matches: list[bool] = []
        for claim_id in self._discover_claim_ids():
            try:
                _validate_claim_dir_name(claim_id)
            except ValueError as exc:
                log_branch_decision(
                    logger,
                    branch="evaluation_batch",
                    outcome="SKIP",
                    reason="unsafe_claim_id",
                    level=logging.WARNING,
                    claim=claim_id,
                    error=type(exc).__name__,
                )
                continue
            try:
                single = self.evaluate_claim(claim_id)
            except Exception as exc:
                counted = self._count_failed_claim(claim_id, all_matches, claim_ids)
                log_branch_decision(
                    logger,
                    branch="evaluation_batch",
                    outcome="SKIP",
                    reason="claim_failed",
                    level=logging.WARNING,
                    claim=claim_id,
                    error=type(exc).__name__,
                    counted_as_incorrect=counted,
                )
                continue
            claim_ids.extend(single.claim_ids)
            y_true.extend(single.y_true)
            y_pred.extend(single.y_pred)
            scored_matches.extend(single.matches)
            all_matches.extend(single.matches)
        return self._aggregate_scores(
            claim_ids,
            y_true,
            y_pred,
            scored_matches,
            all_matches,
            labels,
        )

    def _count_failed_claim(
        self,
        claim_id: str,
        all_matches: list[bool],
        claim_ids: list[str],
    ) -> bool:
        """Count a failed claim as incorrect when ground truth is readable.

        Incomplete pairs stay out of the confusion matrix / F1 vectors, but
        still enlarge the accuracy denominator so metrics cover all samples.

        :param claim_id: Claim folder under results_dir.
        :param all_matches: Accumulators of per-sample match flags (accuracy).
        :param claim_ids: Accumulators of claim identifiers in sample order.
        :return: True when the claim was counted as an incorrect sample.
        """
        try:
            self._read_ground_truth(claim_id)
        except Exception:
            return False
        claim_ids.append(claim_id)
        all_matches.append(False)
        return True

    def _discover_claim_ids(self) -> list[str]:
        """List claim folder names under results_dir (A11 discovery).

        :return: Claim folder names sorted by numeric id, then name.
        """
        results_dir = Path(self._config.preprocessing.results_dir)
        if not results_dir.is_dir():
            return []
        folders = [
            path
            for path in results_dir.iterdir()
            if path.is_dir() and path.name.lower().startswith("claim")
        ]
        return [path.name for path in sorted(folders, key=self._claim_sort_key)]

    def _claim_sort_key(self, path: Path) -> tuple[int, str]:
        """Sort key preferring numeric claim ids.

        :param path: Claim folder path under results_dir.
        :return: (number, name) for stable ordering.
        """
        match = _CLAIM_NUM.search(path.name)
        number = int(match.group(1)) if match else 0
        return (number, path.name)

    def _aggregate_scores(
        self,
        claim_ids: list[str],
        y_true: list[str],
        y_pred: list[str],
        scored_matches: list[bool],
        all_matches: list[bool],
        labels: list[str],
    ) -> EvaluationResult:
        """Build EvaluationResult from collected per-claim vectors via A4/A5 helpers.

        Accuracy uses ``all_matches`` (every GT-backed sample). Confusion matrix
        and macro F1 use only fully scored prediction/label pairs.

        :param claim_ids: Claim folder names in sample order (scored + incorrect).
        :param y_true: Ground-truth decisions for fully scored pairs.
        :param y_pred: Raw predicted decisions for fully scored pairs.
        :param scored_matches: A4 match flags aligned with ``y_true`` / ``y_pred``.
        :param all_matches: Match flags for accuracy (includes failed-as-incorrect).
        :param labels: Config evaluation label vocabulary.
        :return: Aggregate metrics with shared confusion/F1 math.
        """
        n_samples = len(all_matches)
        if n_samples == 0:
            empty_matrix = [[0 for _ in labels] for _ in labels]
            result = EvaluationResult(
                claim_ids=[],
                y_true=[],
                y_pred=[],
                matches=[],
                confusion_matrix=empty_matrix,
                labels=labels,
                accuracy=0.0,
                f1_macro=0.0,
                n_evaluated=0,
            )
        else:
            effective = [
                self._effective_pred_label(pred, true, matched)
                for pred, true, matched in zip(
                    y_pred, y_true, scored_matches, strict=True
                )
            ]
            result = EvaluationResult(
                claim_ids=claim_ids,
                y_true=y_true,
                y_pred=y_pred,
                matches=all_matches,
                confusion_matrix=(
                    self._confusion_matrix(y_true, effective, labels)
                    if y_true
                    else [[0 for _ in labels] for _ in labels]
                ),
                labels=labels,
                accuracy=sum(all_matches) / n_samples,
                f1_macro=(
                    self._macro_f1(y_true, effective, labels) if y_true else 0.0
                ),
                n_evaluated=n_samples,
            )
        logger.info(
            "batch evaluated n=%d accuracy=%.4f f1_macro=%.4f",
            result.n_evaluated,
            result.accuracy,
            result.f1_macro,
        )
        return result

    def _read_predicted(self, claim_id: str) -> GroundTruth:
        """Load predicted_answer.json for a claim from results_dir.

        :param claim_id: Validated claim folder segment.
        :return: Parsed GroundTruth-shaped prediction.
        """
        artifacts = self._config.preprocessing.artifacts
        path = (
            Path(self._config.preprocessing.results_dir)
            / claim_id
            / artifacts.predicted_answer
        )
        return cast(GroundTruth, self._reader.read(path))

    def _read_ground_truth(self, claim_id: str) -> GroundTruth:
        """Load answer.json for a claim from data_dir.

        :param claim_id: Validated claim folder segment.
        :return: Parsed ground-truth GroundTruth.
        """
        artifacts = self._config.preprocessing.artifacts
        path = Path(self._config.preprocessing.data_dir) / claim_id / artifacts.answer
        return cast(GroundTruth, self._reader.read(path))

    def _require_known_labels(
        self,
        pred_decision: str,
        gt_decision: str,
        labels: list[str],
    ) -> None:
        """Reject decisions outside the configured vocabulary (T-06-04).

        :param pred_decision: Predicted decision string.
        :param gt_decision: Ground-truth decision string.
        :param labels: Allowed labels from config.evaluation.labels.
        :raises ValueError: When either decision is not in ``labels``.
        """
        allowed = set(labels)
        if gt_decision not in allowed:
            msg = f"ground-truth decision {gt_decision!r} not in evaluation.labels {labels}"
            raise ValueError(msg)
        if pred_decision not in allowed:
            msg = f"predicted decision {pred_decision!r} not in evaluation.labels {labels}"
            raise ValueError(msg)

    def _match_decision(self, pred: GroundTruth, gt: GroundTruth) -> bool:
        """Return whether prediction matches ground truth per A4.

        :param pred: Predicted decision payload.
        :param gt: Ground-truth decision payload.
        :return: True when decisions equal or pred equals non-nan acceptable_decision.
        """
        if pred.decision == gt.decision:
            return True
        acceptable = gt.acceptable_decision
        if isinstance(acceptable, str) and not is_nan_scalar(acceptable):
            return pred.decision == acceptable
        return False

    def _effective_pred_label(self, pred: str, true: str, matched: bool) -> str:
        """Map matched pairs to the true label for F1 (A5).

        :param pred: Raw predicted decision.
        :param true: Ground-truth decision.
        :param matched: Whether the pair matched under A4.
        :return: Effective predicted label for metrics.
        """
        return true if matched else pred

    def _confusion_matrix(
        self,
        y_true: list[str],
        y_pred: list[str],
        labels: list[str],
    ) -> list[list[int]]:
        """Build a square confusion matrix in config label order.

        :param y_true: True labels.
        :param y_pred: Effective predicted labels.
        :param labels: Axis order for rows (true) and columns (pred).
        :return: Nested list matrix of counts.
        """
        index = {label: i for i, label in enumerate(labels)}
        n = len(labels)
        matrix = [[0 for _ in range(n)] for _ in range(n)]
        for true_label, pred_label in zip(y_true, y_pred, strict=True):
            matrix[index[true_label]][index[pred_label]] += 1
        return matrix

    def _macro_f1(
        self,
        y_true: list[str],
        y_pred: list[str],
        labels: list[str],
    ) -> float:
        """Macro-average F1 over all config labels; zero-support → 0.0.

        :param y_true: True labels.
        :param y_pred: Effective predicted labels.
        :param labels: Full label vocabulary from config.
        :return: Macro F1 in ``[0, 1]``.
        """
        if not labels:
            return 0.0
        scores = [self._f1_for_label(y_true, y_pred, label) for label in labels]
        return sum(scores) / len(scores)

    def _f1_for_label(
        self,
        y_true: list[str],
        y_pred: list[str],
        label: str,
    ) -> float:
        """Per-label F1; zero true-support contributes 0.0.

        :param y_true: True labels.
        :param y_pred: Effective predicted labels.
        :param label: Class to score.
        :return: F1 for ``label``.
        """
        tp = sum(1 for t, p in zip(y_true, y_pred, strict=True) if t == label and p == label)
        fp = sum(1 for t, p in zip(y_true, y_pred, strict=True) if t != label and p == label)
        fn = sum(1 for t, p in zip(y_true, y_pred, strict=True) if t == label and p != label)
        support = tp + fn
        if support == 0:
            return 0.0
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        if precision + recall == 0.0:
            return 0.0
        return 2.0 * precision * recall / (precision + recall)
