from __future__ import annotations

import json
from pathlib import Path

import pytest

from compliance.config.settings import (
    AnalysisConfig,
    AppConfig,
    CheckingConfig,
    ClassificationConfig,
    EvaluationConfig,
    ExtractionConfig,
    PreprocessingConfig,
)
from evaluation import Evaluator


def _analysis_config() -> AnalysisConfig:
    stage = ClassificationConfig(
        labels=["1"],
        other_label="None",
        model="test-model",
        prompt="classify",
    )
    return AnalysisConfig(
        coverage=stage,
        cancellation_reason=stage,
        cancellation_document=stage,
        personal_effects_document=stage,
        missed_departure_document=stage,
    )


def _config(data_dir: Path, results_dir: Path) -> AppConfig:
    """Minimal AppConfig with evaluation labels for evaluator tests."""
    return AppConfig(
        preprocessing=PreprocessingConfig(
            data_dir=str(data_dir),
            document_formats=["webp", "jpg", "jpeg", "png", "pdf"],
            confidence_threshold=0.7,
            preprocessed_dir=str(data_dir / "preprocessed"),
            results_dir=str(results_dir),
        ),
        extraction=ExtractionConfig(model="test-model", prompt="extract"),
        classification=ClassificationConfig(
            labels=["1"],
            other_label="Other",
            model="test-model",
            prompt="classify",
        ),
        checking=CheckingConfig(
            model="test-model",
            containment_prompt="containment",
            contradicts_prompt="contradicts",
            identity_prompt="identity",
            healthy_prompt="healthy",
        ),
        analysis=_analysis_config(),
        evaluation=EvaluationConfig(
            labels=["APPROVE", "DENY", "UNCERTAIN"],
            metrics_artifact="evaluation_metrics.json",
        ),
    )


def _write_pair(
    data_dir: Path,
    results_dir: Path,
    claim_id: str,
    *,
    gt: dict[str, object],
    pred: dict[str, object],
) -> None:
    gt_dir = data_dir / claim_id
    pred_dir = results_dir / claim_id
    gt_dir.mkdir(parents=True, exist_ok=True)
    pred_dir.mkdir(parents=True, exist_ok=True)
    (gt_dir / "answer.json").write_text(json.dumps(gt), encoding="utf-8")
    (pred_dir / "predicted_answer.json").write_text(json.dumps(pred), encoding="utf-8")


def test_evaluate_claim_perfect_match(tmp_path: Path) -> None:
    data_dir = tmp_path / "raw"
    results_dir = tmp_path / "results"
    claim_id = "claim 1"
    _write_pair(
        data_dir,
        results_dir,
        claim_id,
        gt={"decision": "DENY"},
        pred={"decision": "DENY"},
    )
    result = Evaluator(_config(data_dir, results_dir)).evaluate_claim(claim_id)
    assert result.accuracy == 1.0
    assert result.n_evaluated == 1
    assert result.matches == [True]
    # A5: macro mean over all 3 labels; only DENY has support → F1=1; others 0 → ≈1/3
    assert result.f1_macro == pytest.approx(1.0 / 3.0)
    assert len(result.confusion_matrix) == 3
    assert len(result.confusion_matrix[0]) == 3
    deny_idx = result.labels.index("DENY")
    assert result.confusion_matrix[deny_idx][deny_idx] == 1


def test_evaluate_claim_mismatch(tmp_path: Path) -> None:
    data_dir = tmp_path / "raw"
    results_dir = tmp_path / "results"
    claim_id = "claim 2"
    _write_pair(
        data_dir,
        results_dir,
        claim_id,
        gt={"decision": "DENY"},
        pred={"decision": "APPROVE"},
    )
    result = Evaluator(_config(data_dir, results_dir)).evaluate_claim(claim_id)
    assert result.accuracy == 0.0
    assert result.matches == [False]
    off_diagonal = sum(
        result.confusion_matrix[i][j]
        for i in range(len(result.labels))
        for j in range(len(result.labels))
        if i != j
    )
    assert off_diagonal == 1


