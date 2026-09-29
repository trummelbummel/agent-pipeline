from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from compliance.config.settings import EvaluationConfig
from evaluation import Evaluator

if TYPE_CHECKING:
    from conftest import MinimalAppConfigFactory


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


def test_evaluate_claim_perfect_match(
    tmp_path: Path,
    minimal_app_config_factory: MinimalAppConfigFactory,
) -> None:
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
    config = minimal_app_config_factory(
        data_dir,
        preprocessed_dir=data_dir / "preprocessed",
        results_dir=results_dir,
        extraction_prompt="extract",
    )
    result = Evaluator(config).evaluate_claim(claim_id)
    assert result.accuracy == 1.0
    assert result.n_evaluated == 1
    assert result.matches == [True]
    assert result.human_in_the_loop_true == 0
    assert result.human_in_the_loop_false == 1
    # A5: macro mean over all 3 labels; only DENY has support → F1=1; others 0 → ≈1/3
    assert result.f1_macro == pytest.approx(1.0 / 3.0)
    assert len(result.confusion_matrix) == 3
    assert len(result.confusion_matrix[0]) == 3
    deny_idx = result.labels.index("DENY")
    assert result.confusion_matrix[deny_idx][deny_idx] == 1


def test_evaluate_claim_rejects_mixed_generation(
    tmp_path: Path,
    minimal_app_config_factory: MinimalAppConfigFactory,
) -> None:
    from compliance.workflows.artifact_publication import MixedGenerationError

    data_dir = tmp_path / "raw"
    results_dir = tmp_path / "results"
    claim_id = "claim 1"
    _write_pair(
        data_dir,
        results_dir,
        claim_id,
        gt={"decision": "DENY"},
        pred={"decision": "DENY", "run_id": "20260929T120000-newrun02"},
    )
    (results_dir / claim_id / "run_manifest.json").write_text(
        json.dumps({
            "run_id": "20260929T110000-oldrun01",
            "published_at": "2026-09-29T11:00:00Z",
            "source": "analysis",
            "artifacts": ["predicted_answer.json"],
        })
        + "\n",
        encoding="utf-8",
    )
    config = minimal_app_config_factory(
        data_dir,
        preprocessed_dir=data_dir / "preprocessed",
        results_dir=results_dir,
        extraction_prompt="extract",
    )
    with pytest.raises(MixedGenerationError) as exc_info:
        Evaluator(config).evaluate_claim(claim_id)
    assert exc_info.value.claim_id == claim_id
    assert exc_info.value.artifact == "predicted_answer.json"
    assert exc_info.value.reason == "run_id_mismatch"


def test_batch_counts_mixed_generation_as_incorrect(
    tmp_path: Path,
    minimal_app_config_factory: MinimalAppConfigFactory,
) -> None:
    data_dir = tmp_path / "raw"
    results_dir = tmp_path / "results"
    _write_pair(
        data_dir,
        results_dir,
        "claim 1",
        gt={"decision": "DENY"},
        pred={"decision": "DENY", "run_id": "20260929T120000-okrun001"},
    )
    (results_dir / "claim 1" / "run_manifest.json").write_text(
        json.dumps({
            "run_id": "20260929T120000-okrun001",
            "published_at": "2026-09-29T12:00:00Z",
            "source": "analysis",
            "artifacts": ["predicted_answer.json"],
        })
        + "\n",
        encoding="utf-8",
    )
    _write_pair(
        data_dir,
        results_dir,
        "claim 2",
        gt={"decision": "APPROVE"},
        pred={"decision": "APPROVE", "run_id": "20260929T120000-newrun02"},
    )
    (results_dir / "claim 2" / "run_manifest.json").write_text(
        json.dumps({
            "run_id": "20260929T110000-oldrun01",
            "published_at": "2026-09-29T11:00:00Z",
            "source": "analysis",
            "artifacts": ["predicted_answer.json"],
        })
        + "\n",
        encoding="utf-8",
    )
    config = minimal_app_config_factory(
        data_dir,
        preprocessed_dir=data_dir / "preprocessed",
        results_dir=results_dir,
        extraction_prompt="extract",
    )
    result = Evaluator(config).evaluate()
    assert result.n_evaluated == 2
    assert "claim 2" in result.claim_ids
    assert result.y_true == ["DENY"]
    assert result.y_pred == ["DENY"]
    assert result.accuracy == 0.5


