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