def test_refuses_unsafe_claim_id(tmp_path: Path) -> None:
    data_dir = tmp_path / "raw"
    results_dir = tmp_path / "results"
    evaluator = Evaluator(_config(data_dir, results_dir))
    with pytest.raises(ValueError):
        evaluator.evaluate_claim("../escape")
    with pytest.raises(ValueError):
        evaluator.evaluate_claim("claim/nested")


def test_evaluator_import_requires_no_network() -> None:
    """Importing evaluation.Evaluator must not require live Ollama or network."""
    from evaluation import Evaluator as Ev

    assert Ev is Evaluator


def test_acceptable_decision_counts_as_match(tmp_path: Path) -> None:
    data_dir = tmp_path / "raw"
    results_dir = tmp_path / "results"
    claim_id = "claim 13"
    _write_pair(
        data_dir,
        results_dir,
        claim_id,
        gt={"decision": "UNCERTAIN", "acceptable_decision": "DENY"},
        pred={"decision": "DENY"},
    )
    result = Evaluator(_config(data_dir, results_dir)).evaluate_claim(claim_id)
    assert result.matches == [True]
    assert result.accuracy == 1.0
    # A5: effective pred remapped to UNCERTAIN when matched via acceptable_decision
    uncertain_idx = result.labels.index("UNCERTAIN")
    assert result.confusion_matrix[uncertain_idx][uncertain_idx] == 1
    assert result.f1_macro == pytest.approx(1.0 / 3.0)


def test_acceptable_decision_ignored_when_nan(tmp_path: Path) -> None:
    data_dir = tmp_path / "raw"
    results_dir = tmp_path / "results"
    claim_id = "claim 3"
    _write_pair(
        data_dir,
        results_dir,
        claim_id,
        gt={"decision": "DENY", "acceptable_decision": None},
        pred={"decision": "UNCERTAIN"},
    )
    result = Evaluator(_config(data_dir, results_dir)).evaluate_claim(claim_id)
    assert result.matches == [False]
    assert result.accuracy == 0.0


def test_confusion_matrix_label_order(tmp_path: Path) -> None:
    data_dir = tmp_path / "raw"
    results_dir = tmp_path / "results"
    claim_id = "claim 4"
    custom_labels = ["UNCERTAIN", "APPROVE", "DENY"]
    _write_pair(
        data_dir,
        results_dir,
        claim_id,
        gt={"decision": "APPROVE"},
        pred={"decision": "APPROVE"},
    )
    config = _config(data_dir, results_dir)
    config = config.model_copy(
        update={
            "evaluation": EvaluationConfig(
                labels=custom_labels,
                metrics_artifact="evaluation_metrics.json",
            )
        }
    )
    result = Evaluator(config).evaluate_claim(claim_id)
    assert result.labels == custom_labels
    assert len(result.confusion_matrix) == len(custom_labels)
    assert all(len(row) == len(custom_labels) for row in result.confusion_matrix)
    approve_idx = custom_labels.index("APPROVE")
    assert result.confusion_matrix[approve_idx][approve_idx] == 1


def test_unknown_pred_label_raises(tmp_path: Path) -> None:
    data_dir = tmp_path / "raw"
    results_dir = tmp_path / "results"
    claim_id = "claim 5"
    _write_pair(
        data_dir,
        results_dir,
        claim_id,
        gt={"decision": "DENY"},
        pred={"decision": "OTHER"},
    )
    with pytest.raises(ValueError, match="not in"):
        Evaluator(_config(data_dir, results_dir)).evaluate_claim(claim_id)