def test_batch_scores_claim_without_manifest(
    tmp_path: Path,
    minimal_app_config_factory: MinimalAppConfigFactory,
) -> None:
    """P-04: legacy trees without run_manifest.json still score."""
    data_dir = tmp_path / "raw"
    results_dir = tmp_path / "results"
    _write_pair(
        data_dir,
        results_dir,
        "claim 1",
        gt={"decision": "DENY"},
        pred={"decision": "DENY"},
    )
    config = minimal_app_config_factory(
        data_dir,
        preprocessed_dir=data_dir / "preprocessed",
        results_dir=results_dir,
        extraction_prompt="extract",
    )
    result = Evaluator(config).evaluate()
    assert result.n_evaluated == 1
    assert result.claim_ids == ["claim 1"]
    assert result.accuracy == 1.0
    assert result.matches == [True]


def test_evaluate_claim_mismatch(
    tmp_path: Path,
    minimal_app_config_factory: MinimalAppConfigFactory,
) -> None:
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
    config = minimal_app_config_factory(
        data_dir,
        preprocessed_dir=data_dir / "preprocessed",
        results_dir=results_dir,
        extraction_prompt="extract",
    )
    result = Evaluator(config).evaluate_claim(claim_id)
    assert result.accuracy == 0.0
    assert result.matches == [False]
    off_diagonal = sum(
        result.confusion_matrix[i][j] for i in range(len(result.labels)) for j in range(len(result.labels)) if i != j
    )
    assert off_diagonal == 1


def test_refuses_unsafe_claim_id(
    tmp_path: Path,
    minimal_app_config_factory: MinimalAppConfigFactory,
) -> None:
    data_dir = tmp_path / "raw"
    results_dir = tmp_path / "results"
    config = minimal_app_config_factory(
        data_dir,
        preprocessed_dir=data_dir / "preprocessed",
        results_dir=results_dir,
        extraction_prompt="extract",
    )
    evaluator = Evaluator(config)
    with pytest.raises(ValueError):
        evaluator.evaluate_claim("../escape")
    with pytest.raises(ValueError):
        evaluator.evaluate_claim("claim/nested")


def test_evaluator_import_requires_no_network() -> None:
    """Importing evaluation.Evaluator must not require live Ollama or network."""
    from evaluation import Evaluator as Ev

    assert Ev is Evaluator


def test_acceptable_decision_counts_as_match(
    tmp_path: Path,
    minimal_app_config_factory: MinimalAppConfigFactory,
) -> None:
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
    config = minimal_app_config_factory(
        data_dir,
        preprocessed_dir=data_dir / "preprocessed",
        results_dir=results_dir,
        extraction_prompt="extract",
    )
    result = Evaluator(config).evaluate_claim(claim_id)
    assert result.matches == [True]
    assert result.accuracy == 1.0
    # A5: effective pred remapped to UNCERTAIN when matched via acceptable_decision
    uncertain_idx = result.labels.index("UNCERTAIN")
    assert result.confusion_matrix[uncertain_idx][uncertain_idx] == 1
    assert result.f1_macro == pytest.approx(1.0 / 3.0)


def test_acceptable_decision_ignored_when_nan(
    tmp_path: Path,
    minimal_app_config_factory: MinimalAppConfigFactory,
) -> None:
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
    config = minimal_app_config_factory(
        data_dir,
        preprocessed_dir=data_dir / "preprocessed",
        results_dir=results_dir,
        extraction_prompt="extract",
    )
    result = Evaluator(config).evaluate_claim(claim_id)
    assert result.matches == [False]
    assert result.accuracy == 0.0


def test_confusion_matrix_label_order(
    tmp_path: Path,
    minimal_app_config_factory: MinimalAppConfigFactory,
) -> None:
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
    config = minimal_app_config_factory(
        data_dir,
        preprocessed_dir=data_dir / "preprocessed",
        results_dir=results_dir,
        extraction_prompt="extract",
        evaluation=EvaluationConfig(
            labels=custom_labels,
            metrics_artifact="evaluation_metrics.json",
        ),
    )
    result = Evaluator(config).evaluate_claim(claim_id)
    assert result.labels == custom_labels
    assert len(result.confusion_matrix) == len(custom_labels)
    assert all(len(row) == len(custom_labels) for row in result.confusion_matrix)
    approve_idx = custom_labels.index("APPROVE")
    assert result.confusion_matrix[approve_idx][approve_idx] == 1


def test_unknown_pred_label_raises(
    tmp_path: Path,
    minimal_app_config_factory: MinimalAppConfigFactory,
) -> None:
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
    config = minimal_app_config_factory(
        data_dir,
        preprocessed_dir=data_dir / "preprocessed",
        results_dir=results_dir,
        extraction_prompt="extract",
    )
    with pytest.raises(ValueError, match="not in"):
        Evaluator(config).evaluate_claim(claim_id)


