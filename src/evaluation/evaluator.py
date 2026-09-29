from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import cast

from compliance.branch_log import log_branch_decision
from compliance.config.settings import AppConfig
from compliance.models.claim import GroundTruth, is_nan_scalar
from compliance.preprocessing.answer import AnswerReader
from compliance.preprocessing.claim_batch import (
    _validate_claim_dir_name,
    discover_claim_folder_names,
)
from compliance.workflows.artifact_publication import MixedGenerationError, generation_mismatch

logger = logging.getLogger(__name__)


class ClaimStatus(str, Enum):
    """Per-claim classification in a ground-truth-first evaluation batch.

    :cvar SCORED: Readable in-vocabulary ground truth and prediction; generation valid.
    :cvar MISSING_PREDICTION: Ground truth present; prediction file absent.
    :cvar INVALID_PREDICTION: Ground truth present; prediction unparseable, out of
        vocabulary, or refused by the SR-005 generation guard.
    :cvar INVALID_GROUND_TRUTH: Ground truth absent, unparseable, or out of vocabulary
        — excluded from the scored population.
    :cvar UNMATCHED_PREDICTION: Prediction under results_dir with no ground-truth folder.
    """

    SCORED = "scored"
    MISSING_PREDICTION = "missing_prediction"
    INVALID_PREDICTION = "invalid_prediction"
    INVALID_GROUND_TRUTH = "invalid_ground_truth"
    UNMATCHED_PREDICTION = "unmatched_prediction"


@dataclass(frozen=True)
class ClaimOutcome:
    """Typed per-claim evaluation outcome for attribution and matrix placement.

    :param claim_id: Claim folder identifier.
    :param status: Population classification for this claim.
    :param ground_truth: Ground-truth decision when readable and in vocabulary.
    :param prediction: Predicted decision when readable and in vocabulary.
    :param reason: Short stable reason code for non-scored outcomes.
    :param raw_match: Exact decision equality (raw metric rule).
    :param policy_match: Raw match or non-nan acceptable_decision credit.
    :param human_in_the_loop: HITL flag from a scored prediction, else None.
    """

    claim_id: str
    status: ClaimStatus
    ground_truth: str | None
    prediction: str | None
    reason: str | None
    raw_match: bool
    policy_match: bool
    human_in_the_loop: bool | None


@dataclass(frozen=True)
class MetricSet:
    """Named metrics derived from one confusion matrix over one population.

    Rows are the configured labels; columns are the labels plus the unscored
    column. ``accuracy`` is the matrix trace over its total; ``f1_macro`` is
    computed from the same cells so the three cannot describe different sets.

    :param name: Matching-rule name (e.g. ``raw`` or ``policy``).
    :param accuracy: Trace / total of ``confusion_matrix``.
    :param f1_macro: Macro-averaged F1 from the same matrix cells.
    :param confusion_matrix: Counts with shape ``len(labels) x (len(labels)+1)``.
    :param n: Matrix total (equals ground-truth population size).
    """

    name: str
    accuracy: float
    f1_macro: float
    confusion_matrix: list[list[int]]
    n: int


@dataclass(frozen=True)
class EvaluationPopulation:
    """Counts for the ground-truth-first evaluation denominator.

    :param n_ground_truth: Claims with readable in-vocabulary ground truth.
    :param n_scored: Claims with a scorable prediction.
    :param n_missing_prediction: Ground-truth claims with no prediction file.
    :param n_invalid_prediction: Ground-truth claims with an unusable prediction.
    :param n_invalid_ground_truth: Claim folders excluded from the population.
    :param n_unmatched_prediction: Results-only claims with no ground-truth folder.
    :param coverage_rate: ``n_scored / n_ground_truth`` (0.0 when empty).
    """

    n_ground_truth: int
    n_scored: int
    n_missing_prediction: int
    n_invalid_prediction: int
    n_invalid_ground_truth: int
    n_unmatched_prediction: int
    coverage_rate: float


