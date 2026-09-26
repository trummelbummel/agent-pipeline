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
    EvaluationConfig,
    ExtractionConfig,
    OcrRetryConfig,
    PreprocessingConfig,
    RequiredDocumentsConfig,
)

TRIP_CANCELLATION = "1"
PERSONAL_EFFECTS = "2"
MISSED_DEPARTURE = "3"
COVERAGE_OTHER = "False"
COVERAGE_FALSE = "False"
MEDICAL_EMERGENCY = "2"
MEDICAL_CERTIFICATE = "1"
PROOF_OF_THEFT = "1"
INCIDENT_REPORT = "1"
PROOF_OF_BOOKING = "2"


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
            "1",
            "2",
            "3",
            "False",
        ],
        other_label="False",
        model="test-model",
        prompt="classify coverage",
        label_names={
            "1": "Trip cancellation or rescheduling",
            "2": "Personal Effects",
            "3": "Missed Departure or Missed Connection",
            "False": "False",
        },
    )
    cancellation_reason = ClassificationConfig(
        labels=[
            "1",
            "2",
            "3",
            "4",
            "False",
        ],
        other_label="False",
        model="test-model",
        prompt="classify reason",
        label_names={
            "1": "Jury duty",
            "2": "Medical emergency",
            "3": "Theft or criminal incident",
            "4": "Other specified personal emergencies",
            "False": "False",
        },
    )
    cancellation_document = ClassificationConfig(
        labels=["1", "2", "3", "4", "False"],
        other_label="False",
        model="test-model",
        prompt="classify cancel doc",
        label_names={
            "1": "medical certificate",
            "2": "police report",
            "3": "jury summon letter",
            "4": "hospital admission",
            "False": "False",
        },
    )
    personal_effects_document = ClassificationConfig(
        labels=["1", "False"],
        other_label="False",
        model="test-model",
        prompt="classify pe doc",
        label_names={
            "1": "Proof of theft, loss, or damage",
            "False": "False",
        },
    )
    missed_departure_document = ClassificationConfig(
        labels=[
            "1",
            "2",
            "False",
        ],
        other_label="False",
        model="test-model",
        prompt="classify missed doc",
        label_names={
            "1": "Incident report or documentation explaining the cause of delay",
            "2": "Proof of booking",
            "False": "False",
        },
    )
    return AnalysisConfig(
        coverage=coverage,
        cancellation_reason=cancellation_reason,
        cancellation_document=cancellation_document,
        personal_effects_document=personal_effects_document,
        missed_departure_document=missed_departure_document,
        required_documents=RequiredDocumentsConfig(
            cancellation_by_reason={
                "1": ["3"],
                "2": ["1", "4"],
                "3": ["2"],
                "4": ["1", "2", "3", "4"],
            },
            personal_effects=["1"],
            missed_departure=["1", "2"],
            signature_required_codes=["1", "4"],
            identity_required_codes=["1", "4"],
        ),
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
                "1",
                "2",
                "3",
            ],
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
        ),
        ocr_retry=OcrRetryConfig(
            enabled=False,
            model="llava",
            prompt="ocr",
        ),
    )


def _chat_response(payload: dict[str, Any]) -> SimpleNamespace:
    return SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))


