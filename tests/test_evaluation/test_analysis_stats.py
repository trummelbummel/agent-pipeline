from __future__ import annotations

import json
from pathlib import Path

from compliance.config.settings import (
    AnalysisConfig,
    AppConfig,
    CheckingConfig,
    ClassificationConfig,
    EvaluationConfig,
    ExtractionConfig,
    PreprocessingConfig,
)
from evaluation.analysis_stats import AnalysisStats, aggregate_analysis_stats


def _analysis_config() -> AnalysisConfig:
    stage = ClassificationConfig(
        labels=["1"],
        other_label="False",
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


def _config(results_dir: Path) -> AppConfig:
    """Minimal AppConfig pointing results_dir at a temp tree."""
    return AppConfig(
        preprocessing=PreprocessingConfig(
            data_dir=str(results_dir / "raw"),
            document_formats=["webp", "jpg", "jpeg", "png", "pdf"],
            confidence_threshold=0.7,
            preprocessed_dir=str(results_dir / "preprocessed"),
            results_dir=str(results_dir),
        ),
        extraction=ExtractionConfig(model="test-model", prompt="extract"),
        classification=ClassificationConfig(
            labels=["1"],
            other_label="False",
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
            analysis_stats_artifact="analysis_stats.json",
            analysis_visualization_artifact="analysis_stats_visualization.png",
        ),
    )


def _write_analysis(results_dir: Path, claim_id: str, payload: dict[str, object]) -> None:
    claim_dir = results_dir / claim_id
    claim_dir.mkdir(parents=True, exist_ok=True)
    (claim_dir / "analysis_result.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )


def test_aggregate_two_claims_decisions_and_sorted_ids(tmp_path: Path) -> None:
    results_dir = tmp_path / "results"
    _write_analysis(
        results_dir,
        "claim 10",
        {
            "decision": "APPROVE",
            "decision_explanation": "ok",
            "coverage_labels": ["Trip cancellation or rescheduling"],
            "reason_labels": ["Medical emergency"],
            "document_labels": ["Medical certificate"],
            "checker_containment": True,
            "checker_contradicts": False,
        },
    )
    _write_analysis(
        results_dir,
        "claim 2",
        {
            "decision": "DENY",
            "decision_explanation": "checker_contradicts",
            "coverage_labels": ["Trip cancellation or rescheduling"],
            "reason_labels": [],
            "document_labels": ["False"],
            "checker_contradicts": True,
            "human_in_the_loop": True,
        },
    )
    stats = aggregate_analysis_stats(_config(results_dir))
    assert stats.n_claims == 2
    assert stats.claim_ids == ["claim 2", "claim 10"]
    assert stats.decision_counts == {"APPROVE": 1, "DENY": 1}
    assert stats.coverage_label_counts == {"Trip cancellation or rescheduling": 2}
    assert stats.reason_label_counts == {"Medical emergency": 1}
    assert stats.document_label_counts == {"Medical certificate": 1, "False": 1}
    assert stats.decision_explanation_counts == {
        "ok": 1,
        "checker_contradicts": 1,
    }
    # checker_containment present only on claim 10
    assert stats.checker_present_counts["checker_containment"] == 1
    assert stats.checker_true_counts["checker_containment"] == 1
    assert stats.checker_true_rates["checker_containment"] == 1.0
    # checker_contradicts present on both
    assert stats.checker_present_counts["checker_contradicts"] == 2
    assert stats.checker_true_counts["checker_contradicts"] == 1
    assert stats.checker_true_rates["checker_contradicts"] == 0.5
    # human_in_the_loop present only on claim 2
    assert stats.checker_present_counts["human_in_the_loop"] == 1
    assert stats.checker_true_counts["human_in_the_loop"] == 1


def test_aggregate_soft_skips_missing_and_invalid(tmp_path: Path) -> None:
    results_dir = tmp_path / "results"
    _write_analysis(
        results_dir,
        "claim 1",
        {"decision": "UNCERTAIN", "decision_explanation": "coverage_false_label"},
    )
    (results_dir / "claim 2").mkdir(parents=True)
    bad = results_dir / "claim 3"
    bad.mkdir(parents=True)
    (bad / "analysis_result.json").write_text("{not-json", encoding="utf-8")
    stats = aggregate_analysis_stats(_config(results_dir))
    assert stats.n_claims == 1
    assert stats.claim_ids == ["claim 1"]
    assert stats.decision_counts == {"UNCERTAIN": 1}


def test_aggregate_empty_results_dir(tmp_path: Path) -> None:
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    stats = aggregate_analysis_stats(_config(results_dir))
    assert stats.n_claims == 0
    assert stats.claim_ids == []
    assert stats.decision_counts == {}
    assert stats.checker_true_counts == {}
    assert stats.checker_present_counts == {}
    assert stats.checker_true_rates == {}
    assert stats.coverage_label_counts == {}
    assert stats.reason_label_counts == {}
    assert stats.document_label_counts == {}
    assert stats.decision_explanation_counts == {}
    assert isinstance(stats, AnalysisStats)
