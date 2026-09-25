from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from compliance.config.settings import (
    AnalysisConfig,
    AppConfig,
    CheckingConfig,
    ClassificationConfig,
    ExtractionConfig,
    PreprocessingConfig,
)

TRIP_CANCELLATION = "Trip cancellation or rescheduling"
PERSONAL_EFFECTS = "Personal Effects"
MISSED_DEPARTURE = "Missed Departure or Missed Connection"
COVERAGE_OTHER = "None"
MEDICAL_EMERGENCY = "Medical emergency"
MEDICAL_CERTIFICATE = "medical certificate"
PROOF_OF_THEFT = "Proof of theft, loss, or damage"
INCIDENT_REPORT = (
    "Incident report or documentation explaining the cause of delay"
)
PROOF_OF_BOOKING = "Proof of booking"


def _claim_pipeline_cls() -> type:
    """Import ClaimPipeline; fail the test intentionally when the module is absent."""
    try:
        from compliance.workflows.claim_pipeline import ClaimPipeline
    except ImportError as exc:
        pytest.fail(f"ClaimPipeline not implemented: {exc}")
    return ClaimPipeline


def _analysis_config() -> AnalysisConfig:
    coverage = ClassificationConfig(
        labels=[
            "Trip cancellation or rescheduling",
            "Personal Effects",
            "Missed Departure or Missed Connection",
        ],
        other_label="None",
        model="test-model",
        prompt="classify coverage",
    )
    cancellation_reason = ClassificationConfig(
        labels=[
            "Jury duty",
            "Medical emergency",
            "Theft or criminal incident",
            "Other specified personal emergencies",
        ],
        other_label="None",
        model="test-model",
        prompt="classify reason",
    )
    cancellation_document = ClassificationConfig(
        labels=["medical certificate", "police report", "jury summon letter"],
        other_label="None",
        model="test-model",
        prompt="classify cancel doc",
    )
    personal_effects_document = ClassificationConfig(
        labels=["Proof of theft, loss, or damage"],
        other_label="None",
        model="test-model",
        prompt="classify pe doc",
    )
    missed_departure_document = ClassificationConfig(
        labels=[
            "Incident report or documentation explaining the cause of delay",
            "Proof of booking",
        ],
        other_label="None",
        model="test-model",
        prompt="classify missed doc",
    )
    return AnalysisConfig(
        coverage=coverage,
        cancellation_reason=cancellation_reason,
        cancellation_document=cancellation_document,
        personal_effects_document=personal_effects_document,
        missed_departure_document=missed_departure_document,
    )


def _config(
    data_dir: Path,
    *,
    preprocessed_dir: Path | str | None = None,
    results_dir: Path | str | None = None,
) -> AppConfig:
    """Build AppConfig with checking + analysis for ClaimPipeline tests.

    :param data_dir: Temporary claim data root used as preprocessing.data_dir.
    :param preprocessed_dir: Optional preprocessed mirror root.
    :param results_dir: Optional analysis/results root.
    :return: Typed AppConfig suitable for unit tests without live Ollama.
    """
    return AppConfig(
        preprocessing=PreprocessingConfig(
            data_dir=str(data_dir),
            document_formats=["webp", "jpg", "jpeg", "png", "pdf"],
            confidence_threshold=0.7,
            preprocessed_dir=str(preprocessed_dir or data_dir / "preprocessed"),
            results_dir=str(results_dir or data_dir / "results"),
        ),
        extraction=ExtractionConfig(model="test-model", prompt="extract fields"),
        classification=ClassificationConfig(
            labels=[
                "Trip cancellation or rescheduling",
                "Personal Effects",
                "Missed Departure or Missed Connection",
            ],
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
    )


def _chat_response(payload: dict[str, Any]) -> SimpleNamespace:
    return SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))


def _cancellation_chat_fn() -> MagicMock:
    """Injected chat_fn: coverage → reason → cancel-doc → checker contradicts."""
    coverage = _chat_response(
        {
            "labels": [TRIP_CANCELLATION],
            "probabilities": {TRIP_CANCELLATION: 0.9, "None": 0.1},
        }
    )
    reason = _chat_response(
        {
            "labels": [MEDICAL_EMERGENCY],
            "probabilities": {MEDICAL_EMERGENCY: 0.85, "None": 0.15},
        }
    )
    document = _chat_response(
        {
            "labels": [MEDICAL_CERTIFICATE],
            "probabilities": {MEDICAL_CERTIFICATE: 0.8, "None": 0.2},
        }
    )
    contradicts = _chat_response({"result": False})
    return MagicMock(side_effect=[coverage, reason, document, contradicts])