def _cancellation_chat_fn() -> MagicMock:
    """Injected chat_fn: coverage → reason → cancel-doc → checker contradicts."""
    coverage = _chat_response(
        {
            "labels": [TRIP_CANCELLATION],
            "probabilities": {TRIP_CANCELLATION: 0.9, "False": 0.1},
        }
    )
    reason = _chat_response(
        {
            "labels": [MEDICAL_EMERGENCY],
            "probabilities": {MEDICAL_EMERGENCY: 0.85, "False": 0.15},
        }
    )
    document = _chat_response(
        {
            "labels": [MEDICAL_CERTIFICATE],
            "probabilities": {MEDICAL_CERTIFICATE: 0.8, "False": 0.2},
        }
    )
    contradicts = _chat_response({"result": False})
    identity = _chat_response({"result": True})
    healthy = _chat_response({"result": False})
    return MagicMock(side_effect=[coverage, reason, document, contradicts, identity, healthy])


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
    (claim_dir / artifacts.document_metadata).write_text(
        json.dumps(
            {
                "documents": [
                    {
                        "source_file": "medical.png",
                        "has_signature": True,
                        "extraction_probability": 0.9,
                        "faulty_extraction": False,
                        "human_in_the_loop": False,
                    }
                ]
            }
        )
        + "\n",
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
    assert "Trip cancellation or rescheduling" in payload["coverage_labels"]
    assert "Medical emergency" in payload["reason_labels"]
    assert "medical certificate" in payload["document_labels"]
    assert TRIP_CANCELLATION in payload["coverage_label_codes"]
    assert MEDICAL_EMERGENCY in payload["reason_label_codes"]
    assert MEDICAL_CERTIFICATE in payload["document_label_codes"]
    assert payload["checker_containment"] is True
    assert payload["checker_contradicts"] is False
    assert payload["checker_missing_documentation"] is False
    assert payload["identity_check"] is True
    assert payload["document_has_signature"] is True
    assert payload["signature_check"] is True
    assert payload["decision"] == "APPROVE"
    assert payload["decision_explanation"] == "checker_consistent"
    predicted_path = (
        Path(config.preprocessing.results_dir)
        / claim_dir.name
        / config.preprocessing.artifacts.predicted_answer
    )
    assert predicted_path.is_file()
    predicted = json.loads(predicted_path.read_text(encoding="utf-8"))
    assert predicted["decision"] == "APPROVE"
    assert predicted["source"] == "analysis"
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
    assert set(payload["coverage_label_codes"]) <= allowed
    assert TRIP_CANCELLATION in payload["coverage_label_codes"]
    assert "Trip cancellation or rescheduling" in payload["coverage_labels"]
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

    assert MEDICAL_EMERGENCY in payload["reason_label_codes"]
    assert "Medical emergency" in payload["reason_labels"]
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
    assert payload["identity_check"] is True
    # Healthy mode is the last checker LLM call.
    last_content = chat_fn.call_args_list[-1].kwargs["messages"][0]["content"]
    assert "healthy" in last_content


def test_deny_when_identity_check_false(tmp_path: Path) -> None:
    """identity mismatch (booking name vs obscured doc name) → DENY."""
    ClaimPipeline = _claim_pipeline_cls()
    config = _config(tmp_path)
    claim_dir = _seed_preprocessed_claim(config, claim_name="claim identity")
    artifacts = config.preprocessing.artifacts
    (claim_dir / artifacts.supporting_documents).write_text(
        "# Supporting documents\n\n## Internal: 1\n**name**: Roy Hoffman\n",
        encoding="utf-8",
    )
    (claim_dir / artifacts.supporting_document).write_text(
        "# Supporting document\n\nPatient: R\n*19.12.1945\n",
        encoding="utf-8",
    )
    coverage = _chat_response(
        {
            "labels": [TRIP_CANCELLATION],
            "probabilities": {TRIP_CANCELLATION: 0.9, "False": 0.1},
        }
    )
    reason = _chat_response(
        {
            "labels": [MEDICAL_EMERGENCY],
            "probabilities": {MEDICAL_EMERGENCY: 0.85, "False": 0.15},
        }
    )
    document = _chat_response(
        {
            "labels": [MEDICAL_CERTIFICATE],
            "probabilities": {MEDICAL_CERTIFICATE: 0.8, "False": 0.2},
        }
    )
    contradicts = _chat_response({"result": False})
    identity = _chat_response({"result": "mismatch"})
    healthy = _chat_response({"result": False})
    # Description is not embedded in supporting_document → containment also hits LLM.
    containment = _chat_response({"result": False})
    chat_fn = MagicMock(
        side_effect=[
            coverage,
            reason,
            document,
            containment,
            contradicts,
            identity,
            healthy,
        ]
    )
    pipeline = ClaimPipeline(config, chat_fn=chat_fn)

    result_path = pipeline.analyze_claim(claim_dir)
    payload = json.loads(result_path.read_text(encoding="utf-8"))

    assert payload["identity_check"] is False
    assert payload["identity_unclear"] is False
    assert payload["decision"] == "DENY"
    assert "identity_check" in payload["decision_explanation"]
    identity_user = chat_fn.call_args_list[-2].kwargs["messages"][1]["content"]
    assert "Roy Hoffman" in identity_user
    assert "Patient: R" in identity_user
    assert "Booking / internal" in identity_user
    predicted = json.loads(
        (
            Path(config.preprocessing.results_dir)
            / claim_dir.name
            / config.preprocessing.artifacts.predicted_answer
        ).read_text(encoding="utf-8")
    )
    assert predicted["decision"] == "DENY"
    assert "identity_check" in predicted["explanation"]


def test_uncertain_when_identity_unclear(tmp_path: Path) -> None:
    """No clear patient name field on medical OCR → UNCERTAIN, not DENY."""
    ClaimPipeline = _claim_pipeline_cls()
    config = _config(tmp_path)
    claim_dir = _seed_preprocessed_claim(config, claim_name="claim identity unclear")
    artifacts = config.preprocessing.artifacts
    (claim_dir / artifacts.supporting_documents).write_text(
        "# Supporting documents\n\n## Internal: 1\n**name**: Olivier Bayante\n",
        encoding="utf-8",
    )
    (claim_dir / artifacts.supporting_document).write_text(
        "# Supporting document\n\nDr. Rossi\nAmbulatorio\n",
        encoding="utf-8",
    )
    coverage = _chat_response(
        {
            "labels": [TRIP_CANCELLATION],
            "probabilities": {TRIP_CANCELLATION: 0.9, "False": 0.1},
        }
    )
    reason = _chat_response(
        {
            "labels": [MEDICAL_EMERGENCY],
            "probabilities": {MEDICAL_EMERGENCY: 0.85, "False": 0.15},
        }
    )
    document = _chat_response(
        {
            "labels": [MEDICAL_CERTIFICATE],
            "probabilities": {MEDICAL_CERTIFICATE: 0.8, "False": 0.2},
        }
    )
    containment = _chat_response({"result": False})
    contradicts = _chat_response({"result": False})
    identity = _chat_response({"result": "unclear"})
    healthy = _chat_response({"result": False})
    chat_fn = MagicMock(
        side_effect=[
            coverage,
            reason,
            document,
            containment,
            contradicts,
            identity,
            healthy,
        ]
    )
    pipeline = ClaimPipeline(config, chat_fn=chat_fn)

    result_path = pipeline.analyze_claim(claim_dir)
    payload = json.loads(result_path.read_text(encoding="utf-8"))

    assert payload["identity_check"] is False
    assert payload["identity_unclear"] is True
    assert payload["decision"] == "UNCERTAIN"
    assert payload["decision_explanation"] == "identity_unclear"


def test_identity_skipped_for_non_medical_document(tmp_path: Path) -> None:
    """Personal-effects docs do not run identity LLM; identity_check passes."""
    ClaimPipeline = _claim_pipeline_cls()
    config = _config(tmp_path)
    claim_dir = _seed_preprocessed_claim(config, claim_name="claim pe identity skip")
    artifacts = config.preprocessing.artifacts
    (claim_dir / artifacts.description).write_text(
        "My suitcase was stolen from the hotel lobby.", encoding="utf-8"
    )
    (claim_dir / artifacts.supporting_document).write_text(
        "My suitcase was stolen from the hotel lobby.\nPolice report filed.",
        encoding="utf-8",
    )
    chat_fn = _pe_chat_fn()
    pipeline = ClaimPipeline(config, chat_fn=chat_fn)

    result_path = pipeline.analyze_claim(claim_dir)
    payload = json.loads(result_path.read_text(encoding="utf-8"))

    assert payload["identity_check"] is True
    assert payload["identity_unclear"] is False
    # coverage + document + contradicts + healthy (no identity call)
    assert chat_fn.call_count == 4
    system_prompts = [
        call.kwargs["messages"][0]["content"] for call in chat_fn.call_args_list
    ]
    assert not any("identity" in prompt for prompt in system_prompts)


HOSPITAL_ADMISSION = "4"


def test_deny_when_signature_check_false_for_medical_certificate(
    tmp_path: Path,
) -> None:
    """Medical certificate / hospital admission without has_signature → DENY."""
    ClaimPipeline = _claim_pipeline_cls()
    config = _config(tmp_path)
    claim_dir = _seed_preprocessed_claim(config, claim_name="claim no sig")
    artifacts = config.preprocessing.artifacts
    (claim_dir / artifacts.document_metadata).write_text(
        json.dumps(
            {
                "documents": [
                    {
                        "source_file": "hospital admission document.png",
                        "has_signature": False,
                    }
                ]
            }
        )
        + "\n",
        encoding="utf-8",
    )
    coverage = _chat_response(
        {
            "labels": [TRIP_CANCELLATION],
            "probabilities": {TRIP_CANCELLATION: 0.9, "False": 0.1},
        }
    )
    reason = _chat_response(
        {
            "labels": [MEDICAL_EMERGENCY],
            "probabilities": {MEDICAL_EMERGENCY: 0.85, "False": 0.15},
        }
    )
    document = _chat_response(
        {
            "labels": [HOSPITAL_ADMISSION],
            "probabilities": {HOSPITAL_ADMISSION: 0.8, "False": 0.2},
        }
    )
    contradicts = _chat_response({"result": False})
    identity = _chat_response({"result": True})
    healthy = _chat_response({"result": False})
    chat_fn = MagicMock(
        side_effect=[coverage, reason, document, contradicts, identity, healthy]
    )
    pipeline = ClaimPipeline(config, chat_fn=chat_fn)

    result_path = pipeline.analyze_claim(claim_dir)
    payload = json.loads(result_path.read_text(encoding="utf-8"))

    assert payload["document_has_signature"] is False
    assert payload["signature_check"] is False
    assert payload["document_labels"] == ["hospital admission"]
    assert payload["decision"] == "DENY"
    assert "signature_check" in payload["decision_explanation"]


def test_deny_when_healthy_check_true(tmp_path: Path) -> None:
    """supporting_document asserts patient healthy → DENY."""
    ClaimPipeline = _claim_pipeline_cls()
    config = _config(tmp_path)
    claim_dir = _seed_preprocessed_claim(config, claim_name="claim healthy")
    artifacts = config.preprocessing.artifacts
    (claim_dir / artifacts.supporting_document).write_text(
        "# Supporting document\n\n"
        "## CERTIFICADO MÉDICO\n"
        "En el momento se encuentra CLÍNICAMENTE SANA\n"
        "APTO PARA REALIZAR ACTIVIDAD FÍSICA: SI\n",
        encoding="utf-8",
    )
    coverage = _chat_response(
        {
            "labels": [TRIP_CANCELLATION],
            "probabilities": {TRIP_CANCELLATION: 0.9, "False": 0.1},
        }
    )
    reason = _chat_response(
        {
            "labels": [MEDICAL_EMERGENCY],
            "probabilities": {MEDICAL_EMERGENCY: 0.85, "False": 0.15},
        }
    )
    document = _chat_response(
        {
            "labels": [MEDICAL_CERTIFICATE],
            "probabilities": {MEDICAL_CERTIFICATE: 0.8, "False": 0.2},
        }
    )
    # Description not in supporting doc → containment LLM
    containment = _chat_response({"result": False})
    contradicts = _chat_response({"result": False})
    identity = _chat_response({"result": True})
    healthy = _chat_response({"result": True})
    chat_fn = MagicMock(
        side_effect=[
            coverage,
            reason,
            document,
            containment,
            contradicts,
            identity,
            healthy,
        ]
    )
    pipeline = ClaimPipeline(config, chat_fn=chat_fn)

    result_path = pipeline.analyze_claim(claim_dir)
    payload = json.loads(result_path.read_text(encoding="utf-8"))

    assert payload["healthy_check"] is True
    assert payload["decision"] == "DENY"
    assert "healthy_check" in payload["decision_explanation"]
    healthy_user = chat_fn.call_args_list[-1].kwargs["messages"][1]["content"]
    assert "CLÍNICAMENTE SANA" in healthy_user
    assert "Supporting document" in healthy_user


def _contradicts_deny_chat_fn() -> MagicMock:
    """Injected chat_fn: cancellation path with checker_contradicts True."""
    coverage = _chat_response(
        {
            "labels": [TRIP_CANCELLATION],
            "probabilities": {TRIP_CANCELLATION: 0.9, "False": 0.1},
        }
    )
    reason = _chat_response(
        {
            "labels": [MEDICAL_EMERGENCY],
            "probabilities": {MEDICAL_EMERGENCY: 0.85, "False": 0.15},
        }
    )
    document = _chat_response(
        {
            "labels": [MEDICAL_CERTIFICATE],
            "probabilities": {MEDICAL_CERTIFICATE: 0.8, "False": 0.2},
        }
    )
    contradicts = _chat_response({"result": True})
    identity = _chat_response({"result": True})
    healthy = _chat_response({"result": False})
    return MagicMock(side_effect=[coverage, reason, document, contradicts, identity, healthy])


def test_deny_explanation_names_violated_checker(tmp_path: Path) -> None:
    """DENY decision_explanation lists the violated checker field name."""
    ClaimPipeline = _claim_pipeline_cls()
    config = _config(tmp_path)
    claim_dir = _seed_preprocessed_claim(config, claim_name="claim deny")
    chat_fn = _contradicts_deny_chat_fn()
    pipeline = ClaimPipeline(config, chat_fn=chat_fn)

    result_path = pipeline.analyze_claim(claim_dir)
    payload = json.loads(result_path.read_text(encoding="utf-8"))

    assert payload["checker_contradicts"] is True
    assert payload["checker_missing_documentation"] is False
    assert payload["decision"] == "DENY"
    assert "checker_contradicts" in payload["decision_explanation"]
    predicted = json.loads(
        (
            Path(config.preprocessing.results_dir)
            / claim_dir.name
            / config.preprocessing.artifacts.predicted_answer
        ).read_text(encoding="utf-8")
    )
    assert predicted["decision"] == "DENY"
    assert "checker_contradicts" in predicted["explanation"]


def _wrong_document_type_chat_fn() -> MagicMock:
    """Medical-emergency reason but police-report document (not acceptable)."""
    coverage = _chat_response(
        {
            "labels": [TRIP_CANCELLATION],
            "probabilities": {TRIP_CANCELLATION: 0.9, "False": 0.1},
        }
    )
    reason = _chat_response(
        {
            "labels": [MEDICAL_EMERGENCY],
            "probabilities": {MEDICAL_EMERGENCY: 0.85, "False": 0.15},
        }
    )
    document = _chat_response(
        {
            "labels": ["2"],
            "probabilities": {"2": 0.8, "False": 0.2},
        }
    )
    contradicts = _chat_response({"result": False})
    healthy = _chat_response({"result": False})
    # Police report → identity skipped.
    return MagicMock(side_effect=[coverage, reason, document, contradicts, healthy])


def test_missing_documentation_when_document_type_not_acceptable(
    tmp_path: Path,
) -> None:
    """Missing documentation when classified doc type is outside required set."""
    ClaimPipeline = _claim_pipeline_cls()
    config = _config(tmp_path)
    claim_dir = _seed_preprocessed_claim(config, claim_name="claim wrong doc")
    chat_fn = _wrong_document_type_chat_fn()
    pipeline = ClaimPipeline(config, chat_fn=chat_fn)

    result_path = pipeline.analyze_claim(claim_dir)
    payload = json.loads(result_path.read_text(encoding="utf-8"))

    assert payload["checker_missing_documentation"] is True
    assert payload["decision"] == "DENY"
    assert "checker_missing_documentation" in payload["decision_explanation"]
    # Failed containment must not be the missing-doc signal.
    assert "checker_containment" not in payload["decision_explanation"]


def _none_document_chat_fn() -> MagicMock:
    """Medical path with document classifier other_label only."""
    coverage = _chat_response(
        {
            "labels": [TRIP_CANCELLATION],
            "probabilities": {TRIP_CANCELLATION: 0.9, "False": 0.1},
        }
    )
    reason = _chat_response(
        {
            "labels": [MEDICAL_EMERGENCY],
            "probabilities": {MEDICAL_EMERGENCY: 0.85, "False": 0.15},
        }
    )
    document = _chat_response(
        {
            "labels": [COVERAGE_OTHER],
            "probabilities": {COVERAGE_OTHER: 0.9},
        }
    )
    contradicts = _chat_response({"result": False})
    healthy = _chat_response({"result": False})
    # Document None → identity skipped (not medical/hospital codes).
    return MagicMock(side_effect=[coverage, reason, document, contradicts, healthy])


def test_missing_documentation_when_document_is_none(tmp_path: Path) -> None:
    """Document other_label (False) counts as missing acceptable documentation."""
    ClaimPipeline = _claim_pipeline_cls()
    config = _config(tmp_path)
    claim_dir = _seed_preprocessed_claim(config, claim_name="claim no doc type")
    chat_fn = _none_document_chat_fn()
    pipeline = ClaimPipeline(config, chat_fn=chat_fn)

    result_path = pipeline.analyze_claim(claim_dir)
    payload = json.loads(result_path.read_text(encoding="utf-8"))

    assert payload["checker_missing_documentation"] is True
    assert payload["decision"] == "DENY"
    assert payload["decision_explanation"] == "checker_missing_documentation"


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
            "probabilities": {PERSONAL_EFFECTS: 0.9, "False": 0.1},
        }
    )
    document = _chat_response(
        {
            "labels": [PROOF_OF_THEFT],
            "probabilities": {PROOF_OF_THEFT: 0.85, "False": 0.15},
        }
    )
    contradicts = _chat_response({"result": False})
    healthy = _chat_response({"result": False})
    return MagicMock(side_effect=[coverage, document, contradicts, healthy])


