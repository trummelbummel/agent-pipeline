from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock

import pytest
from conftest import build_minimal_app_config

from compliance.config.settings import (
    AnalysisConfig,
    AppConfig,
    ClassificationConfig,
    CoverageClassificationConfig,
    OcrRetryConfig,
    RequiredDocumentsConfig,
    TransportRetryConfig,
)

if TYPE_CHECKING:
    from conftest import CancellationChatFactory

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

_PIPELINE_CLASSIFICATION = ClassificationConfig(
    labels=["1", "2", "3"],
    other_label="False",
    model="test-model",
    prompt="classify",
)


def _claim_pipeline_cls() -> type:
    """Import ClaimPipeline; fail the test intentionally when the module is absent."""
    try:
        from compliance.workflows.claim_pipeline import ClaimPipeline
    except ImportError as exc:
        pytest.fail(f"ClaimPipeline not implemented: {exc}")
    return ClaimPipeline


def _analysis_config() -> AnalysisConfig:
    coverage = CoverageClassificationConfig(
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
        branches={
            "1": "cancellation",
            "2": "personal_effects",
            "3": "missed_departure",
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
    return build_minimal_app_config(
        data_dir,
        preprocessed_dir=preprocessed_dir or data_dir / "preprocessed",
        results_dir=results_dir or data_dir / "results",
        analysis=_analysis_config(),
        classification=_PIPELINE_CLASSIFICATION,
        ocr_retry=OcrRetryConfig(
            enabled=False,
            model="llava",
            prompt="ocr",
        ),
    )


def _chat_response(payload: dict[str, Any]) -> SimpleNamespace:
    return SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))


def _cancellation_chat_fn(
    cancellation_chat_factory: CancellationChatFactory,
) -> MagicMock:
    """Injected chat_fn: coverage → reason → cancel-doc → checker (identity skipped)."""
    return cancellation_chat_factory([
        {"result": False},
        {"result": False},
        {"result": False},
        {"result": False},
    ])


def _seed_preprocessed_claim(config: AppConfig, claim_name: str = "claim 1") -> Path:
    """Write description + supporting_document under preprocessed_dir using artifact names.

    :param config: AppConfig providing paths and artifact filenames.
    :param claim_name: Safe claim folder segment.
    :return: Path to the seeded claim directory under preprocessed_dir.
    """
    artifacts = config.preprocessing.artifacts
    claim_dir = Path(config.preprocessing.preprocessed_dir) / claim_name
    claim_dir.mkdir(parents=True, exist_ok=True)
    description = "I had to cancel my flight to Paris because of a medical emergency."
    (claim_dir / artifacts.description).write_text(description, encoding="utf-8")
    # Include description text so Checker containment hits deterministically (no LLM).
    # Matching booking/patient name so identity containment skips the LLM.
    (claim_dir / artifacts.supporting_document).write_text(
        f"# Supporting document\n\n{description}\n\nPatient: Ada Lovelace\nMedical certificate attached.\n",
        encoding="utf-8",
    )
    (claim_dir / artifacts.supporting_documents).write_text(
        "# Supporting documents\n\n**name**: Ada Lovelace\n",
        encoding="utf-8",
    )
    (claim_dir / artifacts.document_metadata).write_text(
        json.dumps({
            "documents": [
                {
                    "source_file": "medical.png",
                    "has_signature": True,
                    "extraction_probability": 0.9,
                    "faulty_extraction": False,
                    "human_in_the_loop": False,
                }
            ]
        })
        + "\n",
        encoding="utf-8",
    )
    return claim_dir


# --- SR-004: single authoritative coverage route (routed_coverage) ---

# Path tail keyed by winning coverage code (DRY): classification payloads then
# checker boolean payloads, consumed after the coverage classification response.
_COVERAGE_WINNER_TAILS: dict[str, list[dict[str, Any]]] = {
    TRIP_CANCELLATION: [
        {"labels": [MEDICAL_EMERGENCY], "probabilities": {MEDICAL_EMERGENCY: 0.85, "False": 0.15}},
        {"labels": [MEDICAL_CERTIFICATE], "probabilities": {MEDICAL_CERTIFICATE: 0.8, "False": 0.2}},
        {"result": False},
        {"result": False},
        {"result": False},
        {"result": False},
    ],
    PERSONAL_EFFECTS: [
        {"labels": [PROOF_OF_THEFT], "probabilities": {PROOF_OF_THEFT: 0.8, "False": 0.2}},
        {"result": False},
        {"result": False},
    ],
    MISSED_DEPARTURE: [
        {"labels": [INCIDENT_REPORT], "probabilities": {INCIDENT_REPORT: 0.8, "False": 0.2}},
        {"result": False},
        {"result": False},
    ],
    COVERAGE_FALSE: [],
}

# Full expectation per winning coverage code, asserted by test_coverage_route_by_probability.
_COVERAGE_WINNER_EXPECTATIONS: dict[str, dict[str, Any]] = {
    TRIP_CANCELLATION: {
        "routed_coverage_label": "Trip cancellation or rescheduling",
        "document_labels": ["medical certificate"],
        "reason_label_codes": [MEDICAL_EMERGENCY],
        "decision": "APPROVE",
        "decision_explanation": "checker_consistent",
        "human_in_the_loop": False,
        "call_count": 7,
        "not_authentic_present": True,
    },
    PERSONAL_EFFECTS: {
        "routed_coverage_label": "Personal Effects",
        "document_labels": ["Proof of theft, loss, or damage"],
        "reason_label_codes": [],
        "decision": "APPROVE",
        "decision_explanation": "checker_consistent",
        "human_in_the_loop": False,
        "call_count": 4,
        "not_authentic_present": False,
    },
    MISSED_DEPARTURE: {
        "routed_coverage_label": "Missed Departure or Missed Connection",
        "document_labels": ["Incident report or documentation explaining the cause of delay"],
        "reason_label_codes": [],
        "decision": "APPROVE",
        "decision_explanation": "checker_consistent",
        "human_in_the_loop": False,
        "call_count": 4,
        "not_authentic_present": False,
    },
    COVERAGE_FALSE: {
        "routed_coverage_label": "False",
        "document_labels": [],
        "reason_label_codes": [],
        "decision": "UNCERTAIN",
        "decision_explanation": "coverage_false_label",
        "human_in_the_loop": True,
        "call_count": 1,
        "not_authentic_present": False,
    },
}


def _coverage_route_chat_fn(labels: list[str], probabilities: dict[str, float], winner: str) -> MagicMock:
    """Injected chat_fn: coverage selection, then the winner's path tail.

    An unexpected extra LLM call beyond the tail raises StopIteration, which is
    the mechanism that enforces exactly one path is followed (SR-004).
    """
    coverage = _chat_response({"labels": labels, "probabilities": probabilities})
    tail = [_chat_response(payload) for payload in _COVERAGE_WINNER_TAILS[winner]]
    return MagicMock(side_effect=[coverage, *tail])