def _seed_preprocessed_claim(config: AppConfig, claim_name: str = "claim 1") -> Path:
    """Write description + supporting_document under preprocessed_dir using artifact names.

    :param config: AppConfig providing paths and artifact filenames.
    :param claim_name: Safe claim folder segment.
    :return: Path to the seeded claim directory under preprocessed_dir.
    """
    artifacts = config.preprocessing.artifacts
    claim_dir = Path(config.preprocessing.preprocessed_dir) / claim_name
    claim_dir.mkdir(parents=True, exist_ok=True)
    description = (
        "I had to cancel my flight to Paris because of a medical emergency."
    )
    (claim_dir / artifacts.description).write_text(description, encoding="utf-8")
    # Include description text so Checker containment hits deterministically (no LLM).
    (claim_dir / artifacts.supporting_document).write_text(
        f"# Supporting document\n\n{description}\n\nMedical certificate attached.\n",
        encoding="utf-8",
    )
    (claim_dir / artifacts.supporting_documents).write_text(
        "# Supporting documents\n\n_none_\n",
        encoding="utf-8",
    )
    return claim_dir


def test_analyze_claim_cancellation_path_writes_analysis_result(tmp_path: Path) -> None:
    """R010–R014: cancellation path writes analysis_result.json under results_dir."""
    ClaimPipeline = _claim_pipeline_cls()
    config = _config(tmp_path)
    claim_dir = _seed_preprocessed_claim(config)
    chat_fn = _cancellation_chat_fn()
    pipeline = ClaimPipeline(config, chat_fn=chat_fn)

    result_path = pipeline.analyze_claim(claim_dir)

    expected = (
        Path(config.preprocessing.results_dir)
        / claim_dir.name
        / config.preprocessing.artifacts.analysis_result
    )
    assert result_path == expected
    assert result_path.is_file()
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    assert payload["claim_id"] == claim_dir.name
    assert TRIP_CANCELLATION in payload["coverage_labels"]
    assert MEDICAL_EMERGENCY in payload["reason_labels"]
    assert MEDICAL_CERTIFICATE in payload["document_labels"]
    assert payload["checker_containment"] is True
    assert payload["checker_contradicts"] is False
    assert chat_fn.call_count >= 1


def test_coverage_node(tmp_path: Path) -> None:
    """R011: coverage classifier runs on description.txt via injectable chat_fn."""
    ClaimPipeline = _claim_pipeline_cls()
    config = _config(tmp_path)
    claim_dir = _seed_preprocessed_claim(config)
    chat_fn = _cancellation_chat_fn()
    pipeline = ClaimPipeline(config, chat_fn=chat_fn)

    result_path = pipeline.analyze_claim(claim_dir)
    payload = json.loads(result_path.read_text(encoding="utf-8"))

    allowed = set(config.analysis.coverage.labels) | {config.analysis.coverage.other_label}
    assert set(payload["coverage_labels"]) <= allowed
    assert TRIP_CANCELLATION in payload["coverage_labels"]
    first_call = chat_fn.call_args_list[0]
    user_content = first_call.kwargs["messages"][1]["content"]
    assert "cancel my flight" in user_content


def test_routes_cancellation_to_reason(tmp_path: Path) -> None:
    """R012: trip-cancellation coverage routes to cancellation_reason classifier."""
    ClaimPipeline = _claim_pipeline_cls()
    config = _config(tmp_path)
    claim_dir = _seed_preprocessed_claim(config)
    chat_fn = _cancellation_chat_fn()
    pipeline = ClaimPipeline(config, chat_fn=chat_fn)

    result_path = pipeline.analyze_claim(claim_dir)
    payload = json.loads(result_path.read_text(encoding="utf-8"))

    assert MEDICAL_EMERGENCY in payload["reason_labels"]
    assert chat_fn.call_count >= 2


def test_checker_node(tmp_path: Path) -> None:
    """R014: Checker containment/contradicts run after document classification."""
    ClaimPipeline = _claim_pipeline_cls()
    config = _config(tmp_path)
    claim_dir = _seed_preprocessed_claim(config)
    chat_fn = _cancellation_chat_fn()
    pipeline = ClaimPipeline(config, chat_fn=chat_fn)

    result_path = pipeline.analyze_claim(claim_dir)
    payload = json.loads(result_path.read_text(encoding="utf-8"))

    assert payload["checker_containment"] is True
    assert payload["checker_contradicts"] is False
    # Contradicts mode always hits LLM; last call should be checker JSON.
    last_content = chat_fn.call_args_list[-1].kwargs["messages"][0]["content"]
    assert "contradicts" in last_content