def _missed_chat_fn() -> MagicMock:
    """Injected chat_fn: coverage missed → missed document → checker (no identity)."""
    coverage = _chat_response(
        {
            "labels": [MISSED_DEPARTURE],
            "probabilities": {MISSED_DEPARTURE: 0.9, "False": 0.1},
        }
    )
    document = _chat_response(
        {
            "labels": [INCIDENT_REPORT, PROOF_OF_BOOKING],
            "probabilities": {
                INCIDENT_REPORT: 0.7,
                PROOF_OF_BOOKING: 0.6,
                "False": 0.1,
            },
        }
    )
    contradicts = _chat_response({"result": False})
    healthy = _chat_response({"result": False})
    return MagicMock(side_effect=[coverage, document, contradicts, healthy])


def test_routes_personal_effects(tmp_path: Path) -> None:
    """R013: Personal Effects coverage routes to personal_effects_document."""
    ClaimPipeline = _claim_pipeline_cls()
    config = _config(tmp_path)
    claim_dir = _seed_preprocessed_claim(config, claim_name="claim pe")
    chat_fn = _pe_chat_fn()
    pipeline = ClaimPipeline(config, chat_fn=chat_fn)

    result_path = pipeline.analyze_claim(claim_dir)
    payload = json.loads(result_path.read_text(encoding="utf-8"))

    assert PERSONAL_EFFECTS in payload["coverage_label_codes"]
    assert "Personal Effects" in payload["coverage_labels"]
    assert PROOF_OF_THEFT in payload["document_label_codes"]
    assert "Proof of theft, loss, or damage" in payload["document_labels"]
    pe_allowed = set(config.analysis.personal_effects_document.labels) | {
        config.analysis.personal_effects_document.other_label
    }
    assert set(payload["document_label_codes"]) <= pe_allowed
    assert not payload.get("reason_labels")
    assert not payload.get("reason_label_codes")
    assert payload["checker_containment"] is True
    assert payload["checker_contradicts"] is False
    assert payload["identity_check"] is True
    assert payload["identity_unclear"] is False
    assert chat_fn.call_count == 4