@dataclass(frozen=True)
class EvaluationResult:
    """Ground-truth-first evaluation with named matrix-derived metrics.

    Flat unnamed accuracy fields are intentionally absent — a reader must
    pick a named metric set so the matching rule is never ambiguous. The
    ``raw`` and ``policy`` names exist so a reader always knows which
    matching rule produced a number.

    :param claim_ids: Ground-truth population claim ids in discovery order.
    :param labels: Decision vocabulary for matrix rows and scored columns.
    :param unscored_label: Column name for non-scored ground-truth claims.
    :param outcomes: Per-claim outcomes (population members plus unmatched).
    :param population: Denominator and non-scored counts with coverage_rate.
    :param raw: Exact-match metric set over the ground-truth population.
    :param policy: Same claims and matrix shape as ``raw``; credits a prediction
        equal to a non-nan ``acceptable_decision`` and remaps it onto the true
        label (A5).
    :param human_in_the_loop_true: Scored predictions with HITL True.
    :param human_in_the_loop_false: Scored predictions with HITL False.
    """

    claim_ids: list[str]
    labels: list[str]
    unscored_label: str
    outcomes: list[ClaimOutcome]
    population: EvaluationPopulation
    raw: MetricSet
    policy: MetricSet
    human_in_the_loop_true: int = 0
    human_in_the_loop_false: int = 0


def _raw_match(outcome: ClaimOutcome) -> bool:
    """Exact decision equality for the raw metric set.

    :param outcome: Per-claim outcome carrying match flags.
    :return: Whether the prediction equals the ground-truth decision.
    """
    return outcome.raw_match