def test_unit_path_uses_injected_chat_fn(tmp_path: Path) -> None:
    """R016: unit path injects MagicMock chat_fn; never calls live Ollama."""
    ClaimPipeline = _claim_pipeline_cls()
    config = _config(tmp_path)
    claim_dir = _seed_preprocessed_claim(config)
    chat_fn = _cancellation_chat_fn()
    pipeline = ClaimPipeline(config, chat_fn=chat_fn)

    pipeline.analyze_claim(claim_dir)

    assert chat_fn.call_count >= 1


def _pe_chat_fn() -> MagicMock:
    """Injected chat_fn: coverage PE → PE document → checker contradicts."""
    coverage = _chat_response(
        {
            "labels": [PERSONAL_EFFECTS],
            "probabilities": {PERSONAL_EFFECTS: 0.9, "None": 0.1},
        }
    )
    document = _chat_response(
        {
            "labels": [PROOF_OF_THEFT],
            "probabilities": {PROOF_OF_THEFT: 0.85, "None": 0.15},
        }
    )
    contradicts = _chat_response({"result": False})
    return MagicMock(side_effect=[coverage, document, contradicts])


def _missed_chat_fn() -> MagicMock:
    """Injected chat_fn: coverage missed → missed document → checker contradicts."""
    coverage = _chat_response(
        {
            "labels": [MISSED_DEPARTURE],
            "probabilities": {MISSED_DEPARTURE: 0.9, "None": 0.1},
        }
    )
    document = _chat_response(
        {
            "labels": [INCIDENT_REPORT, PROOF_OF_BOOKING],
            "probabilities": {
                INCIDENT_REPORT: 0.7,
                PROOF_OF_BOOKING: 0.6,
                "None": 0.1,
            },
        }
    )
    contradicts = _chat_response({"result": False})
    return MagicMock(side_effect=[coverage, document, contradicts])


def test_routes_personal_effects(tmp_path: Path) -> None:
    """R013: Personal Effects coverage routes to personal_effects_document."""
    ClaimPipeline = _claim_pipeline_cls()
    config = _config(tmp_path)
    claim_dir = _seed_preprocessed_claim(config, claim_name="claim pe")
    chat_fn = _pe_chat_fn()
    pipeline = ClaimPipeline(config, chat_fn=chat_fn)

    result_path = pipeline.analyze_claim(claim_dir)
    payload = json.loads(result_path.read_text(encoding="utf-8"))

    assert PERSONAL_EFFECTS in payload["coverage_labels"]
    assert PROOF_OF_THEFT in payload["document_labels"]
    pe_allowed = set(config.analysis.personal_effects_document.labels) | {
        config.analysis.personal_effects_document.other_label
    }
    assert set(payload["document_labels"]) <= pe_allowed
    assert not payload.get("reason_labels")
    assert payload["checker_containment"] is True
    assert payload["checker_contradicts"] is False
    assert chat_fn.call_count == 3


def test_routes_missed_departure(tmp_path: Path) -> None:
    """R013: Missed Departure coverage routes to missed_departure_document."""
    ClaimPipeline = _claim_pipeline_cls()
    config = _config(tmp_path)
    claim_dir = _seed_preprocessed_claim(config, claim_name="claim missed")
    chat_fn = _missed_chat_fn()
    pipeline = ClaimPipeline(config, chat_fn=chat_fn)

    result_path = pipeline.analyze_claim(claim_dir)
    payload = json.loads(result_path.read_text(encoding="utf-8"))

    assert MISSED_DEPARTURE in payload["coverage_labels"]
    assert INCIDENT_REPORT in payload["document_labels"]
    assert PROOF_OF_BOOKING in payload["document_labels"]
    missed_allowed = set(config.analysis.missed_departure_document.labels) | {
        config.analysis.missed_departure_document.other_label
    }
    assert set(payload["document_labels"]) <= missed_allowed
    assert not payload.get("reason_labels")
    assert payload["checker_containment"] is True
    assert payload["checker_contradicts"] is False
    assert chat_fn.call_count == 3


def _other_coverage_chat_fn() -> MagicMock:
    """Injected chat_fn: coverage other_label only (no reason/doc/checker)."""
    coverage = _chat_response(
        {
            "labels": [COVERAGE_OTHER],
            "probabilities": {COVERAGE_OTHER: 0.95},
        }
    )
    return MagicMock(side_effect=[coverage])