def test_evaluate_batch_aggregates_two_claims(tmp_path: Path) -> None:
    data_dir = tmp_path / "raw"
    results_dir = tmp_path / "results"
    _write_pair(
        data_dir,
        results_dir,
        "claim 1",
        gt={"decision": "DENY"},
        pred={"decision": "DENY"},
    )
    _write_pair(
        data_dir,
        results_dir,
        "claim 2",
        gt={"decision": "APPROVE"},
        pred={"decision": "APPROVE"},
    )
    result = Evaluator(_config(data_dir, results_dir)).evaluate()
    assert result.n_evaluated == 2
    assert result.accuracy == 1.0
    assert sum(sum(row) for row in result.confusion_matrix) == 2
    assert set(result.claim_ids) == {"claim 1", "claim 2"}


def test_evaluate_batch_skips_missing_prediction(tmp_path: Path) -> None:
    data_dir = tmp_path / "raw"
    results_dir = tmp_path / "results"
    _write_pair(
        data_dir,
        results_dir,
        "claim 1",
        gt={"decision": "DENY"},
        pred={"decision": "DENY"},
    )
    missing_pred = data_dir / "claim 2"
    missing_pred.mkdir(parents=True)
    (missing_pred / "answer.json").write_text(
        json.dumps({"decision": "APPROVE"}), encoding="utf-8"
    )
    (results_dir / "claim 2").mkdir(parents=True)
    result = Evaluator(_config(data_dir, results_dir)).evaluate()
    # Missing prediction still counts as an incorrect sample for accuracy.
    assert result.n_evaluated == 2
    assert result.accuracy == 0.5
    assert set(result.claim_ids) == {"claim 1", "claim 2"}
    assert sum(sum(row) for row in result.confusion_matrix) == 1
    assert result.y_true == ["DENY"]
    assert result.y_pred == ["DENY"]

def test_evaluate_batch_skips_missing_ground_truth(tmp_path: Path) -> None:
    data_dir = tmp_path / "raw"
    results_dir = tmp_path / "results"
    _write_pair(
        data_dir,
        results_dir,
        "claim 1",
        gt={"decision": "DENY"},
        pred={"decision": "DENY"},
    )
    orphan = results_dir / "claim 3"
    orphan.mkdir(parents=True)
    (orphan / "predicted_answer.json").write_text(
        json.dumps({"decision": "APPROVE"}), encoding="utf-8"
    )
    (data_dir / "claim 3").mkdir(parents=True)
    result = Evaluator(_config(data_dir, results_dir)).evaluate()
    assert result.n_evaluated == 1
    assert result.claim_ids == ["claim 1"]


def test_evaluate_batch_empty(tmp_path: Path) -> None:
    data_dir = tmp_path / "raw"
    results_dir = tmp_path / "results"
    data_dir.mkdir()
    results_dir.mkdir()
    result = Evaluator(_config(data_dir, results_dir)).evaluate()
    assert result.n_evaluated == 0
    assert result.accuracy == 0.0
    assert result.f1_macro == 0.0
    assert result.claim_ids == []
    assert sum(sum(row) for row in result.confusion_matrix) == 0


def test_evaluate_batch_refuses_unsafe_names_in_discovery(tmp_path: Path) -> None:
    data_dir = tmp_path / "raw"
    results_dir = tmp_path / "results"
    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "secret.json"
    secret.write_text('{"decision":"APPROVE"}', encoding="utf-8")
    _write_pair(
        data_dir,
        results_dir,
        "claim 1",
        gt={"decision": "DENY"},
        pred={"decision": "DENY"},
    )
    evaluator = Evaluator(_config(data_dir, results_dir))

    def _unsafe_names() -> list[str]:
        return ["../escape", "claim/nested", "claim 1"]

    evaluator._discover_claim_ids = _unsafe_names  # type: ignore[method-assign]
    result = evaluator.evaluate()
    assert result.n_evaluated == 1
    assert result.claim_ids == ["claim 1"]
    # Unsafe names must not escape roots to read sibling files
    assert secret.read_text(encoding="utf-8") == '{"decision":"APPROVE"}'