def _policy_match(outcome: ClaimOutcome) -> bool:
    """Acceptable-decision-aware match for the policy metric set.

    :param outcome: Per-claim outcome carrying match flags.
    :return: Whether the claim matches under the policy rule.
    """
    return outcome.policy_match


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

        Strict boundary: missing, unparseable, out-of-vocabulary, or
        mixed-generation predictions raise rather than soft-classify.

        :param claim_id: Claim folder name under data_dir / results_dir.
        :return: Structured EvaluationResult for the one-claim batch.
        :raises ValueError: When claim_id is unsafe or a decision is outside labels.
        :raises FileNotFoundError: When predicted or ground-truth JSON is missing.
        :raises MixedGenerationError: When the published run_manifest disagrees with
            ``predicted_answer.json`` — scoring that prediction would report a number
            for a run that never completed as a valid generation.
        """
        _validate_claim_dir_name(claim_id)
        pred = self._read_predicted(claim_id)
        gt = self._read_ground_truth(claim_id)
        labels = list(self._config.evaluation.labels)
        self._require_known_labels(pred.decision, gt.decision, labels)
        outcome = self._outcome_from_pair(claim_id, gt, pred)
        return self._result_from_outcomes([outcome], labels, unmatched=[])

    def evaluate(self) -> EvaluationResult:
        """Evaluate every ground-truth claim under data_dir.

        The denominator is claim folders with readable in-vocabulary
        ``answer.json``. Missing and invalid predictions are counted incorrect;
        invalid ground truth is reported separately and excluded from the
        population. Predictions with no ground-truth folder are unmatched.

        :return: Aggregate EvaluationResult with population and raw metrics.
        """
        labels = list(self._config.evaluation.labels)
        all_classified = [
            self._classified_outcome(claim_id) for claim_id in self._safe_claim_ids(self._ground_truth_claim_ids())
        ]
        population_outcomes = [o for o in all_classified if o.status != ClaimStatus.INVALID_GROUND_TRUTH]
        invalid_gt_outcomes = [o for o in all_classified if o.status == ClaimStatus.INVALID_GROUND_TRUTH]
        classified_ids = {o.claim_id for o in all_classified}
        unmatched = self._unmatched_prediction_outcomes(classified_ids)
        result = self._result_from_outcomes(
            population_outcomes,
            labels,
            unmatched=unmatched,
            invalid_ground_truth=invalid_gt_outcomes,
        )
        logger.info(
            "batch evaluated n_ground_truth=%d n_scored=%d coverage_rate=%.4f "
            "raw_accuracy=%.4f policy_accuracy=%.4f hitl_true=%d hitl_false=%d",
            result.population.n_ground_truth,
            result.population.n_scored,
            result.population.coverage_rate,
            result.raw.accuracy,
            result.policy.accuracy,
            result.human_in_the_loop_true,
            result.human_in_the_loop_false,
        )
        return result

    def _unmatched_prediction_outcomes(
        self,
        classified_ids: set[str],
    ) -> list[ClaimOutcome]:
        """Report results-only claims that have no ground-truth folder.

        :param classified_ids: Claim ids already seen under data_dir discovery.
        :return: Unmatched-prediction outcomes excluded from every metric.
        """
        unmatched: list[ClaimOutcome] = []
        for claim_id in self._safe_claim_ids(self._prediction_claim_ids()):
            if claim_id in classified_ids:
                continue
            unmatched.append(
                ClaimOutcome(
                    claim_id=claim_id,
                    status=ClaimStatus.UNMATCHED_PREDICTION,
                    ground_truth=None,
                    prediction=None,
                    reason="no_ground_truth_folder",
                    raw_match=False,
                    policy_match=False,
                    human_in_the_loop=None,
                )
            )
        return unmatched

    def _safe_claim_ids(self, claim_ids: list[str]) -> list[str]:
        """Filter discovered names through the claim-dir safety check.

        :param claim_ids: Raw folder names from discovery.
        :return: Names that pass ``_validate_claim_dir_name``.
        """
        safe: list[str] = []
        for claim_id in claim_ids:
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
            safe.append(claim_id)
        return safe

    def _ground_truth_claim_ids(self) -> list[str]:
        """List claim folder names under data_dir (ground-truth discovery).

        :return: Claim folder names sorted by numeric id, then name.
        """
        return discover_claim_folder_names(Path(self._config.preprocessing.data_dir))

    def _prediction_claim_ids(self) -> list[str]:
        """List claim folder names under results_dir (unmatched detection).

        :return: Claim folder names sorted by numeric id, then name.
        """
        return discover_claim_folder_names(Path(self._config.preprocessing.results_dir))

    def _classified_outcome(self, claim_id: str) -> ClaimOutcome:
        """Classify one claim without raising for known failure modes.

        :param claim_id: Validated claim folder segment.
        :return: Typed outcome for population accounting.
        """
        gt_result = self._ground_truth_or_invalid(claim_id)
        if isinstance(gt_result, ClaimOutcome):
            return gt_result
        gt = gt_result
        pred_result = self._prediction_or_status(claim_id, gt)
        if isinstance(pred_result, ClaimOutcome):
            return pred_result
        return self._outcome_from_pair(claim_id, gt, pred_result)

    def _ground_truth_or_invalid(self, claim_id: str) -> GroundTruth | ClaimOutcome:
        """Read ground truth or return an invalid-ground-truth outcome.

        :param claim_id: Validated claim folder segment.
        :return: Parsed ground truth, or an invalid outcome with a reason code.
        """
        try:
            gt = self._read_ground_truth(claim_id)
        except Exception as exc:
            log_branch_decision(
                logger,
                branch="evaluation_batch",
                outcome="SKIP",
                reason="invalid_ground_truth",
                level=logging.WARNING,
                claim=claim_id,
                error=type(exc).__name__,
            )
            return ClaimOutcome(
                claim_id=claim_id,
                status=ClaimStatus.INVALID_GROUND_TRUTH,
                ground_truth=None,
                prediction=None,
                reason=type(exc).__name__,
                raw_match=False,
                policy_match=False,
                human_in_the_loop=None,
            )
        labels = list(self._config.evaluation.labels)
        if gt.decision not in set(labels):
            log_branch_decision(
                logger,
                branch="evaluation_batch",
                outcome="SKIP",
                reason="gt_out_of_vocabulary",
                level=logging.WARNING,
                claim=claim_id,
                decision=gt.decision,
            )
            return ClaimOutcome(
                claim_id=claim_id,
                status=ClaimStatus.INVALID_GROUND_TRUTH,
                ground_truth=gt.decision,
                prediction=None,
                reason="gt_out_of_vocabulary",
                raw_match=False,
                policy_match=False,
                human_in_the_loop=None,
            )
        return gt

    def _prediction_or_status(
        self,
        claim_id: str,
        gt: GroundTruth,
    ) -> GroundTruth | ClaimOutcome:
        """Read prediction or return a missing/invalid-prediction outcome.

        :param claim_id: Validated claim folder segment.
        :param gt: Already-validated ground truth for this claim.
        :return: Parsed prediction, or a non-scored outcome with a reason code.
        """
        artifacts = self._config.preprocessing.artifacts
        claim_dir = Path(self._config.preprocessing.results_dir) / claim_id
        path = claim_dir / artifacts.predicted_answer
        if not path.is_file():
            log_branch_decision(
                logger,
                branch="evaluation_batch",
                outcome="SKIP",
                reason="missing_prediction",
                level=logging.WARNING,
                claim=claim_id,
            )
            return ClaimOutcome(
                claim_id=claim_id,
                status=ClaimStatus.MISSING_PREDICTION,
                ground_truth=gt.decision,
                prediction=None,
                reason="missing_prediction",
                raw_match=False,
                policy_match=False,
                human_in_the_loop=None,
            )
        try:
            self._assert_prediction_generation(claim_id, claim_dir)
            pred = cast(GroundTruth, self._reader.read(path))
        except MixedGenerationError as exc:
            log_branch_decision(
                logger,
                branch="evaluation_batch",
                outcome="SKIP",
                reason=exc.reason,
                level=logging.WARNING,
                claim=claim_id,
                error=type(exc).__name__,
            )
            return ClaimOutcome(
                claim_id=claim_id,
                status=ClaimStatus.INVALID_PREDICTION,
                ground_truth=gt.decision,
                prediction=None,
                reason=exc.reason,
                raw_match=False,
                policy_match=False,
                human_in_the_loop=None,
            )
        except Exception as exc:
            log_branch_decision(
                logger,
                branch="evaluation_batch",
                outcome="SKIP",
                reason="invalid_prediction",
                level=logging.WARNING,
                claim=claim_id,
                error=type(exc).__name__,
            )
            return ClaimOutcome(
                claim_id=claim_id,
                status=ClaimStatus.INVALID_PREDICTION,
                ground_truth=gt.decision,
                prediction=None,
                reason=type(exc).__name__,
                raw_match=False,
                policy_match=False,
                human_in_the_loop=None,
            )
        labels = list(self._config.evaluation.labels)
        if pred.decision not in set(labels):
            log_branch_decision(
                logger,
                branch="evaluation_batch",
                outcome="SKIP",
                reason="pred_out_of_vocabulary",
                level=logging.WARNING,
                claim=claim_id,
                decision=pred.decision,
            )
            return ClaimOutcome(
                claim_id=claim_id,
                status=ClaimStatus.INVALID_PREDICTION,
                ground_truth=gt.decision,
                prediction=pred.decision,
                reason="pred_out_of_vocabulary",
                raw_match=False,
                policy_match=False,
                human_in_the_loop=None,
            )
        return pred

    def _outcome_from_pair(
        self,
        claim_id: str,
        gt: GroundTruth,
        pred: GroundTruth,
    ) -> ClaimOutcome:
        """Build a scored outcome with raw and policy match flags.

        :param claim_id: Claim folder identifier.
        :param gt: Ground-truth payload.
        :param pred: Predicted payload.
        :return: Scored ClaimOutcome.
        """
        raw = pred.decision == gt.decision
        policy = self._match_decision(pred, gt)
        return ClaimOutcome(
            claim_id=claim_id,
            status=ClaimStatus.SCORED,
            ground_truth=gt.decision,
            prediction=pred.decision,
            reason=None,
            raw_match=raw,
            policy_match=policy,
            human_in_the_loop=bool(pred.human_in_the_loop),
        )

    def _result_from_outcomes(
        self,
        population_outcomes: list[ClaimOutcome],
        labels: list[str],
        *,
        unmatched: list[ClaimOutcome],
        invalid_ground_truth: list[ClaimOutcome] | None = None,
    ) -> EvaluationResult:
        """Assemble EvaluationResult from classified outcomes.

        :param population_outcomes: Outcomes in the ground-truth denominator.
        :param labels: Config evaluation label vocabulary.
        :param unmatched: Unmatched-prediction outcomes (not in population).
        :param invalid_ground_truth: Invalid-GT outcomes excluded from population.
        :return: Structured result with population and raw MetricSet.
        """
        invalid_gt = invalid_ground_truth or []
        unscored = self._config.evaluation.unscored_label
        raw = self._metric_set(population_outcomes, labels, name="raw", matched=_raw_match)
        policy = self._metric_set(population_outcomes, labels, name="policy", matched=_policy_match)
        n_scored = sum(1 for o in population_outcomes if o.status == ClaimStatus.SCORED)
        n_missing = sum(1 for o in population_outcomes if o.status == ClaimStatus.MISSING_PREDICTION)
        n_invalid_pred = sum(1 for o in population_outcomes if o.status == ClaimStatus.INVALID_PREDICTION)
        n_gt = len(population_outcomes)
        coverage = (n_scored / n_gt) if n_gt else 0.0
        population = EvaluationPopulation(
            n_ground_truth=n_gt,
            n_scored=n_scored,
            n_missing_prediction=n_missing,
            n_invalid_prediction=n_invalid_pred,
            n_invalid_ground_truth=len(invalid_gt),
            n_unmatched_prediction=len(unmatched),
            coverage_rate=coverage,
        )
        hitl_true = sum(1 for o in population_outcomes if o.human_in_the_loop is True)
        hitl_false = sum(1 for o in population_outcomes if o.human_in_the_loop is False)
        all_outcomes = [*population_outcomes, *invalid_gt, *unmatched]
        return EvaluationResult(
            claim_ids=[o.claim_id for o in population_outcomes],
            labels=labels,
            unscored_label=unscored,
            outcomes=all_outcomes,
            population=population,
            raw=raw,
            policy=policy,
            human_in_the_loop_true=hitl_true,
            human_in_the_loop_false=hitl_false,
        )

    def _metric_set(
        self,
        outcomes: list[ClaimOutcome],
        labels: list[str],
        *,
        name: str,
        matched: Callable[[ClaimOutcome], bool],
    ) -> MetricSet:
        """Build a named MetricSet from outcomes via one shared matrix.

        :param outcomes: Ground-truth population outcomes.
        :param labels: Row / scored-column vocabulary.
        :param name: Metric set name.
        :param matched: Callable selecting the match rule for column remapping.
        :return: Matrix-derived accuracy, F1, and confusion matrix.
        """
        matrix = self._confusion_matrix(outcomes, labels, matched)
        total = sum(sum(row) for row in matrix)
        accuracy = self._accuracy_from_matrix(matrix)
        f1_macro = self._macro_f1_from_matrix(matrix, labels)
        return MetricSet(
            name=name,
            accuracy=accuracy,
            f1_macro=f1_macro,
            confusion_matrix=matrix,
            n=total,
        )

    def _confusion_matrix(
        self,
        outcomes: list[ClaimOutcome],
        labels: list[str],
        matched: Callable[[ClaimOutcome], bool],
    ) -> list[list[int]]:
        """Build labels x (labels + unscored) matrix from population outcomes.

        :param outcomes: Ground-truth population outcomes.
        :param labels: Row and scored-column vocabulary.
        :param matched: Match rule for remapping a hit onto the true label.
        :return: Nested count matrix.
        """
        unscored = self._config.evaluation.unscored_label
        columns = [*labels, unscored]
        index = {label: i for i, label in enumerate(labels)}
        col_index = {label: i for i, label in enumerate(columns)}
        n_rows = len(labels)
        n_cols = len(columns)
        matrix = [[0 for _ in range(n_cols)] for _ in range(n_rows)]
        for outcome in outcomes:
            if outcome.ground_truth is None or outcome.ground_truth not in index:
                continue
            row = index[outcome.ground_truth]
            if outcome.status != ClaimStatus.SCORED or outcome.prediction is None:
                matrix[row][col_index[unscored]] += 1
                continue
            if matched(outcome):
                matrix[row][row] += 1
            else:
                matrix[row][col_index[outcome.prediction]] += 1
        return matrix

    def _accuracy_from_matrix(self, matrix: list[list[int]]) -> float:
        """Accuracy as matrix trace over total.

        :param matrix: Confusion matrix with square label block on the left.
        :return: Trace / total, or 0.0 for an empty matrix.
        """
        if not matrix:
            return 0.0
        n_labels = len(matrix)
        total = sum(sum(row) for row in matrix)
        if total == 0:
            return 0.0
        trace = sum(matrix[i][i] for i in range(n_labels))
        return trace / total

    def _macro_f1_from_matrix(self, matrix: list[list[int]], labels: list[str]) -> float:
        """Macro F1 from matrix cells; zero-support labels contribute 0.0.

        :param matrix: Confusion matrix (rows=labels, cols=labels+unscored).
        :param labels: Label vocabulary (row axis).
        :return: Macro-averaged F1.
        """
        if not labels:
            return 0.0
        scores = [self._f1_for_label_from_matrix(matrix, i) for i in range(len(labels))]
        return sum(scores) / len(scores)

    def _f1_for_label_from_matrix(self, matrix: list[list[int]], label_idx: int) -> float:
        """Per-label F1 from matrix cells including the unscored column in FN.

        :param matrix: Confusion matrix.
        :param label_idx: Index of the label in the row/column axes.
        :return: F1 for that label.
        """
        tp = matrix[label_idx][label_idx]
        fp = sum(matrix[r][label_idx] for r in range(len(matrix)) if r != label_idx)
        fn = sum(matrix[label_idx][c] for c in range(len(matrix[label_idx])) if c != label_idx)
        support = tp + fn
        if support == 0:
            return 0.0
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        if precision + recall == 0.0:
            return 0.0
        return 2.0 * precision * recall / (precision + recall)

    def _read_predicted(self, claim_id: str) -> GroundTruth:
        """Load predicted_answer.json for a claim from results_dir.

        :param claim_id: Validated claim folder segment.
        :return: Parsed GroundTruth-shaped prediction.
        :raises MixedGenerationError: When the prediction disagrees with the
            published run manifest for this claim.
        """
        artifacts = self._config.preprocessing.artifacts
        claim_dir = Path(self._config.preprocessing.results_dir) / claim_id
        self._assert_prediction_generation(claim_id, claim_dir)
        path = claim_dir / artifacts.predicted_answer
        return cast(GroundTruth, self._reader.read(path))

    def _assert_prediction_generation(self, claim_id: str, claim_dir: Path) -> None:
        """Refuse to score a prediction that disagrees with the published generation.

        :param claim_id: Claim folder segment (for the error attributes).
        :param claim_dir: ``results_dir/{claim_id}/``.
        :raises MixedGenerationError: When ``generation_mismatch`` returns a reason.
        """
        artifacts = self._config.preprocessing.artifacts
        reason = generation_mismatch(
            claim_dir,
            artifacts.predicted_answer,
            artifacts.run_manifest,
        )
        if reason is not None:
            raise MixedGenerationError(claim_id, artifacts.predicted_answer, reason)

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
        """Return whether prediction matches ground truth under the policy rule.

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
