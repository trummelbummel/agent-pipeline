from __future__ import annotations

import json
from pathlib import Path

from evaluation.__main__ import main


def _write_minimal_config(tmp_path: Path, data_dir: Path, results_dir: Path) -> Path:
    """Write a minimal AppConfig YAML pointing at tmp roots."""
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        f"""
preprocessing:
  data_dir: {data_dir}
  document_formats: [webp, jpg, jpeg, png, pdf]
  confidence_threshold: 0.7
  preprocessed_dir: {tmp_path / "preprocessed"}
  results_dir: {results_dir}
extraction:
  model: test-model
  prompt: |
    extract
classification:
  labels: ["1"]
  other_label: "False"
  model: test-model
  prompt: |
    classify
checking:
  model: test-model
  containment_prompt: containment
  contradicts_prompt: contradicts
  identity_prompt: identity
  healthy_prompt: healthy
  authenticity_prompt: authenticity
  incomplete_prompt: incomplete
analysis:
  coverage:
    labels: ["1"]
    branches:
      "1": cancellation
    other_label: "False"
    model: test-model
    prompt: classify coverage
  cancellation_reason:
    labels: ["1"]
    other_label: "False"
    model: test-model
    prompt: classify reason
  cancellation_document:
    labels: ["1"]
    other_label: "False"
    model: test-model
    prompt: classify cancel doc
  personal_effects_document:
    labels: ["1"]
    other_label: "False"
    model: test-model
    prompt: classify pe doc
  missed_departure_document:
    labels: ["1"]
    other_label: "False"
    model: test-model
    prompt: classify missed doc
logging:
  level: INFO
  format: "%(levelname)s %(message)s"
evaluation:
  labels: [APPROVE, DENY, UNCERTAIN]
  metrics_artifact: evaluation_metrics.json
  confusion_matrix_artifact: confusion_matrix.json
  visualization_artifact: evaluation_visualization.png
  analysis_stats_artifact: analysis_stats.json
  analysis_visualization_artifact: analysis_stats_visualization.png
""",
        encoding="utf-8",
    )
    return config_path


def test_cli_writes_metrics_json(tmp_path: Path) -> None:
    data_dir = tmp_path / "raw"
    results_dir = tmp_path / "results"
    claim_id = "claim 1"
    gt_dir = data_dir / claim_id
    pred_dir = results_dir / claim_id
    gt_dir.mkdir(parents=True)
    pred_dir.mkdir(parents=True)
    (gt_dir / "answer.json").write_text(json.dumps({"decision": "DENY"}), encoding="utf-8")
    (pred_dir / "predicted_answer.json").write_text(json.dumps({"decision": "DENY"}), encoding="utf-8")
    (pred_dir / "analysis_result.json").write_text(
        json.dumps({
            "decision": "DENY",
            "decision_explanation": "checker_contradicts",
            "coverage_labels": ["Trip cancellation or rescheduling"],
            "reason_labels": [],
            "document_labels": [],
            "checker_contradicts": True,
        }),
        encoding="utf-8",
    )
    config_path = _write_minimal_config(tmp_path, data_dir, results_dir)
    exit_code = main(["--config", str(config_path)])
    assert exit_code == 0
    metrics_path = results_dir / "evaluation_metrics.json"
    assert metrics_path.is_file()
    payload = json.loads(metrics_path.read_text(encoding="utf-8"))
    assert payload["n_evaluated"] == 1
    assert "accuracy" in payload
    assert "f1_macro" in payload
    assert "confusion_matrix" in payload
    assert payload["human_in_the_loop_true"] == 0
    assert payload["human_in_the_loop_false"] == 1
    assert payload["confusion_matrix_labeled"]["DENY"]["DENY"] == 1
    assert "labels" in payload
    assert "explanation" not in payload
    assert "explanations" not in payload
    matrix_path = results_dir / "confusion_matrix.json"
    assert matrix_path.is_file()
    matrix_payload = json.loads(matrix_path.read_text(encoding="utf-8"))
    assert matrix_payload["rows"] == "true_label"
    assert matrix_payload["cols"] == "predicted_label"
    assert matrix_payload["labeled"]["DENY"]["DENY"] == 1
    assert matrix_payload["matrix"] == payload["confusion_matrix"]
    viz_path = results_dir / "evaluation_visualization.png"
    assert viz_path.is_file()
    assert viz_path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    stats_path = results_dir / "analysis_stats.json"
    assert stats_path.is_file()
    stats = json.loads(stats_path.read_text(encoding="utf-8"))
    assert stats["n_claims"] == 1
    assert stats["claim_ids"] == ["claim 1"]
    assert stats["decision_counts"]["DENY"] == 1
    analysis_viz = results_dir / "analysis_stats_visualization.png"
    assert analysis_viz.is_file()
    assert analysis_viz.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_cli_exit_zero_on_empty_batch(tmp_path: Path) -> None:
    data_dir = tmp_path / "raw"
    results_dir = tmp_path / "results"
    data_dir.mkdir()
    results_dir.mkdir()
    config_path = _write_minimal_config(tmp_path, data_dir, results_dir)
    exit_code = main(["--config", str(config_path)])
    assert exit_code == 0
    metrics_path = results_dir / "evaluation_metrics.json"
    assert metrics_path.is_file()
    payload = json.loads(metrics_path.read_text(encoding="utf-8"))
    assert payload["n_evaluated"] == 0
    assert payload["accuracy"] == 0.0
    assert payload["f1_macro"] == 0.0
    viz_path = results_dir / "evaluation_visualization.png"
    assert viz_path.is_file()
    assert viz_path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    stats_path = results_dir / "analysis_stats.json"
    assert stats_path.is_file()
    stats = json.loads(stats_path.read_text(encoding="utf-8"))
    assert stats["n_claims"] == 0
    assert stats["claim_ids"] == []
    assert stats["decision_counts"] == {}
    analysis_viz = results_dir / "analysis_stats_visualization.png"
    assert analysis_viz.is_file()
    assert analysis_viz.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