def test_routes_missed_departure(tmp_path: Path) -> None:
    """R013: Missed Departure coverage routes to missed_departure_document."""
    ClaimPipeline = _claim_pipeline_cls()
    config = _config(tmp_path)
    claim_dir = _seed_preprocessed_claim(config, claim_name="claim missed")
    chat_fn = _missed_chat_fn()
    pipeline = ClaimPipeline(config, chat_fn=chat_fn)

    result_path = pipeline.analyze_claim(claim_dir)
    payload = json.loads(result_path.read_text(encoding="utf-8"))

    assert MISSED_DEPARTURE in payload["coverage_label_codes"]
    assert "Missed Departure or Missed Connection" in payload["coverage_labels"]
    assert INCIDENT_REPORT in payload["document_label_codes"]
    assert PROOF_OF_BOOKING in payload["document_label_codes"]
    assert (
        "Incident report or documentation explaining the cause of delay"
        in payload["document_labels"]
    )
    assert "Proof of booking" in payload["document_labels"]
    missed_allowed = set(config.analysis.missed_departure_document.labels) | {
        config.analysis.missed_departure_document.other_label
    }
    assert set(payload["document_label_codes"]) <= missed_allowed
    assert not payload.get("reason_labels")
    assert not payload.get("reason_label_codes")
    assert payload["checker_containment"] is True
    assert payload["checker_contradicts"] is False
    assert payload["identity_check"] is True
    assert payload["identity_unclear"] is False
    assert chat_fn.call_count == 4


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
    """A7/R012: coverage False abstention skips reason/docs/Checker; HITL on prediction."""
    ClaimPipeline = _claim_pipeline_cls()
    config = _config(tmp_path)
    claim_dir = _seed_preprocessed_claim(config, claim_name="claim other")
    chat_fn = _other_coverage_chat_fn()
    pipeline = ClaimPipeline(config, chat_fn=chat_fn)

    result_path = pipeline.analyze_claim(claim_dir)
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    predicted = json.loads(
        (
            Path(config.preprocessing.results_dir)
            / "claim other"
            / config.preprocessing.artifacts.predicted_answer
        ).read_text(encoding="utf-8")
    )

    assert COVERAGE_OTHER in payload["coverage_labels"]
    assert payload["coverage_labels"] == [config.analysis.coverage.other_label]
    assert not payload.get("reason_labels")
    assert not payload.get("document_labels")
    assert "checker_containment" not in payload
    assert "checker_contradicts" not in payload
    assert payload["human_in_the_loop"] is True
    assert predicted["human_in_the_loop"] is True
    assert predicted["decision"] == "UNCERTAIN"
    assert chat_fn.call_count == 1


