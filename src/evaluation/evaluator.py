from __future__ import annotations

from dataclasses import dataclass, field

from compliance.config.settings import AppConfig


@dataclass
class EvaluationResult:
    """Structured metrics for one or more evaluated claims.

    :param claim_ids: Claim folder identifiers evaluated.
    :param y_true: Ground-truth decision labels in claim order.
    :param y_pred: Predicted decision labels in claim order.
    :param matches: Per-claim match booleans (A4).
    :param confusion_matrix: Rows=true labels, cols=predicted; axis order = labels.
    :param labels: Decision vocabulary used for the matrix axes.
    :param accuracy: Mean of matches.
    :param f1_macro: Macro-averaged F1 over all labels.
    :param n_evaluated: Number of claims scored.
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

    Stub for TDD RED — returns intentionally wrong metrics until GREEN.

    :param config: Application config providing paths and evaluation labels.
    """

    def __init__(self, config: AppConfig) -> None:
        """Store config for claim evaluation.

        :param config: Typed application configuration.
        """
        self._config = config

    def evaluate_claim(self, claim_id: str) -> EvaluationResult:
        """Evaluate a single claim (stub — wrong metrics, no path safety).

        :param claim_id: Claim folder name under data_dir / results_dir.
        :return: Intentionally incorrect EvaluationResult for RED gate.
        """
        labels = ["APPROVE", "DENY", "UNCERTAIN"]
        return EvaluationResult(
            claim_ids=[claim_id],
            y_true=["DENY"],
            y_pred=["DENY"],
            matches=[False],
            confusion_matrix=[[0, 0, 0], [0, 0, 0], [0, 0, 0]],
            labels=labels,
            accuracy=-1.0,
            f1_macro=-1.0,
            n_evaluated=1,
        )
