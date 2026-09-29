from __future__ import annotations

from compliance.llm.checker import CheckOutcome
from compliance.policy.checks import checker_state_updates, legacy_booleans_from_outcomes
from compliance.policy.rules import CheckerRuleSet


def test_legacy_booleans_containment_and_contradicts() -> None:
    """Containment PASS and contradicts VIOLATION map to legacy booleans."""
    flags = legacy_booleans_from_outcomes({
        "containment": CheckOutcome.PASS,
        "contradicts": CheckOutcome.VIOLATION,
    })
    assert flags["checker_containment"] is True
    assert flags["checker_contradicts"] is True
    assert flags["identity_check"] is True
    assert flags["identity_unclear"] is False


def test_legacy_booleans_identity_outcomes() -> None:
    """Identity PASS / ABSTAIN / VIOLATION map to identity_check and unclear."""
    assert legacy_booleans_from_outcomes({"identity": CheckOutcome.PASS}) == {
        "identity_check": True,
        "identity_unclear": False,
    }
    unclear = legacy_booleans_from_outcomes({"identity": CheckOutcome.ABSTAIN})
    assert unclear["identity_check"] is False
    assert unclear["identity_unclear"] is True
    violation = legacy_booleans_from_outcomes({"identity": CheckOutcome.VIOLATION})
    assert violation["identity_check"] is False
    assert violation["identity_unclear"] is False


def test_legacy_booleans_medical_modes() -> None:
    """Healthy / not_authentic / incomplete VIOLATION map to legacy keys."""
    flags = legacy_booleans_from_outcomes({
        "healthy": CheckOutcome.VIOLATION,
        "not_authentic": CheckOutcome.VIOLATION,
        "incomplete": CheckOutcome.VIOLATION,
    })
    assert flags["healthy_check"] is True
    assert flags["checker_document_not_authentic"] is True
    assert flags["checker_incomplete_document"] is True


def test_checker_state_updates_omits_skipped_signature_key() -> None:
    """A skipped signature check omits signature_check rather than recording false."""
    rule_set = CheckerRuleSet(name="personal_effects_non_medical", applicable=frozenset())
    from compliance.policy.checks import CheckerRunResult

    results = CheckerRunResult(
        departure_within_days=False,
        suspicious_dating=False,
        outcomes={"containment": CheckOutcome.PASS, "contradicts": CheckOutcome.PASS},
        legacy_booleans=legacy_booleans_from_outcomes({
            "containment": CheckOutcome.PASS,
            "contradicts": CheckOutcome.PASS,
        }),
    )
    payload = checker_state_updates(rule_set, results, document_has_signature=False)
    assert "signature_check" not in payload
    assert "departure_within_days" not in payload
    assert payload["checker_rule_set"] == "personal_effects_non_medical"
    assert "identity" in payload["checker_skipped"]


def test_checker_state_updates_records_applicable_signature() -> None:
    """An applicable signature check records the preprocess signature flag."""
    rule_set = CheckerRuleSet(
        name="cancellation_medical",
        applicable=frozenset({"signature", "departure"}),
    )
    from compliance.policy.checks import CheckerRunResult

    results = CheckerRunResult(
        departure_within_days=False,
        suspicious_dating=False,
        outcomes={},
        legacy_booleans={},
    )
    payload = checker_state_updates(rule_set, results, document_has_signature=True)
    assert payload["signature_check"] is True
    assert payload["departure_within_days"] is False