def test_classifier_false_sets_human_in_the_loop(tmp_path: Path) -> None:
    """Coverage False flags human_in_the_loop on analysis_result, metadata, and prediction."""
    ClaimPipeline = _claim_pipeline_cls()
    config = _config(tmp_path)
    claim_dir = _seed_preprocessed_claim(config, claim_name="claim false")
    artifacts = config.preprocessing.artifacts
    coverage = _chat_response(
        {
            "labels": [COVERAGE_FALSE],
            "probabilities": {COVERAGE_FALSE: 0.9},
        }
    )
    chat_fn = MagicMock(side_effect=[coverage])
    pipeline = ClaimPipeline(config, chat_fn=chat_fn)

    result_path = pipeline.analyze_claim(claim_dir)
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    predicted = json.loads(
        (
            Path(config.preprocessing.results_dir)
            / "claim false"
            / artifacts.predicted_answer
        ).read_text(encoding="utf-8")
    )

    assert payload["coverage_label_codes"] == [COVERAGE_FALSE]
    assert payload["human_in_the_loop"] is True
    assert payload["decision"] == "UNCERTAIN"
    assert predicted["human_in_the_loop"] is True
    meta = json.loads((claim_dir / artifacts.document_metadata).read_text(encoding="utf-8"))
    assert meta["documents"][0]["human_in_the_loop"] is True
    assert chat_fn.call_count == 1