def test_routes_coverage_other_skips_reason_and_docs(tmp_path: Path) -> None:
    """A7/R012: coverage other_label skips reason, docs, and Checker; still persists."""
    ClaimPipeline = _claim_pipeline_cls()
    config = _config(tmp_path)
    claim_dir = _seed_preprocessed_claim(config, claim_name="claim other")
    chat_fn = _other_coverage_chat_fn()
    pipeline = ClaimPipeline(config, chat_fn=chat_fn)

    result_path = pipeline.analyze_claim(claim_dir)
    payload = json.loads(result_path.read_text(encoding="utf-8"))

    assert COVERAGE_OTHER in payload["coverage_labels"]
    assert payload["coverage_labels"] == [config.analysis.coverage.other_label]
    assert not payload.get("reason_labels")
    assert not payload.get("document_labels")
    assert "checker_containment" not in payload
    assert "checker_contradicts" not in payload
    assert chat_fn.call_count == 1


def test_refuses_unsafe_claim_dir_name(tmp_path: Path) -> None:
    """R010/T-04-01: claim_dir.name with path separators or .. raises before I/O."""
    ClaimPipeline = _claim_pipeline_cls()
    config = _config(tmp_path)
    results_root = Path(config.preprocessing.results_dir)
    results_root.mkdir(parents=True, exist_ok=True)
    before = set(results_root.iterdir())
    chat_fn = MagicMock(name="should_not_be_called")
    pipeline = ClaimPipeline(config, chat_fn=chat_fn)

    class _UnsafeDir:
        name = f"..{os.sep}escape"

        def __truediv__(self, other: object) -> Path:
            raise AssertionError("should not join before validation")

    with pytest.raises(ValueError, match="Unsafe claim directory name"):
        pipeline.analyze_claim(_UnsafeDir())  # type: ignore[arg-type]

    class _DotDot:
        name = ".."

        def __truediv__(self, other: object) -> Path:
            raise AssertionError("should not join before validation")

    with pytest.raises(ValueError, match="Unsafe claim directory name"):
        pipeline.analyze_claim(_DotDot())  # type: ignore[arg-type]

    assert set(results_root.iterdir()) == before
    chat_fn.assert_not_called()


def _repeating_cancellation_chat_fn() -> MagicMock:
    """Chat seam that repeats the cancellation path responses for batch runs."""
    from itertools import cycle

    coverage = _chat_response(
        {
            "labels": [TRIP_CANCELLATION],
            "probabilities": {TRIP_CANCELLATION: 0.9, "None": 0.1},
        }
    )
    reason = _chat_response(
        {
            "labels": [MEDICAL_EMERGENCY],
            "probabilities": {MEDICAL_EMERGENCY: 0.85, "None": 0.15},
        }
    )
    document = _chat_response(
        {
            "labels": [MEDICAL_CERTIFICATE],
            "probabilities": {MEDICAL_CERTIFICATE: 0.8, "None": 0.2},
        }
    )
    contradicts = _chat_response({"result": False})
    return MagicMock(side_effect=cycle([coverage, reason, document, contradicts]))


def test_run_batch_writes_analysis_for_successful_claims(tmp_path: Path) -> None:
    """R010: ClaimPipeline.run analyzes all preprocessed claims and writes results."""
    ClaimPipeline = _claim_pipeline_cls()
    config = _config(tmp_path)
    _seed_preprocessed_claim(config, claim_name="claim 1")
    _seed_preprocessed_claim(config, claim_name="claim 2")
    chat_fn = _repeating_cancellation_chat_fn()
    pipeline = ClaimPipeline(config, chat_fn=chat_fn)

    written = pipeline.run()

    analysis_name = config.preprocessing.artifacts.analysis_result
    results_root = Path(config.preprocessing.results_dir)
    expected = [
        results_root / "claim 1" / analysis_name,
        results_root / "claim 2" / analysis_name,
    ]
    assert sorted(written) == sorted(expected)
    for path in expected:
        assert path.is_file()
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert TRIP_CANCELLATION in payload["coverage_labels"]


def test_run_batch_soft_fails_one_claim(tmp_path: Path) -> None:
    """R010: one failing claim is skipped; siblings still get analysis_result.json."""
    ClaimPipeline = _claim_pipeline_cls()
    config = _config(tmp_path)
    _seed_preprocessed_claim(config, claim_name="claim 1")
    bad_dir = _seed_preprocessed_claim(config, claim_name="claim 2")
    # Remove description so analyze_claim fails inside load_artifacts.
    (bad_dir / config.preprocessing.artifacts.description).unlink()
    chat_fn = _repeating_cancellation_chat_fn()
    pipeline = ClaimPipeline(config, chat_fn=chat_fn)

    written = pipeline.run()

    analysis_name = config.preprocessing.artifacts.analysis_result
    results_root = Path(config.preprocessing.results_dir)
    good_path = results_root / "claim 1" / analysis_name
    bad_path = results_root / "claim 2" / analysis_name
    assert good_path in written
    assert bad_path not in written
    assert good_path.is_file()
    assert not bad_path.exists()