@pytest.mark.parametrize(
    ("labels", "probabilities", "winner"),
    [
        pytest.param(["2", "3"], {"2": 0.4, "3": 0.8}, MISSED_DEPARTURE, id="tracer_23"),
        pytest.param(["3", "2"], {"2": 0.4, "3": 0.8}, MISSED_DEPARTURE, id="tracer_32"),
        pytest.param(["1", "2"], {"1": 0.4, "2": 0.8}, PERSONAL_EFFECTS, id="multi_positive_12_pe_wins"),
        pytest.param(["2", "1"], {"1": 0.4, "2": 0.8}, PERSONAL_EFFECTS, id="multi_positive_21_pe_wins"),
        pytest.param(["1", "2"], {"1": 0.8, "2": 0.4}, TRIP_CANCELLATION, id="multi_positive_12_cancel_wins"),
        pytest.param(["2", "1"], {"1": 0.8, "2": 0.4}, TRIP_CANCELLATION, id="multi_positive_21_cancel_wins"),
        pytest.param(["False", "1"], {"False": 0.7, "1": 0.3}, COVERAGE_FALSE, id="false_first_abstention_wins"),
        pytest.param(["1", "False"], {"False": 0.7, "1": 0.3}, COVERAGE_FALSE, id="false_last_abstention_wins"),
        pytest.param(["False", "1"], {"False": 0.3, "1": 0.7}, TRIP_CANCELLATION, id="false_first_positive_wins"),
        pytest.param(["1", "False"], {"False": 0.3, "1": 0.7}, TRIP_CANCELLATION, id="false_last_positive_wins"),
        pytest.param(["3", "2"], {"2": 0.5, "3": 0.5}, PERSONAL_EFFECTS, id="tie_positive_config_order"),
        pytest.param(["False", "3"], {"False": 0.5, "3": 0.5}, MISSED_DEPARTURE, id="tie_positive_beats_abstention"),
        pytest.param(["1", "3"], {"3": 0.2}, MISSED_DEPARTURE, id="missing_probability_counts_zero"),
        pytest.param(["1", "3"], {"1": 0.6, "3": 0.8}, MISSED_DEPARTURE, id="overlap_missed_wins"),
        pytest.param(["3", "1"], {"1": 0.8, "3": 0.6}, TRIP_CANCELLATION, id="overlap_cancel_wins"),
    ],
)
def test_coverage_route_by_probability(
    tmp_path: Path,
    labels: list[str],
    probabilities: dict[str, float],
    winner: str,
) -> None:
    """SR-004: highest-probability selected coverage label wins (D-01..D-06, P-01..P-03).

    The winning label alone determines branch, document stage, and decision —
    order of ``labels`` never matters (order invariance, D-01), and a losing
    ``False`` cannot skip stages (D-02).
    """
    ClaimPipeline = _claim_pipeline_cls()
    config = _config(tmp_path)
    claim_dir = _seed_preprocessed_claim(config, claim_name=f"claim {'-'.join(labels)}-{winner}")
    chat_fn = _coverage_route_chat_fn(labels, probabilities, winner)
    pipeline = ClaimPipeline(config, chat_fn=chat_fn)

    result_path = pipeline.analyze_claim(claim_dir)
    payload = json.loads(result_path.read_text(encoding="utf-8"))

    expected = _COVERAGE_WINNER_EXPECTATIONS[winner]
    assert payload["routed_coverage_label_code"] == winner
    assert payload["routed_coverage_label"] == expected["routed_coverage_label"]
    assert payload["coverage_label_codes"] == labels
    assert payload["coverage_probabilities"][winner] == probabilities.get(winner, 0.0)
    assert payload.get("document_labels", []) == expected["document_labels"]
    assert payload.get("reason_label_codes", []) == expected["reason_label_codes"]
    assert payload["decision"] == expected["decision"]
    assert payload["decision_explanation"] == expected["decision_explanation"]
    assert payload["human_in_the_loop"] is expected["human_in_the_loop"]
    assert chat_fn.call_count == expected["call_count"]
    assert ("checker_document_not_authentic" in payload) is expected["not_authentic_present"]


def test_coverage_label_order_does_not_remap_branch(tmp_path: Path) -> None:
    """Reversed coverage ``labels`` must not change which branch a code routes to (D-01).

    Probabilities are unambiguous on purpose (P-08): SR-004 tie-break still follows
    ``labels`` order, so this test only proves branch remapping is gone.
    """
    ClaimPipeline = _claim_pipeline_cls()
    config = _config(tmp_path)
    reordered = config.model_copy(
        update={
            "analysis": config.analysis.model_copy(
                update={
                    "coverage": config.analysis.coverage.model_copy(
                        update={"labels": ["3", "2", "1", "False"]},
                    ),
                },
            ),
        },
    )
    claim_dir = _seed_preprocessed_claim(reordered, claim_name="claim reorder-branch")
    chat_fn = _coverage_route_chat_fn(["1"], {"1": 0.9}, TRIP_CANCELLATION)
    pipeline = ClaimPipeline(reordered, chat_fn=chat_fn)

    result_path = pipeline.analyze_claim(claim_dir)
    payload = json.loads(result_path.read_text(encoding="utf-8"))

    expected = _COVERAGE_WINNER_EXPECTATIONS[TRIP_CANCELLATION]
    assert payload["routed_coverage_label_code"] == TRIP_CANCELLATION
    assert payload["routed_coverage_label"] == expected["routed_coverage_label"]
    assert payload.get("reason_label_codes", []) == expected["reason_label_codes"]
    assert payload.get("document_labels", []) == expected["document_labels"]
    assert payload["decision"] == expected["decision"]
    assert payload["decision_explanation"] == expected["decision_explanation"]
    assert payload["human_in_the_loop"] is expected["human_in_the_loop"]
    assert chat_fn.call_count == expected["call_count"]


def test_analyze_claim_cancellation_path_writes_analysis_result(
    tmp_path: Path,
    cancellation_chat_factory: CancellationChatFactory,
) -> None:
    """R010-R014: cancellation path writes analysis_result.json under results_dir."""
    ClaimPipeline = _claim_pipeline_cls()
    config = _config(tmp_path)
    claim_dir = _seed_preprocessed_claim(config)
    chat_fn = _cancellation_chat_fn(cancellation_chat_factory)
    pipeline = ClaimPipeline(config, chat_fn=chat_fn)

    result_path = pipeline.analyze_claim(claim_dir)

    expected = Path(config.preprocessing.results_dir) / claim_dir.name / config.preprocessing.artifacts.analysis_result
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
        Path(config.preprocessing.results_dir) / claim_dir.name / config.preprocessing.artifacts.predicted_answer
    )
    assert predicted_path.is_file()
    predicted = json.loads(predicted_path.read_text(encoding="utf-8"))
    assert predicted["decision"] == "APPROVE"
    assert predicted["source"] == "analysis"
    assert chat_fn.call_count >= 1


def test_coverage_node(
    tmp_path: Path,
    cancellation_chat_factory: CancellationChatFactory,
) -> None:
    """R011: coverage classifier runs on description.txt via injectable chat_fn."""
    ClaimPipeline = _claim_pipeline_cls()
    config = _config(tmp_path)
    claim_dir = _seed_preprocessed_claim(config)
    chat_fn = _cancellation_chat_fn(cancellation_chat_factory)
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


def test_routes_cancellation_to_reason(
    tmp_path: Path,
    cancellation_chat_factory: CancellationChatFactory,
) -> None:
    """R012: trip-cancellation coverage routes to cancellation_reason classifier."""
    ClaimPipeline = _claim_pipeline_cls()
    config = _config(tmp_path)
    claim_dir = _seed_preprocessed_claim(config)
    chat_fn = _cancellation_chat_fn(cancellation_chat_factory)
    pipeline = ClaimPipeline(config, chat_fn=chat_fn)

    result_path = pipeline.analyze_claim(claim_dir)
    payload = json.loads(result_path.read_text(encoding="utf-8"))

    assert MEDICAL_EMERGENCY in payload["reason_label_codes"]
    assert "Medical emergency" in payload["reason_labels"]
    assert chat_fn.call_count >= 2