def test_evaluate_batch_aggregates_two_claims(
    tmp_path: Path,
    minimal_app_config_factory: MinimalAppConfigFactory,
) -> None:
    data_dir = tmp_path / "raw"
    results_dir = tmp_path / "results"
    _write_pair(
        data_dir,
        results_dir,
        "claim 1",
        gt={"decision": "DENY"},
        pred={"decision": "DENY", "human_in_the_loop": True},
    )
    _write_pair(
        data_dir,
        results_dir,
        "claim 2",
        gt={"decision": "APPROVE"},
        pred={"decision": "APPROVE", "human_in_the_loop": False},
    )
    config = minimal_app_config_factory(
        data_dir,
        preprocessed_dir=data_dir / "preprocessed",
        results_dir=results_dir,
        extraction_prompt="extract",
    )
    result = Evaluator(config).evaluate()
    assert result.n_evaluated == 2
    assert result.accuracy == 1.0
    assert result.human_in_the_loop_true == 1
    assert result.human_in_the_loop_false == 1
    assert sum(sum(row) for row in result.confusion_matrix) == 2
    assert set(result.claim_ids) == {"claim 1", "claim 2"}


def test_evaluate_batch_skips_missing_prediction(
    tmp_path: Path,
    minimal_app_config_factory: MinimalAppConfigFactory,
) -> None:
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
    (missing_pred / "answer.json").write_text(json.dumps({"decision": "APPROVE"}), encoding="utf-8")
    (results_dir / "claim 2").mkdir(parents=True)
    config = minimal_app_config_factory(
        data_dir,
        preprocessed_dir=data_dir / "preprocessed",
        results_dir=results_dir,
        extraction_prompt="extract",
    )
    result = Evaluator(config).evaluate()
    # Missing prediction still counts as an incorrect sample for accuracy.
    assert result.n_evaluated == 2
    assert result.accuracy == 0.5
    assert set(result.claim_ids) == {"claim 1", "claim 2"}
    assert sum(sum(row) for row in result.confusion_matrix) == 1
    assert result.y_true == ["DENY"]
    assert result.y_pred == ["DENY"]


def test_evaluate_batch_skips_missing_ground_truth(
    tmp_path: Path,
    minimal_app_config_factory: MinimalAppConfigFactory,
) -> None:
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
    (orphan / "predicted_answer.json").write_text(json.dumps({"decision": "APPROVE"}), encoding="utf-8")
    (data_dir / "claim 3").mkdir(parents=True)
    config = minimal_app_config_factory(
        data_dir,
        preprocessed_dir=data_dir / "preprocessed",
        results_dir=results_dir,
        extraction_prompt="extract",
    )
    result = Evaluator(config).evaluate()
    assert result.n_evaluated == 1
    assert result.claim_ids == ["claim 1"]


def test_evaluate_batch_empty(
    tmp_path: Path,
    minimal_app_config_factory: MinimalAppConfigFactory,
) -> None:
    data_dir = tmp_path / "raw"
    results_dir = tmp_path / "results"
    data_dir.mkdir()
    results_dir.mkdir()
    config = minimal_app_config_factory(
        data_dir,
        preprocessed_dir=data_dir / "preprocessed",
        results_dir=results_dir,
        extraction_prompt="extract",
    )
    result = Evaluator(config).evaluate()
    assert result.n_evaluated == 0
    assert result.accuracy == 0.0
    assert result.f1_macro == 0.0
    assert result.claim_ids == []
    assert sum(sum(row) for row in result.confusion_matrix) == 0


def test_evaluate_batch_refuses_unsafe_names_in_discovery(
    tmp_path: Path,
    minimal_app_config_factory: MinimalAppConfigFactory,
) -> None:
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
    config = minimal_app_config_factory(
        data_dir,
        preprocessed_dir=data_dir / "preprocessed",
        results_dir=results_dir,
        extraction_prompt="extract",
    )
    evaluator = Evaluator(config)

    def _unsafe_names() -> list[str]:
        return ["../escape", "claim/nested", "claim 1"]

    evaluator._discover_claim_ids = _unsafe_names  # type: ignore[method-assign]
    result = evaluator.evaluate()
    assert result.n_evaluated == 1
    assert result.claim_ids == ["claim 1"]
    # Unsafe names must not escape roots to read sibling files
    assert secret.read_text(encoding="utf-8") == '{"decision":"APPROVE"}'