def test_document_classifier_false_sets_human_in_the_loop(tmp_path: Path) -> None:
    """Document-stage False also raises human_in_the_loop for review."""
    ClaimPipeline = _claim_pipeline_cls()
    config = _config(tmp_path)
    claim_dir = _seed_preprocessed_claim(config, claim_name="claim doc false")
    artifacts = config.preprocessing.artifacts
    coverage = _chat_response(
        {
            "labels": [TRIP_CANCELLATION],
            "probabilities": {TRIP_CANCELLATION: 0.9, "False": 0.1},
        }
    )
    reason = _chat_response(
        {
            "labels": [MEDICAL_EMERGENCY],
            "probabilities": {MEDICAL_EMERGENCY: 0.85, "False": 0.15},
        }
    )
    document = _chat_response(
        {
            "labels": [COVERAGE_FALSE],
            "probabilities": {COVERAGE_FALSE: 0.8, "False": 0.2},
        }
    )
    containment = _chat_response({"result": False})
    contradicts = _chat_response({"result": False})
    healthy = _chat_response({"result": False})
    chat_fn = MagicMock(
        side_effect=[coverage, reason, document, containment, contradicts, healthy]
    )
    pipeline = ClaimPipeline(config, chat_fn=chat_fn)

    result_path = pipeline.analyze_claim(claim_dir)
    payload = json.loads(result_path.read_text(encoding="utf-8"))

    assert COVERAGE_FALSE in payload["document_label_codes"]
    assert payload["human_in_the_loop"] is True
    meta = json.loads((claim_dir / artifacts.document_metadata).read_text(encoding="utf-8"))
    assert meta["documents"][0]["human_in_the_loop"] is True


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
            "probabilities": {TRIP_CANCELLATION: 0.9, "False": 0.1},
        }
    )
    reason = _chat_response(
        {
            "labels": [MEDICAL_EMERGENCY],
            "probabilities": {MEDICAL_EMERGENCY: 0.85, "False": 0.15},
        }
    )
    document = _chat_response(
        {
            "labels": [MEDICAL_CERTIFICATE],
            "probabilities": {MEDICAL_CERTIFICATE: 0.8, "False": 0.2},
        }
    )
    contradicts = _chat_response({"result": False})
    identity = _chat_response({"result": True})
    healthy = _chat_response({"result": False})
    return MagicMock(side_effect=cycle([coverage, reason, document, contradicts, identity, healthy]))


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
        assert "Trip cancellation or rescheduling" in payload["coverage_labels"]
        assert TRIP_CANCELLATION in payload["coverage_label_codes"]


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