def test_checker_node(
    tmp_path: Path,
    cancellation_chat_factory: CancellationChatFactory,
) -> None:
    """R014: Checker containment/contradicts run after document classification."""
    ClaimPipeline = _claim_pipeline_cls()
    config = _config(tmp_path)
    claim_dir = _seed_preprocessed_claim(config)
    chat_fn = _cancellation_chat_fn(cancellation_chat_factory)
    pipeline = ClaimPipeline(config, chat_fn=chat_fn)

    result_path = pipeline.analyze_claim(claim_dir)
    payload = json.loads(result_path.read_text(encoding="utf-8"))

    assert payload["checker_containment"] is True
    assert payload["checker_contradicts"] is False
    assert payload["identity_check"] is True
    assert payload["checker_document_not_authentic"] is False
    assert payload["checker_incomplete_document"] is False
    # Incomplete mode is the last medical checker LLM call; authenticity precedes it.
    last_content = chat_fn.call_args_list[-1].kwargs["messages"][0]["content"]
    assert "incomplete" in last_content
    authenticity_content = chat_fn.call_args_list[-2].kwargs["messages"][0]["content"]
    assert "authenticity" in authenticity_content
    healthy_content = chat_fn.call_args_list[-3].kwargs["messages"][0]["content"]
    assert "healthy" in healthy_content


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
    coverage = _chat_response({
        "labels": [TRIP_CANCELLATION],
        "probabilities": {TRIP_CANCELLATION: 0.9, "False": 0.1},
    })
    reason = _chat_response({
        "labels": [MEDICAL_EMERGENCY],
        "probabilities": {MEDICAL_EMERGENCY: 0.85, "False": 0.15},
    })
    document = _chat_response({
        "labels": [MEDICAL_CERTIFICATE],
        "probabilities": {MEDICAL_CERTIFICATE: 0.8, "False": 0.2},
    })
    contradicts = _chat_response({"result": False})
    identity = _chat_response({"name": "R"})
    healthy = _chat_response({"result": False})
    authenticity = _chat_response({"result": False})
    incomplete = _chat_response({"result": False})
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
            authenticity,
            incomplete,
        ]
    )
    pipeline = ClaimPipeline(config, chat_fn=chat_fn)

    result_path = pipeline.analyze_claim(claim_dir)
    payload = json.loads(result_path.read_text(encoding="utf-8"))

    assert payload["identity_check"] is False
    assert payload["identity_unclear"] is False
    assert payload["decision"] == "DENY"
    assert "identity_check" in payload["decision_explanation"]
    identity_user = chat_fn.call_args_list[-4].kwargs["messages"][1]["content"]
    assert "Patient: R" in identity_user
    assert "patient" in identity_user.lower()
    predicted = json.loads(
        (
            Path(config.preprocessing.results_dir) / claim_dir.name / config.preprocessing.artifacts.predicted_answer
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
    coverage = _chat_response({
        "labels": [TRIP_CANCELLATION],
        "probabilities": {TRIP_CANCELLATION: 0.9, "False": 0.1},
    })
    reason = _chat_response({
        "labels": [MEDICAL_EMERGENCY],
        "probabilities": {MEDICAL_EMERGENCY: 0.85, "False": 0.15},
    })
    document = _chat_response({
        "labels": [MEDICAL_CERTIFICATE],
        "probabilities": {MEDICAL_CERTIFICATE: 0.8, "False": 0.2},
    })
    containment = _chat_response({"result": False})
    contradicts = _chat_response({"result": False})
    identity = _chat_response({"name": None})
    healthy = _chat_response({"result": False})
    authenticity = _chat_response({"result": False})
    incomplete = _chat_response({"result": False})
    chat_fn = MagicMock(
        side_effect=[
            coverage,
            reason,
            document,
            containment,
            contradicts,
            identity,
            healthy,
            authenticity,
            incomplete,
        ]
    )
    pipeline = ClaimPipeline(config, chat_fn=chat_fn)

    result_path = pipeline.analyze_claim(claim_dir)
    payload = json.loads(result_path.read_text(encoding="utf-8"))

    assert payload["identity_check"] is False
    assert payload["identity_unclear"] is True
    assert payload["decision"] == "UNCERTAIN"
    assert payload["decision_explanation"] == "identity_unclear"
    assert payload["human_in_the_loop"] is True
    predicted = json.loads(
        (Path(config.preprocessing.results_dir) / claim_dir.name / artifacts.predicted_answer).read_text(
            encoding="utf-8"
        )
    )
    assert predicted["human_in_the_loop"] is True
    meta = json.loads((claim_dir / artifacts.document_metadata).read_text(encoding="utf-8"))
    assert meta["documents"][0]["human_in_the_loop"] is True


def test_identity_skipped_for_non_medical_document(tmp_path: Path) -> None:
    """Personal-effects docs do not run identity LLM; identity_check passes."""
    ClaimPipeline = _claim_pipeline_cls()
    config = _config(tmp_path)
    claim_dir = _seed_preprocessed_claim(config, claim_name="claim pe identity skip")
    artifacts = config.preprocessing.artifacts
    (claim_dir / artifacts.description).write_text("My suitcase was stolen from the hotel lobby.", encoding="utf-8")
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
    system_prompts = [call.kwargs["messages"][0]["content"] for call in chat_fn.call_args_list]
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
        json.dumps({
            "documents": [
                {
                    "source_file": "hospital admission document.png",
                    "has_signature": False,
                }
            ]
        })
        + "\n",
        encoding="utf-8",
    )
    coverage = _chat_response({
        "labels": [TRIP_CANCELLATION],
        "probabilities": {TRIP_CANCELLATION: 0.9, "False": 0.1},
    })
    reason = _chat_response({
        "labels": [MEDICAL_EMERGENCY],
        "probabilities": {MEDICAL_EMERGENCY: 0.85, "False": 0.15},
    })
    document = _chat_response({
        "labels": [HOSPITAL_ADMISSION],
        "probabilities": {HOSPITAL_ADMISSION: 0.8, "False": 0.2},
    })
    contradicts = _chat_response({"result": False})
    healthy = _chat_response({"result": False})
    authenticity = _chat_response({"result": False})
    incomplete = _chat_response({"result": False})
    chat_fn = MagicMock(
        side_effect=[
            coverage,
            reason,
            document,
            contradicts,
            healthy,
            authenticity,
            incomplete,
        ]
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
        "Patient: Ada Lovelace\n"
        "En el momento se encuentra CLÍNICAMENTE SANA\n"
        "APTO PARA REALIZAR ACTIVIDAD FÍSICA: SI\n",
        encoding="utf-8",
    )
    coverage = _chat_response({
        "labels": [TRIP_CANCELLATION],
        "probabilities": {TRIP_CANCELLATION: 0.9, "False": 0.1},
    })
    reason = _chat_response({
        "labels": [MEDICAL_EMERGENCY],
        "probabilities": {MEDICAL_EMERGENCY: 0.85, "False": 0.15},
    })
    document = _chat_response({
        "labels": [MEDICAL_CERTIFICATE],
        "probabilities": {MEDICAL_CERTIFICATE: 0.8, "False": 0.2},
    })
    containment = _chat_response({"result": False})
    contradicts = _chat_response({"result": False})
    healthy = _chat_response({"result": True})
    authenticity = _chat_response({"result": False})
    incomplete = _chat_response({"result": False})
    chat_fn = MagicMock(
        side_effect=[
            coverage,
            reason,
            document,
            containment,
            contradicts,
            healthy,
            authenticity,
            incomplete,
        ]
    )
    pipeline = ClaimPipeline(config, chat_fn=chat_fn)

    result_path = pipeline.analyze_claim(claim_dir)
    payload = json.loads(result_path.read_text(encoding="utf-8"))

    assert payload["healthy_check"] is True
    assert payload["decision"] == "DENY"
    assert "healthy_check" in payload["decision_explanation"]
    healthy_user = chat_fn.call_args_list[-3].kwargs["messages"][1]["content"]
    assert "CLÍNICAMENTE SANA" in healthy_user
    assert "Supporting document" in healthy_user


def _contradicts_deny_chat_fn() -> MagicMock:
    """Injected chat_fn: cancellation path with checker_contradicts True."""
    coverage = _chat_response({
        "labels": [TRIP_CANCELLATION],
        "probabilities": {TRIP_CANCELLATION: 0.9, "False": 0.1},
    })
    reason = _chat_response({
        "labels": [MEDICAL_EMERGENCY],
        "probabilities": {MEDICAL_EMERGENCY: 0.85, "False": 0.15},
    })
    document = _chat_response({
        "labels": [MEDICAL_CERTIFICATE],
        "probabilities": {MEDICAL_CERTIFICATE: 0.8, "False": 0.2},
    })
    contradicts = _chat_response({"result": True})
    healthy = _chat_response({"result": False})
    authenticity = _chat_response({"result": False})
    incomplete = _chat_response({"result": False})
    return MagicMock(
        side_effect=[
            coverage,
            reason,
            document,
            contradicts,
            healthy,
            authenticity,
            incomplete,
        ]
    )


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
            Path(config.preprocessing.results_dir) / claim_dir.name / config.preprocessing.artifacts.predicted_answer
        ).read_text(encoding="utf-8")
    )
    assert predicted["decision"] == "DENY"
    assert "checker_contradicts" in predicted["explanation"]


def _wrong_document_type_chat_fn() -> MagicMock:
    """Medical-emergency reason but police-report document (not acceptable)."""
    coverage = _chat_response({
        "labels": [TRIP_CANCELLATION],
        "probabilities": {TRIP_CANCELLATION: 0.9, "False": 0.1},
    })
    reason = _chat_response({
        "labels": [MEDICAL_EMERGENCY],
        "probabilities": {MEDICAL_EMERGENCY: 0.85, "False": 0.15},
    })
    document = _chat_response({
        "labels": ["2"],
        "probabilities": {"2": 0.8, "False": 0.2},
    })
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
    coverage = _chat_response({
        "labels": [TRIP_CANCELLATION],
        "probabilities": {TRIP_CANCELLATION: 0.9, "False": 0.1},
    })
    reason = _chat_response({
        "labels": [MEDICAL_EMERGENCY],
        "probabilities": {MEDICAL_EMERGENCY: 0.85, "False": 0.15},
    })
    document = _chat_response({
        "labels": [COVERAGE_OTHER],
        "probabilities": {COVERAGE_OTHER: 0.9},
    })
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


