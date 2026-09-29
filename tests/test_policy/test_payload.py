from __future__ import annotations

from compliance.config.settings import AnalysisConfig
from compliance.llm.checker import CheckOutcome
from compliance.models.decisions import DECISION_APPROVE
from compliance.policy.coverage import RoutedCoverage
from compliance.policy.payload import analysis_result_payload
from compliance.policy.state import ClaimAnalysisState


def test_payload_key_order_and_conditional_omission(analysis_config: AnalysisConfig) -> None:
    """Payload carries documented key order and omits absent conditional keys."""
    state: ClaimAnalysisState = {
        "claim_id": "claim-x",
        "run_id": "run-1",
        "coverage_labels": ["1"],
        "coverage_probabilities": {"1": 0.9},
        "routed_coverage": RoutedCoverage(branch="cancellation", label="1"),
        "reason_labels": ["2"],
        "document_labels": ["1"],
        "document_has_signature": True,
        "signature_check": True,
        "identity_check": True,
        "identity_unclear": False,
        "checker_containment": True,
        "checker_contradicts": False,
        "healthy_check": False,
        "checker_document_not_authentic": False,
        "checker_incomplete_document": False,
        "checker_outcomes": {
            "containment": CheckOutcome.PASS,
            "contradicts": CheckOutcome.PASS,
            "identity": CheckOutcome.PASS,
        },
        "checker_rule_set": "cancellation_medical",
        "checker_skipped": [],
        "human_in_the_loop": False,
    }
    payload = analysis_result_payload(
        state,
        analysis=analysis_config,
        ocr_failure_reason=None,
        metadata_run_id="meta-run",
    )
    keys = list(payload)
    assert keys[:5] == [
        "claim_id",
        "coverage_labels",
        "coverage_label_codes",
        "routed_coverage_label",
        "routed_coverage_label_code",
    ]
    assert payload["decision"] == DECISION_APPROVE
    assert payload["decision_explanation"] == "checker_consistent"
    assert payload["document_metadata_run_id"] == "meta-run"
    assert payload["checker_rule_set"] == "cancellation_medical"
    assert "checker_outcomes" in payload


def test_payload_omits_conditional_keys_when_absent(analysis_config: AnalysisConfig) -> None:
    """Coverage-only path omits checker_outcomes / rule_set / skipped / missing-doc."""
    state: ClaimAnalysisState = {
        "claim_id": "claim-x",
        "run_id": "run-1",
        "coverage_labels": ["False"],
        "coverage_probabilities": {"False": 0.9},
        "routed_coverage": RoutedCoverage(branch="abstention", label="False"),
        "human_in_the_loop": False,
    }
    payload = analysis_result_payload(
        state,
        analysis=analysis_config,
        ocr_failure_reason=None,
        metadata_run_id=None,
    )
    assert "checker_outcomes" not in payload
    assert "checker_rule_set" not in payload
    assert "checker_skipped" not in payload
    assert "checker_missing_documentation" not in payload
    assert "document_metadata_run_id" not in payload
    assert payload["decision_explanation"] == "coverage_false_label"
