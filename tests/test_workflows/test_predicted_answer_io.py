from __future__ import annotations

import json
from pathlib import Path

from compliance.models.claim import GroundTruth
from compliance.workflows.predicted_answer_io import (
    SOURCE_ANALYSIS,
    SOURCE_PREPROCESS,
    is_preprocess_origin_prediction,
    remove_stale_preprocess_prediction,
    write_analysis_predicted_answer,
    write_preprocess_predicted_answer,
)


def test_is_preprocess_origin_with_source_preprocess() -> None:
    assert is_preprocess_origin_prediction({"source": SOURCE_PREPROCESS, "decision": "DENY"})


def test_is_preprocess_origin_legacy_fraud_explanation() -> None:
    assert is_preprocess_origin_prediction({
        "decision": "DENY",
        "explanation": "fraud (benford chi_squared=1.0)",
    })


def test_is_not_preprocess_origin_analysis_source() -> None:
    assert not is_preprocess_origin_prediction({
        "source": SOURCE_ANALYSIS,
        "decision": "APPROVE",
        "explanation": "checker_consistent",
    })


def test_is_not_preprocess_origin_unknown_without_fraud_heuristic() -> None:
    assert not is_preprocess_origin_prediction({"decision": "APPROVE", "explanation": "checker_consistent"})


def test_remove_stale_preserves_analysis_source_without_analysis_result(
    tmp_path: Path,
) -> None:
    predicted = tmp_path / "predicted_answer.json"
    analysis_result = tmp_path / "analysis_result.json"
    predicted.write_text(
        json.dumps({
            "decision": "APPROVE",
            "explanation": "checker_consistent",
            "source": SOURCE_ANALYSIS,
        }),
        encoding="utf-8",
    )

    removed = remove_stale_preprocess_prediction(predicted, analysis_result_path=analysis_result)

    assert removed is False
    assert predicted.is_file()


def test_remove_stale_unlinks_legacy_fraud_without_analysis_result(
    tmp_path: Path,
) -> None:
    predicted = tmp_path / "predicted_answer.json"
    analysis_result = tmp_path / "analysis_result.json"
    predicted.write_text(
        json.dumps({
            "decision": "DENY",
            "explanation": "fraud (benford chi_squared=1.0)",
        }),
        encoding="utf-8",
    )

    removed = remove_stale_preprocess_prediction(predicted, analysis_result_path=analysis_result)

    assert removed is True
    assert not predicted.exists()


def test_remove_stale_preserves_when_analysis_result_present(tmp_path: Path) -> None:
    predicted = tmp_path / "predicted_answer.json"
    analysis_result = tmp_path / "analysis_result.json"
    predicted.write_text(
        json.dumps({
            "decision": "DENY",
            "explanation": "fraud (benford chi_squared=1.0)",
            "source": SOURCE_PREPROCESS,
        }),
        encoding="utf-8",
    )
    analysis_result.write_text('{"decision":"APPROVE"}', encoding="utf-8")

    removed = remove_stale_preprocess_prediction(predicted, analysis_result_path=analysis_result)

    assert removed is False
    assert predicted.is_file()


def test_write_preprocess_stamps_source(tmp_path: Path) -> None:
    path = tmp_path / "predicted_answer.json"
    written = write_preprocess_predicted_answer(
        path,
        GroundTruth(decision="DENY", explanation="fraud (benford chi_squared=9.0)"),
    )
    payload = json.loads(written.read_text(encoding="utf-8"))
    assert payload["source"] == SOURCE_PREPROCESS
    assert payload["decision"] == "DENY"


def test_write_analysis_stamps_source(tmp_path: Path) -> None:
    path = tmp_path / "predicted_answer.json"
    written = write_analysis_predicted_answer(
        path,
        GroundTruth(decision="APPROVE", explanation="checker_consistent"),
    )
    payload = json.loads(written.read_text(encoding="utf-8"))
    assert payload["source"] == SOURCE_ANALYSIS
    assert payload["decision"] == "APPROVE"