def test_unit_path_uses_injected_chat_fn(
    tmp_path: Path,
    cancellation_chat_factory: CancellationChatFactory,
) -> None:
    """R016: unit path injects MagicMock chat_fn; never calls live Ollama."""
    ClaimPipeline = _claim_pipeline_cls()
    config = _config(tmp_path)
    claim_dir = _seed_preprocessed_claim(config)
    chat_fn = _cancellation_chat_fn(cancellation_chat_factory)
    pipeline = ClaimPipeline(config, chat_fn=chat_fn)

    pipeline.analyze_claim(claim_dir)

    assert chat_fn.call_count >= 1


def _pe_chat_fn() -> MagicMock:
    """Injected chat_fn: coverage PE → PE document → checker contradicts."""
    coverage = _chat_response({
        "labels": [PERSONAL_EFFECTS],
        "probabilities": {PERSONAL_EFFECTS: 0.9, "False": 0.1},
    })
    document = _chat_response({
        "labels": [PROOF_OF_THEFT],
        "probabilities": {PROOF_OF_THEFT: 0.85, "False": 0.15},
    })
    contradicts = _chat_response({"result": False})
    healthy = _chat_response({"result": False})
    return MagicMock(side_effect=[coverage, document, contradicts, healthy])


def _missed_chat_fn() -> MagicMock:
    """Injected chat_fn: coverage missed → missed document → checker (no identity)."""
    coverage = _chat_response({
        "labels": [MISSED_DEPARTURE],
        "probabilities": {MISSED_DEPARTURE: 0.9, "False": 0.1},
    })
    document = _chat_response({
        "labels": [INCIDENT_REPORT, PROOF_OF_BOOKING],
        "probabilities": {
            INCIDENT_REPORT: 0.7,
            PROOF_OF_BOOKING: 0.6,
            "False": 0.1,
        },
    })
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
    assert "Incident report or documentation explaining the cause of delay" in payload["document_labels"]
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
    coverage = _chat_response({
        "labels": [COVERAGE_OTHER],
        "probabilities": {COVERAGE_OTHER: 0.95},
    })
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
            Path(config.preprocessing.results_dir) / "claim other" / config.preprocessing.artifacts.predicted_answer
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
    coverage = _chat_response({
        "labels": [COVERAGE_FALSE],
        "probabilities": {COVERAGE_FALSE: 0.9},
    })
    chat_fn = MagicMock(side_effect=[coverage])
    pipeline = ClaimPipeline(config, chat_fn=chat_fn)

    result_path = pipeline.analyze_claim(claim_dir)
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    predicted = json.loads(
        (Path(config.preprocessing.results_dir) / "claim false" / artifacts.predicted_answer).read_text(
            encoding="utf-8"
        )
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
    coverage = _chat_response({
        "labels": [TRIP_CANCELLATION],
        "probabilities": {TRIP_CANCELLATION: 0.9, "False": 0.1},
    })
    reason = _chat_response({
        "labels": [MEDICAL_EMERGENCY],
        "probabilities": {MEDICAL_EMERGENCY: 0.85, "False": 0.15},
    })
    document = _chat_response({
        "labels": [COVERAGE_FALSE],
        "probabilities": {COVERAGE_FALSE: 0.8, "False": 0.2},
    })
    containment = _chat_response({"result": False})
    contradicts = _chat_response({"result": False})
    healthy = _chat_response({"result": False})
    chat_fn = MagicMock(side_effect=[coverage, reason, document, containment, contradicts, healthy])
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
            pytest.fail("should not join before validation")

    with pytest.raises(ValueError, match="Unsafe claim directory name"):
        pipeline.analyze_claim(_UnsafeDir())  # type: ignore[arg-type]

    class _DotDot:
        name = ".."

        def __truediv__(self, other: object) -> Path:
            pytest.fail("should not join before validation")

    with pytest.raises(ValueError, match="Unsafe claim directory name"):
        pipeline.analyze_claim(_DotDot())  # type: ignore[arg-type]

    assert set(results_root.iterdir()) == before
    chat_fn.assert_not_called()


def _repeating_cancellation_chat_fn() -> MagicMock:
    """Chat seam that repeats the cancellation path responses for batch runs."""
    from itertools import cycle

    coverage = _chat_response({
        "labels": [TRIP_CANCELLATION],
        "probabilities": {TRIP_CANCELLATION: 0.9, "False": 0.1},
    })
    reason = _chat_response({
        "labels": [MEDICAL_EMERGENCY],
        "probabilities": {MEDICAL_EMERGENCY: 0.85, "False": 0.15},
    })
    document = _chat_response({
        "labels": [MEDICAL_CERTIFICATE],
        "probabilities": {MEDICAL_CERTIFICATE: 0.8, "False": 0.2},
    })
    contradicts = _chat_response({"result": False})
    healthy = _chat_response({"result": False})
    authenticity = _chat_response({"result": False})
    incomplete = _chat_response({"result": False})
    return MagicMock(
        side_effect=cycle([
            coverage,
            reason,
            document,
            contradicts,
            healthy,
            authenticity,
            incomplete,
        ])
    )


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
    stage = "\n".join([
        '    labels: ["1"]',
        '    other_label: "False"',
        "    model: test-model",
        "    prompt: classify",
    ])
    coverage_stage = "\n".join([
        '    labels: ["1"]',
        "    branches:",
        '      "1": cancellation',
        '    other_label: "False"',
        "    model: test-model",
        "    prompt: classify",
    ])
    cfg_path.write_text(
        "\n".join([
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
            '  labels: ["1"]',
            '  other_label: "False"',
            "  model: test-model",
            "  prompt: classify",
            "checking:",
            "  model: test-model",
            "  containment_prompt: containment",
            "  contradicts_prompt: contradicts",
            "  identity_prompt: identity",
            "  healthy_prompt: healthy",
            "  authenticity_prompt: authenticity",
            "  incomplete_prompt: incomplete",
            "analysis:",
            "  coverage:",
            coverage_stage,
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
        ]),
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

    def _fake_preprocess(self: PreprocessingPipeline, source: Path | None = None) -> list[Path]:
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

    def _fake_preprocess(self: PreprocessingPipeline, source: Path | None = None) -> list[Path]:
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


def _with_departure_uncertain_enabled(config: AppConfig) -> AppConfig:
    """Return a copy of ``config`` with the far-departure UNCERTAIN gate on."""
    return config.model_copy(
        update={"checking": config.checking.model_copy(update={"departure_uncertain_enabled": True})}
    )


def _with_transport_retry(
    config: AppConfig,
    *,
    max_retries: int,
    backoff_seconds: float,
) -> AppConfig:
    """Return a copy of ``config`` with checker transport_retry overridden."""
    return config.model_copy(
        update={
            "checking": config.checking.model_copy(
                update={
                    "transport_retry": TransportRetryConfig(
                        max_retries=max_retries,
                        backoff_seconds=backoff_seconds,
                    )
                }
            )
        }
    )


def test_uncertain_departure_within_days_skips_llm_checkers(tmp_path: Path) -> None:
    """Medical path: departure farther than n days → UNCERTAIN; skip LLM checkers."""
    from datetime import date

    ClaimPipeline = _claim_pipeline_cls()
    config = _with_departure_uncertain_enabled(_config(tmp_path))
    assert getattr(config.checking, "departure_uncertain_within_days", None) == 14
    assert config.checking.departure_uncertain_enabled is True
    claim_dir = _seed_preprocessed_claim(config, claim_name="claim departure within")
    artifacts = config.preprocessing.artifacts
    (claim_dir / artifacts.supporting_documents).write_text(
        "# Supporting documents\n\n"
        "**current date**: 2017-08-01\n"
        "**name**: Olivier Bayante\n"
        "**departure**: 2017-08-20 13:15 (local)\n",
        encoding="utf-8",
    )
    # OCR may contain multiple calendar days; multiple_document_dates was removed.
    (claim_dir / artifacts.supporting_document).write_text(
        "# Supporting document\n\n"
        "I had to cancel my flight to Paris because of a medical emergency.\n"
        "Certificate dated 14 April 2017.\n",
        encoding="utf-8",
    )
    coverage = _chat_response({
        "labels": [TRIP_CANCELLATION],
        "probabilities": {TRIP_CANCELLATION: 0.9, "False": 0.1},
    })
    reason = _chat_response({
        "labels": [MEDICAL_EMERGENCY],
        "probabilities": {MEDICAL_EMERGENCY: 0.85, "False": 0.15},
    })
    document = _chat_response({
        "labels": [MEDICAL_CERTIFICATE],
        "probabilities": {MEDICAL_CERTIFICATE: 0.8, "False": 0.2},
    })
    chat_fn = MagicMock(side_effect=[coverage, reason, document])
    pipeline = ClaimPipeline(config, chat_fn=chat_fn)

    result_path = pipeline.analyze_claim(claim_dir)
    payload = json.loads(result_path.read_text(encoding="utf-8"))

    assert payload["decision"] == "UNCERTAIN"
    assert payload["decision_explanation"] == "departure_within_days"
    assert payload["departure_within_days"] is True
    assert payload["human_in_the_loop"] is True
    assert "checker_containment" not in payload
    assert "checker_contradicts" not in payload
    assert "identity_check" not in payload
    assert "healthy_check" not in payload
    # coverage + reason + document only — no containment/contradicts/identity/healthy
    assert chat_fn.call_count == 3
    system_prompts = [call.kwargs["messages"][0]["content"] for call in chat_fn.call_args_list]
    joined = "\n".join(system_prompts).lower()
    assert "containment" not in joined
    assert "contradicts" not in joined
    assert "identity" not in joined
    assert "healthy" not in joined
    assert all("classify" in prompt for prompt in system_prompts)

    # Helper: distance > n → True; distance ≤ n → False; unparseable → False
    from compliance.workflows.claim_dates import _departure_beyond_days

    departure_fn = _departure_beyond_days
    assert (
        departure_fn(
            supporting_documents_text=("**current date**: 2017-08-01\n**departure**: 2017-08-15\n"),
            description_text="",
            today=date(2017, 8, 1),
            within_days=14,
        )
        is False
    )
    assert (
        departure_fn(
            supporting_documents_text=("**current date**: 2017-08-01\n**departure**: 2017-08-16\n"),
            description_text="",
            today=date(2017, 8, 1),
            within_days=14,
        )
        is True
    )
    assert (
        departure_fn(
            supporting_documents_text="**departure**: not-a-date\n",
            description_text="also no date here",
            today=date(2017, 8, 1),
            within_days=14,
        )
        is False
    )


def test_unique_calendar_dates_helper(tmp_path: Path) -> None:
    """Shared OCR date extractor still used by suspicious-dating / departure."""
    from datetime import date

    from compliance.workflows.claim_dates import _unique_calendar_dates

    dates = _unique_calendar_dates("Seen 14 April 2017 and again on April 20, 2017. Stamp 14/04/2017.")
    assert dates == {date(2017, 4, 14), date(2017, 4, 20)}
    assert len(_unique_calendar_dates("Visit 2017-04-14 and again 14/04/2017.")) == 1


def test_suspicious_dating_ignores_dob_outside_year_window() -> None:
    """Dates farther than consider_within_years are DOB/history, not suspicious."""
    from datetime import date

    from compliance.workflows.claim_dates import _suspicious_dating

    # Claim-16 shaped: DOB 1980 + care dates near reference today.
    text = (
        "CERTIFICATO DI RICOVERO. Si Attesta che PICCIRILLI FRANCESCA "
        "nata il 30-07-1980. Ricoverata il 14-04-2017 dimesso il 20-04-2017. "
        "Issue stamp present."
    )
    assert (
        _suspicious_dating(
            text,
            today=date(2017, 5, 11),
            max_month_delta=6,
            consider_within_years=2,
        )
        is False
    )
    # Eligible stamp within ±2y but ≥6 months away still fires.
    assert (
        _suspicious_dating(
            "Certificate issue date 2016-01-01.\n",
            today=date(2017, 5, 11),
            max_month_delta=6,
            consider_within_years=2,
        )
        is True
    )


def test_departure_within_days_skips_llm_even_with_multiple_ocr_dates(
    tmp_path: Path,
) -> None:
    """Departure proximity UNCERTAIN early-exits; multiple OCR dates do not decide."""
    ClaimPipeline = _claim_pipeline_cls()
    config = _with_departure_uncertain_enabled(_config(tmp_path))
    claim_dir = _seed_preprocessed_claim(config, claim_name="claim departure multi ocr")
    artifacts = config.preprocessing.artifacts
    (claim_dir / artifacts.supporting_documents).write_text(
        "# Supporting documents\n\n"
        "**current date**: 2017-08-01\n"
        "**name**: Olivier Bayante\n"
        "**departure**: 2017-08-20\n",
        encoding="utf-8",
    )
    (claim_dir / artifacts.supporting_document).write_text(
        "# Supporting document\n\n"
        "I had to cancel my flight to Paris because of a medical emergency.\n"
        "Certificate dated 01/08/2017. Discharge 10/08/2017.\n",
        encoding="utf-8",
    )
    coverage = _chat_response({
        "labels": [TRIP_CANCELLATION],
        "probabilities": {TRIP_CANCELLATION: 0.9, "False": 0.1},
    })
    reason = _chat_response({
        "labels": [MEDICAL_EMERGENCY],
        "probabilities": {MEDICAL_EMERGENCY: 0.85, "False": 0.15},
    })
    document = _chat_response({
        "labels": [MEDICAL_CERTIFICATE],
        "probabilities": {MEDICAL_CERTIFICATE: 0.8, "False": 0.2},
    })
    chat_fn = MagicMock(side_effect=[coverage, reason, document])
    pipeline = ClaimPipeline(config, chat_fn=chat_fn)

    result_path = pipeline.analyze_claim(claim_dir)
    payload = json.loads(result_path.read_text(encoding="utf-8"))

    assert payload["departure_within_days"] is True
    assert "multiple_document_dates" not in payload
    assert payload["decision"] == "UNCERTAIN"
    assert payload["decision_explanation"] == "departure_within_days"
    assert chat_fn.call_count == 3
    assert "checker_contradicts" not in payload


# --- Phase 07 authenticity (R027) / incomplete (R028) / suspicious dating (R029) ---


def test_deny_when_checker_document_not_authentic(tmp_path: Path) -> None:
    """OCR/format authenticity violation → DENY with checker_document_not_authentic.

    Claim 8/18-shaped synthetic OCR (no live Docling). Injectable chat_fn only.
    """
    ClaimPipeline = _claim_pipeline_cls()
    config = _config(tmp_path)
    claim_dir = _seed_preprocessed_claim(config, claim_name="claim not authentic")
    artifacts = config.preprocessing.artifacts
    (claim_dir / artifacts.supporting_document).write_text(
        "# Hospital admission document\n\n"
        "Patient: Ada Lovelace\n"
        "Patient admitted ### garbled OCR @@ format anomaly\n"
        "Stamp unreadable.\n",
        encoding="utf-8",
    )
    coverage = _chat_response({
        "labels": [TRIP_CANCELLATION],
        "probabilities": {TRIP_CANCELLATION: 0.9, "False": 0.1},
    })
    reason = _chat_response({
        "labels": [MEDICAL_EMERGENCY],
        "probabilities": {MEDICAL_EMERGENCY: 0.85, "False": 0.15},
    })
    document = _chat_response({
        "labels": [HOSPITAL_ADMISSION],
        "probabilities": {HOSPITAL_ADMISSION: 0.8, "False": 0.2},
    })
    containment = _chat_response({"result": False})
    contradicts = _chat_response({"result": False})
    healthy = _chat_response({"result": False})
    not_authentic = _chat_response({"result": True})
    incomplete = _chat_response({"result": False})
    chat_fn = MagicMock(
        side_effect=[
            coverage,
            reason,
            document,
            containment,
            contradicts,
            healthy,
            not_authentic,
            incomplete,
        ]
    )
    pipeline = ClaimPipeline(config, chat_fn=chat_fn)

    result_path = pipeline.analyze_claim(claim_dir)
    payload = json.loads(result_path.read_text(encoding="utf-8"))

    assert payload["checker_document_not_authentic"] is True
    assert payload["decision"] == "DENY"
    assert "checker_document_not_authentic" in payload["decision_explanation"]


def test_deny_when_checker_incomplete_document(tmp_path: Path) -> None:
    """Missing medical fields (discharge/diagnosis/condition) → DENY incomplete.

    Signature may still pass separately; incomplete is its own payload key (R028).
    """
    ClaimPipeline = _claim_pipeline_cls()
    config = _config(tmp_path)
    claim_dir = _seed_preprocessed_claim(config, claim_name="claim incomplete doc")
    artifacts = config.preprocessing.artifacts
    (claim_dir / artifacts.supporting_document).write_text(
        "# CERTIFICADO MÉDICO\n\n"
        "Patient: Ada Lovelace\n"
        "Patient name present. No diagnosis, discharge, or condition stated.\n",
        encoding="utf-8",
    )
    coverage = _chat_response({
        "labels": [TRIP_CANCELLATION],
        "probabilities": {TRIP_CANCELLATION: 0.9, "False": 0.1},
    })
    reason = _chat_response({
        "labels": [MEDICAL_EMERGENCY],
        "probabilities": {MEDICAL_EMERGENCY: 0.85, "False": 0.15},
    })
    document = _chat_response({
        "labels": [MEDICAL_CERTIFICATE],
        "probabilities": {MEDICAL_CERTIFICATE: 0.8, "False": 0.2},
    })
    containment = _chat_response({"result": False})
    contradicts = _chat_response({"result": False})
    healthy = _chat_response({"result": False})
    not_authentic = _chat_response({"result": False})
    incomplete = _chat_response({"result": True})
    chat_fn = MagicMock(
        side_effect=[
            coverage,
            reason,
            document,
            containment,
            contradicts,
            healthy,
            not_authentic,
            incomplete,
        ]
    )
    pipeline = ClaimPipeline(config, chat_fn=chat_fn)

    result_path = pipeline.analyze_claim(claim_dir)
    payload = json.loads(result_path.read_text(encoding="utf-8"))

    assert payload.get("checker_incomplete_document") is True
    assert payload["decision"] == "DENY"
    assert "checker_incomplete_document" in payload["decision_explanation"]


def test_uncertain_when_checker_suspicious_dating(tmp_path: Path) -> None:
    """Implausible issue/stamp dating → UNCERTAIN before DENY (R029).

    Single OCR calendar day with month skew ≥ half a year vs booking reference.
    Explanation key checker_suspicious_dating; LLM checker keys omitted.
    """
    ClaimPipeline = _claim_pipeline_cls()
    config = _config(tmp_path)
    claim_dir = _seed_preprocessed_claim(config, claim_name="claim suspicious dating")
    artifacts = config.preprocessing.artifacts
    (claim_dir / artifacts.supporting_documents).write_text(
        "# Supporting documents\n\n"
        "**current date**: 2022-06-01\n"
        "**name**: Test Claimant\n"
        "**departure**: 2022-09-01 10:00 (local)\n",
        encoding="utf-8",
    )
    (claim_dir / artifacts.supporting_document).write_text(
        "# Supporting document\n\nCertificate issue date 2021-01-01.\n",
        encoding="utf-8",
    )
    coverage = _chat_response({
        "labels": [TRIP_CANCELLATION],
        "probabilities": {TRIP_CANCELLATION: 0.9, "False": 0.1},
    })
    reason = _chat_response({
        "labels": [MEDICAL_EMERGENCY],
        "probabilities": {MEDICAL_EMERGENCY: 0.85, "False": 0.15},
    })
    document = _chat_response({
        "labels": [MEDICAL_CERTIFICATE],
        "probabilities": {MEDICAL_CERTIFICATE: 0.8, "False": 0.2},
    })
    # Extra checker responses for RED (no early-exit yet); GREEN omits LLM checkers.
    containment = _chat_response({"result": False})
    contradicts = _chat_response({"result": False})
    identity = _chat_response({"result": True})
    healthy = _chat_response({"result": False})
    not_authentic = _chat_response({"result": False})
    incomplete = _chat_response({"result": False})
    chat_fn = MagicMock(
        side_effect=[
            coverage,
            reason,
            document,
            containment,
            contradicts,
            identity,
            healthy,
            not_authentic,
            incomplete,
        ]
    )
    pipeline = ClaimPipeline(config, chat_fn=chat_fn)

    result_path = pipeline.analyze_claim(claim_dir)
    payload = json.loads(result_path.read_text(encoding="utf-8"))

    assert payload.get("checker_suspicious_dating") is True
    assert payload["decision"] == "UNCERTAIN"
    assert payload["decision_explanation"] == "checker_suspicious_dating"
    assert payload["human_in_the_loop"] is True
    predicted = json.loads(
        (Path(config.preprocessing.results_dir) / claim_dir.name / artifacts.predicted_answer).read_text(
            encoding="utf-8"
        )
    )
    assert predicted["human_in_the_loop"] is True
    assert "checker_document_not_authentic" not in payload
    assert "checker_incomplete_document" not in payload
    assert chat_fn.call_count == 3


def test_suspicious_dating_false_when_coherent_dates(tmp_path: Path) -> None:
    """Single coherent care-window date without month skew → explicit False."""
    ClaimPipeline = _claim_pipeline_cls()
    config = _config(tmp_path)
    claim_dir = _seed_preprocessed_claim(config, claim_name="claim coherent dating")
    artifacts = config.preprocessing.artifacts
    (claim_dir / artifacts.supporting_documents).write_text(
        "# Supporting documents\n\n"
        "**current date**: 2022-06-01\n"
        "**name**: Test Claimant\n"
        "**departure**: 2022-09-01 10:00 (local)\n",
        encoding="utf-8",
    )
    (claim_dir / artifacts.supporting_document).write_text(
        "# Supporting document\n\nPatient: Test Claimant\nMedical certificate dated 2022-05-20. Diagnosis: fracture.\n",
        encoding="utf-8",
    )
    coverage = _chat_response({
        "labels": [TRIP_CANCELLATION],
        "probabilities": {TRIP_CANCELLATION: 0.9, "False": 0.1},
    })
    reason = _chat_response({
        "labels": [MEDICAL_EMERGENCY],
        "probabilities": {MEDICAL_EMERGENCY: 0.85, "False": 0.15},
    })
    document = _chat_response({
        "labels": [MEDICAL_CERTIFICATE],
        "probabilities": {MEDICAL_CERTIFICATE: 0.8, "False": 0.2},
    })
    containment = _chat_response({"result": False})
    contradicts = _chat_response({"result": False})
    healthy = _chat_response({"result": False})
    not_authentic = _chat_response({"result": False})
    incomplete = _chat_response({"result": False})
    chat_fn = MagicMock(
        side_effect=[
            coverage,
            reason,
            document,
            containment,
            contradicts,
            healthy,
            not_authentic,
            incomplete,
        ]
    )
    pipeline = ClaimPipeline(config, chat_fn=chat_fn)

    result_path = pipeline.analyze_claim(claim_dir)
    payload = json.loads(result_path.read_text(encoding="utf-8"))

    assert payload.get("checker_suspicious_dating") is False
    assert payload["decision"] == "APPROVE"


def test_suspicious_dating_precedes_deny(tmp_path: Path) -> None:
    """Suspicious dating True + signature DENY → UNCERTAIN (date flags before DENY)."""
    ClaimPipeline = _claim_pipeline_cls()
    config = _config(tmp_path)
    claim_dir = _seed_preprocessed_claim(config, claim_name="claim dating precedes deny")
    artifacts = config.preprocessing.artifacts
    (claim_dir / artifacts.supporting_documents).write_text(
        "# Supporting documents\n\n"
        "**current date**: 2022-06-01\n"
        "**name**: Test Claimant\n"
        "**departure**: 2022-09-01 10:00 (local)\n",
        encoding="utf-8",
    )
    (claim_dir / artifacts.supporting_document).write_text(
        "# Supporting document\n\nCertificate issue date 2021-01-01.\n",
        encoding="utf-8",
    )
    (claim_dir / artifacts.document_metadata).write_text(
        json.dumps({
            "documents": [
                {
                    "source_file": "medical certificate.jpg",
                    "has_signature": False,
                }
            ]
        })
        + "\n",
        encoding="utf-8",
    )
    coverage = _chat_response({
        "labels": [TRIP_CANCELLATION],
        "probabilities": {TRIP_CANCELLATION: 0.9, "False": 0.1},
    })
    reason = _chat_response({
        "labels": [MEDICAL_EMERGENCY],
        "probabilities": {MEDICAL_EMERGENCY: 0.85, "False": 0.15},
    })
    document = _chat_response({
        "labels": [MEDICAL_CERTIFICATE],
        "probabilities": {MEDICAL_CERTIFICATE: 0.8, "False": 0.2},
    })
    containment = _chat_response({"result": False})
    contradicts = _chat_response({"result": False})
    identity = _chat_response({"result": True})
    healthy = _chat_response({"result": False})
    not_authentic = _chat_response({"result": False})
    incomplete = _chat_response({"result": False})
    chat_fn = MagicMock(
        side_effect=[
            coverage,
            reason,
            document,
            containment,
            contradicts,
            identity,
            healthy,
            not_authentic,
            incomplete,
        ]
    )
    pipeline = ClaimPipeline(config, chat_fn=chat_fn)

    result_path = pipeline.analyze_claim(claim_dir)
    payload = json.loads(result_path.read_text(encoding="utf-8"))

    assert payload.get("checker_suspicious_dating") is True
    assert payload.get("signature_check") is False
    assert payload["decision"] == "UNCERTAIN"
    assert payload["decision_explanation"] == "checker_suspicious_dating"


def test_authenticity_incomplete_skipped_for_non_medical_document(
    tmp_path: Path,
) -> None:
    """PE/missed path must not invoke authenticity or incomplete chat prompts."""
    ClaimPipeline = _claim_pipeline_cls()
    config = _config(tmp_path)
    claim_dir = _seed_preprocessed_claim(config, claim_name="claim pe auth skip")
    artifacts = config.preprocessing.artifacts
    (claim_dir / artifacts.description).write_text("My suitcase was stolen from the hotel lobby.", encoding="utf-8")
    (claim_dir / artifacts.supporting_document).write_text(
        "My suitcase was stolen from the hotel lobby.\nPolice report filed.",
        encoding="utf-8",
    )
    chat_fn = _pe_chat_fn()
    pipeline = ClaimPipeline(config, chat_fn=chat_fn)

    result_path = pipeline.analyze_claim(claim_dir)
    payload = json.loads(result_path.read_text(encoding="utf-8"))

    assert "checker_document_not_authentic" not in payload
    assert "checker_incomplete_document" not in payload
    system_prompts = [call.kwargs["messages"][0]["content"] for call in chat_fn.call_args_list]
    joined = "\n".join(system_prompts).lower()
    assert "authenticity" not in joined
    assert "incomplete" not in joined


def test_payload_omits_llm_keys_on_date_uncertain_early_exit(
    tmp_path: Path,
) -> None:
    """When date UNCERTAIN early-exits, authenticity/incomplete keys stay omitted."""
    ClaimPipeline = _claim_pipeline_cls()
    config = _with_departure_uncertain_enabled(_config(tmp_path))
    claim_dir = _seed_preprocessed_claim(config, claim_name="claim date omit keys")
    artifacts = config.preprocessing.artifacts
    (claim_dir / artifacts.supporting_documents).write_text(
        "# Supporting documents\n\n"
        "**current date**: 2017-08-01\n"
        "**name**: Olivier Bayante\n"
        "**departure**: 2017-08-20 13:15 (local)\n",
        encoding="utf-8",
    )
    (claim_dir / artifacts.supporting_document).write_text(
        "# Supporting document\n\nCertificate dated 14 April 2017.\n",
        encoding="utf-8",
    )
    coverage = _chat_response({
        "labels": [TRIP_CANCELLATION],
        "probabilities": {TRIP_CANCELLATION: 0.9, "False": 0.1},
    })
    reason = _chat_response({
        "labels": [MEDICAL_EMERGENCY],
        "probabilities": {MEDICAL_EMERGENCY: 0.85, "False": 0.15},
    })
    document = _chat_response({
        "labels": [MEDICAL_CERTIFICATE],
        "probabilities": {MEDICAL_CERTIFICATE: 0.8, "False": 0.2},
    })
    chat_fn = MagicMock(side_effect=[coverage, reason, document])
    pipeline = ClaimPipeline(config, chat_fn=chat_fn)

    result_path = pipeline.analyze_claim(claim_dir)
    payload = json.loads(result_path.read_text(encoding="utf-8"))

    assert payload["decision"] == "UNCERTAIN"
    assert "checker_document_not_authentic" not in payload
    assert "checker_incomplete_document" not in payload
    assert "checker_suspicious_dating" not in payload


# --- SR-008: typed CheckOutcome policy matrix ---

_BOOLEAN_CHECKER_MODES = (
    "containment",
    "contradicts",
    "healthy",
    "not_authentic",
    "incomplete",
)

# Benign defaults for medical checker modes (identity is deterministic PASS when
# booking/patient names match Ada Lovelace in the seeded OCR).
_BENIGN_CHECKER_OVERRIDES: dict[str, str] = {
    "containment": json.dumps({"result": True}),
    "contradicts": json.dumps({"result": False}),
    "healthy": json.dumps({"result": False}),
    "not_authentic": json.dumps({"result": False}),
    "incomplete": json.dumps({"result": False}),
}

# Containment ERROR is record-only (D-01 / P-01 locked): outcome ERROR, decision APPROVE.
_POLICY_MATRIX: list[tuple[str, str, str, str, str | None]] = []
for _mode in _BOOLEAN_CHECKER_MODES:
    _deny_key = {
        "containment": None,
        "contradicts": "checker_contradicts",
        "healthy": "healthy_check",
        "not_authentic": "checker_document_not_authentic",
        "incomplete": "checker_incomplete_document",
    }[_mode]
    _true_outcome = "PASS" if _mode == "containment" else "VIOLATION"
    _false_outcome = "ABSTAIN" if _mode == "containment" else "PASS"
    _true_decision = "APPROVE" if _mode == "containment" else "DENY"
    _true_explanation = "checker_consistent" if _mode == "containment" else _deny_key
    _error_decision = "APPROVE" if _mode == "containment" else "UNCERTAIN"
    _error_explanation = "checker_consistent" if _mode == "containment" else f"checker_error:{_mode}"
    _POLICY_MATRIX.extend([
        (_mode, "valid_true", _true_outcome, _true_decision, _true_explanation),
        (_mode, "valid_false", _false_outcome, "APPROVE", "checker_consistent"),
        (_mode, "malformed_json", "ERROR", _error_decision, _error_explanation),
        (_mode, "missing_field", "ERROR", _error_decision, _error_explanation),
        (_mode, "empty", "ERROR", _error_decision, _error_explanation),
        (_mode, "transport_error", "ERROR", _error_decision, _error_explanation),
    ])

_CASE_RAW_CONTENT: dict[str, str | Sequence[str | Exception]] = {
    "valid_true": json.dumps({"result": True}),
    "valid_false": json.dumps({"result": False}),
    "malformed_json": '{"result": tru',
    "missing_field": json.dumps({"verdict": True}),
    "empty": "",
    # Two failures: proves pipeline honours max_retries=1 (not the default 2).
    "transport_error": [ConnectionError("down"), ConnectionError("down")],
}


def _chat_raw_response(content: str) -> SimpleNamespace:
    """Build a chat response whose message content is an exact raw string."""
    return SimpleNamespace(message=SimpleNamespace(content=content))


def _seed_policy_matrix_claim(
    config: AppConfig,
    claim_name: str = "claim policy matrix",
    *,
    booking_name: str = "Ada Lovelace",
    patient_line: str = "Patient: Ada Lovelace",
) -> Path:
    """Seed a medical-certificate claim that always hits the containment LLM.

    Description is intentionally NOT embedded in supporting_document so
    containment goes to the LLM. Default patient line keeps identity
    deterministic (no LLM). Override booking/patient for identity LLM rows.
    """
    claim_dir = _seed_preprocessed_claim(config, claim_name=claim_name)
    artifacts = config.preprocessing.artifacts
    (claim_dir / artifacts.description).write_text(
        "I had to cancel my flight to Paris because of a medical emergency.",
        encoding="utf-8",
    )
    (claim_dir / artifacts.supporting_document).write_text(
        f"# Supporting document\n\n{patient_line}\nMedical certificate attached.\n",
        encoding="utf-8",
    )
    (claim_dir / artifacts.supporting_documents).write_text(
        f"# Supporting documents\n\n**name**: {booking_name}\n",
        encoding="utf-8",
    )
    return claim_dir


def _classifier_responses() -> list[SimpleNamespace]:
    """Coverage → reason → cancel-doc responses for a medical-certificate claim."""
    return [
        _chat_response({
            "labels": [TRIP_CANCELLATION],
            "probabilities": {TRIP_CANCELLATION: 0.9, "False": 0.1},
        }),
        _chat_response({
            "labels": [MEDICAL_EMERGENCY],
            "probabilities": {MEDICAL_EMERGENCY: 0.85, "False": 0.15},
        }),
        _chat_response({
            "labels": [MEDICAL_CERTIFICATE],
            "probabilities": {MEDICAL_CERTIFICATE: 0.8, "False": 0.2},
        }),
    ]


def _append_chat_items(
    responses: list[object],
    raw: str | Exception | Sequence[str | Exception],
) -> None:
    """Append one or more chat responses / raised exceptions to ``responses``."""
    items: Sequence[str | Exception] = raw if isinstance(raw, (list, tuple)) else (raw,)
    for item in items:
        if isinstance(item, Exception):
            responses.append(item)
        else:
            responses.append(_chat_raw_response(item))


def _policy_matrix_chat_side_effect(
    overrides: Mapping[str, str | Exception | Sequence[str | Exception]] | None = None,
    *,
    identity_response: str | Exception | Sequence[str | Exception] | None = None,
) -> list[object]:
    """Build MagicMock side_effect: 3 classifier responses then checker responses.

    Benign defaults cover every boolean mode. ``overrides`` replace per-mode
    content (raw strings) or exception instances. When ``identity_response`` is
    set, it is inserted between contradicts and healthy (identity LLM path).
    """
    resolved: dict[str, str | Exception | Sequence[str | Exception]] = dict(overrides or {})
    responses: list[object] = list(_classifier_responses())
    mode_order = list(_BOOLEAN_CHECKER_MODES)
    if identity_response is not None:
        # Insert identity between contradicts and healthy.
        insert_at = mode_order.index("healthy")
        mode_order.insert(insert_at, "identity")

    for mode in mode_order:
        if mode == "identity":
            assert identity_response is not None
            _append_chat_items(responses, identity_response)
            continue
        raw: str | Exception | Sequence[str | Exception] = resolved.get(mode, _BENIGN_CHECKER_OVERRIDES[mode])
        _append_chat_items(responses, raw)
    return responses


@pytest.mark.parametrize(
    ("mode", "case", "expected_outcome", "expected_decision", "expected_explanation"),
    _POLICY_MATRIX,
    ids=[f"{m}-{c}" for m, c, *_ in _POLICY_MATRIX],
)
def test_checker_policy_matrix(
    tmp_path: Path,
    mode: str,
    case: str,
    expected_outcome: str,
    expected_decision: str,
    expected_explanation: str | None,
) -> None:
    """Mode x parse-case matrix: outcome, decision, explanation, chat call count."""
    ClaimPipeline = _claim_pipeline_cls()
    config = _with_transport_retry(_config(tmp_path), max_retries=1, backoff_seconds=0.0)
    claim_dir = _seed_policy_matrix_claim(config, claim_name=f"claim matrix {mode} {case}")
    overrides: dict[str, str | Exception | Sequence[str | Exception]] = {
        mode: _CASE_RAW_CONTENT[case],
    }
    side_effect = _policy_matrix_chat_side_effect(overrides)
    chat_fn = MagicMock(side_effect=side_effect)
    pipeline = ClaimPipeline(config, chat_fn=chat_fn)

    result_path = pipeline.analyze_claim(claim_dir)
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    predicted = json.loads(
        (
            Path(config.preprocessing.results_dir) / claim_dir.name / config.preprocessing.artifacts.predicted_answer
        ).read_text(encoding="utf-8")
    )

    assert payload["checker_outcomes"][mode] == expected_outcome
    assert payload["decision"] == expected_decision
    assert payload["decision_explanation"] == expected_explanation
    assert predicted["decision"] == expected_decision
    assert predicted["human_in_the_loop"] is (expected_decision == "UNCERTAIN")
    assert chat_fn.call_count == len(side_effect)


@pytest.mark.parametrize(
    (
        "case_id",
        "identity_content",
        "expected_outcome",
        "expected_decision",
        "expected_explanation",
        "legacy_identity_check",
        "legacy_identity_unclear",
    ),
    [
        pytest.param(
            "close_name",
            json.dumps({"name": "Roy Hofman"}),
            "PASS",
            "APPROVE",
            "checker_consistent",
            True,
            False,
            id="close_name",
        ),
        pytest.param(
            "far_name",
            json.dumps({"name": "Someone Completely Different"}),
            "VIOLATION",
            "DENY",
            "identity_check",
            False,
            False,
            id="far_name",
        ),
        pytest.param(
            "null_name",
            json.dumps({"name": None}),
            "ABSTAIN",
            "UNCERTAIN",
            "identity_unclear",
            False,
            True,
            id="null_name",
        ),
        pytest.param(
            "unparseable",
            "not-json-at-all",
            "ERROR",
            "UNCERTAIN",
            "checker_error:identity",
            False,
            True,
            id="unparseable",
        ),
        pytest.param(
            "transport_error",
            [ConnectionError("down"), ConnectionError("down")],
            "ERROR",
            "UNCERTAIN",
            "checker_error:identity",
            False,
            True,
            id="transport_error",
        ),
    ],
)
def test_identity_outcome_policy(
    tmp_path: Path,
    case_id: str,
    identity_content: str | Sequence[str | Exception],
    expected_outcome: str,
    expected_decision: str,
    expected_explanation: str,
    legacy_identity_check: bool,
    legacy_identity_unclear: bool,
) -> None:
    """Identity extraction outcomes fold into decision + legacy booleans (D-02, P-02)."""
    ClaimPipeline = _claim_pipeline_cls()
    config = _with_transport_retry(_config(tmp_path), max_retries=1, backoff_seconds=0.0)
    claim_dir = _seed_policy_matrix_claim(
        config,
        claim_name=f"claim identity {case_id}",
        booking_name="Roy Hoffman",
        patient_line="Patient: Roy Hofman",
    )
    side_effect = _policy_matrix_chat_side_effect({}, identity_response=identity_content)
    chat_fn = MagicMock(side_effect=side_effect)
    pipeline = ClaimPipeline(config, chat_fn=chat_fn)

    result_path = pipeline.analyze_claim(claim_dir)
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    predicted = json.loads(
        (
            Path(config.preprocessing.results_dir) / claim_dir.name / config.preprocessing.artifacts.predicted_answer
        ).read_text(encoding="utf-8")
    )

    assert payload["checker_outcomes"]["identity"] == expected_outcome
    assert payload["identity_check"] is legacy_identity_check
    assert payload["identity_unclear"] is legacy_identity_unclear
    assert payload["decision"] == expected_decision
    assert payload["decision_explanation"] == expected_explanation
    assert predicted["decision"] == expected_decision
    assert predicted["human_in_the_loop"] is (expected_decision == "UNCERTAIN")
    assert chat_fn.call_count == len(side_effect)


@pytest.mark.parametrize(
    ("overrides", "identity_content", "expected_decision", "expected_explanation"),
    [
        pytest.param(
            {"healthy": json.dumps({"result": True}), "contradicts": '{"result": tru'},
            None,
            "DENY",
            "healthy_check",
            id="violation_beats_error",
        ),
        pytest.param(
            {"contradicts": '{"result": tru', "healthy": ""},
            None,
            "UNCERTAIN",
            "checker_error:contradicts,healthy",
            id="two_errors",
        ),
        pytest.param(
            {"contradicts": '{"result": tru'},
            json.dumps({"name": None}),
            "UNCERTAIN",
            "checker_error:contradicts",
            id="error_beats_identity_abstain",
        ),
        pytest.param(
            {"incomplete": ""},
            json.dumps({"name": "Someone Completely Different"}),
            "DENY",
            "identity_check",
            id="identity_violation_beats_incomplete_error",
        ),
    ],
)
def test_checker_outcome_precedence(
    tmp_path: Path,
    overrides: dict[str, str],
    identity_content: str | None,
    expected_decision: str,
    expected_explanation: str,
) -> None:
    """VIOLATION beats ERROR; ERROR beats identity ABSTAIN (D-01 precedence)."""
    ClaimPipeline = _claim_pipeline_cls()
    config = _with_transport_retry(_config(tmp_path), max_retries=1, backoff_seconds=0.0)
    needs_identity_llm = identity_content is not None
    claim_dir = _seed_policy_matrix_claim(
        config,
        claim_name=f"claim precedence {expected_explanation}",
        booking_name="Roy Hoffman" if needs_identity_llm else "Ada Lovelace",
        patient_line="Patient: Roy Hofman" if needs_identity_llm else "Patient: Ada Lovelace",
    )
    side_effect = _policy_matrix_chat_side_effect(
        overrides,
        identity_response=identity_content,
    )
    chat_fn = MagicMock(side_effect=side_effect)
    pipeline = ClaimPipeline(config, chat_fn=chat_fn)

    result_path = pipeline.analyze_claim(claim_dir)
    payload = json.loads(result_path.read_text(encoding="utf-8"))

    assert payload["decision"] == expected_decision
    assert payload["decision_explanation"] == expected_explanation
    assert chat_fn.call_count == len(side_effect)