def _minimal_cli_config_yaml(tmp_path: Path) -> Path:
    """Write a load_config-valid YAML pointing at tmp dirs (includes analysis)."""
    data_dir = tmp_path / "data"
    data_dir.mkdir(exist_ok=True)
    preprocessed = tmp_path / "preprocessed"
    results = tmp_path / "results"
    cfg_path = tmp_path / "config.yaml"
    stage = "\n".join(
        [
            "    labels: [\"1\"]",
            "    other_label: \"False\"",
            "    model: test-model",
            "    prompt: classify",
        ]
    )
    cfg_path.write_text(
        "\n".join(
            [
                "preprocessing:",
                f"  data_dir: {data_dir}",
                "  document_formats: [webp, jpg, jpeg, png, pdf]",
                "  confidence_threshold: 0.7",
                f"  preprocessed_dir: {preprocessed}",
                f"  results_dir: {results}",
                "extraction:",
                "  model: test-model",
                "  prompt: extract",
                "classification:",
                "  labels: [\"1\"]",
                "  other_label: \"False\"",
                "  model: test-model",
                "  prompt: classify",
                "checking:",
                "  model: test-model",
                "  containment_prompt: containment",
                "  contradicts_prompt: contradicts",
                "  identity_prompt: identity",
                "  healthy_prompt: healthy",
                "analysis:",
                "  coverage:",
                stage,
                "  cancellation_reason:",
                stage,
                "  cancellation_document:",
                stage,
                "  personal_effects_document:",
                stage,
                "  missed_departure_document:",
                stage,
                "evaluation:",
                "  labels: [APPROVE, DENY, UNCERTAIN]",
                "  metrics_artifact: evaluation_metrics.json",
                "ocr_retry:",
                "  enabled: false",
                "  model: test-vision",
                "  prompt: ocr",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return cfg_path


def test_main_analyze_mode_invokes_claim_pipeline_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R010/R016: --mode analyze loads config and calls ClaimPipeline.run once."""
    from compliance.workflows.claim_pipeline import ClaimPipeline
    from main import main

    cfg_path = _minimal_cli_config_yaml(tmp_path)
    calls: list[object] = []

    def _fake_run(self: ClaimPipeline, source: Path | None = None) -> list[Path]:
        calls.append(self)
        return []

    monkeypatch.setattr(ClaimPipeline, "run", _fake_run)

    assert main(["--mode", "analyze", "--config", str(cfg_path)]) == 0
    assert len(calls) == 1


def test_main_both_mode_runs_preprocess_then_analyze(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """--mode both runs PreprocessingPipeline then ClaimPipeline."""
    from compliance.workflows.claim_pipeline import ClaimPipeline
    from compliance.workflows.pipeline import PreprocessingPipeline
    from main import main

    cfg_path = _minimal_cli_config_yaml(tmp_path)
    calls: list[str] = []

    def _fake_preprocess(
        self: PreprocessingPipeline, source: Path | None = None
    ) -> list[Path]:
        calls.append("preprocess")
        return []

    def _fake_analyze(self: ClaimPipeline, source: Path | None = None) -> list[Path]:
        calls.append("analyze")
        return []

    monkeypatch.setattr(PreprocessingPipeline, "run", _fake_preprocess)
    monkeypatch.setattr(ClaimPipeline, "run", _fake_analyze)

    assert main(["--mode", "both", "--config", str(cfg_path)]) == 0
    assert calls == ["preprocess", "analyze"]


def test_main_default_still_preprocess(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R016: default argv still runs PreprocessingPipeline (preprocess unbroken)."""
    from compliance.workflows.pipeline import PreprocessingPipeline
    from main import main

    cfg_path = _minimal_cli_config_yaml(tmp_path)
    calls: list[str] = []

    def _fake_preprocess(
        self: PreprocessingPipeline, source: Path | None = None
    ) -> list[Path]:
        calls.append("preprocess")
        return []

    monkeypatch.setattr(PreprocessingPipeline, "run", _fake_preprocess)

    assert main(["--config", str(cfg_path)]) == 0
    assert calls == ["preprocess"]


def test_run_with_claim_folder_processes_one(tmp_path: Path) -> None:
    """R020: ClaimPipeline.run(claim_folder) analyzes that folder only."""
    ClaimPipeline = _claim_pipeline_cls()
    config = _config(tmp_path)
    claim1 = _seed_preprocessed_claim(config, claim_name="claim 1")
    _seed_preprocessed_claim(config, claim_name="claim 2")
    chat_fn = _repeating_cancellation_chat_fn()
    pipeline = ClaimPipeline(config, chat_fn=chat_fn)

    written = pipeline.run(claim1)

    analysis_name = config.preprocessing.artifacts.analysis_result
    results_root = Path(config.preprocessing.results_dir)
    assert written == [results_root / "claim 1" / analysis_name]
    assert (results_root / "claim 1" / analysis_name).is_file()
    assert not (results_root / "claim 2" / analysis_name).exists()


def test_run_with_directory_batches(tmp_path: Path) -> None:
    """R020: ClaimPipeline.run(parent_dir) soft-fail batches under that Path."""
    ClaimPipeline = _claim_pipeline_cls()
    # Config preprocessed_dir is unused — caller Path drives discovery.
    unused_root = tmp_path / "unused_preprocessed"
    unused_root.mkdir()
    parent = tmp_path / "external_preprocessed"
    config = _config(
        tmp_path / "data",
        preprocessed_dir=unused_root,
        results_dir=tmp_path / "results",
    )
    artifacts = config.preprocessing.artifacts
    for name in ("claim 1", "claim 2"):
        claim_dir = parent / name
        claim_dir.mkdir(parents=True)
        (claim_dir / artifacts.description).write_text(
            "I had to cancel my flight to Paris because of a medical emergency.",
            encoding="utf-8",
        )
        (claim_dir / artifacts.supporting_document).write_text(
            "# Supporting document\n\nMedical certificate.\n",
            encoding="utf-8",
        )
        (claim_dir / artifacts.supporting_documents).write_text(
            "# Supporting documents\n\n_none_\n",
            encoding="utf-8",
        )
    chat_fn = _repeating_cancellation_chat_fn()
    pipeline = ClaimPipeline(config, chat_fn=chat_fn)

    written = pipeline.run(parent)

    analysis_name = artifacts.analysis_result
    results_root = Path(config.preprocessing.results_dir)
    expected = [
        results_root / "claim 1" / analysis_name,
        results_root / "claim 2" / analysis_name,
    ]
    assert sorted(written) == sorted(expected)


def test_run_none_uses_config_roots(tmp_path: Path) -> None:
    """R020: ClaimPipeline.run(None) discovers under config preprocessed_dir."""
    ClaimPipeline = _claim_pipeline_cls()
    config = _config(tmp_path)
    _seed_preprocessed_claim(config, claim_name="claim 1")
    chat_fn = _repeating_cancellation_chat_fn()
    pipeline = ClaimPipeline(config, chat_fn=chat_fn)

    written = pipeline.run(None)

    analysis_name = config.preprocessing.artifacts.analysis_result
    results_root = Path(config.preprocessing.results_dir)
    assert written == [results_root / "claim 1" / analysis_name]

