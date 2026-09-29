from __future__ import annotations

from compliance.config.settings import RequiredDocumentsConfig
from compliance.policy.rules import rule_set_for_claim


def test_rule_set_non_cancellation_branches_skip_all_gated() -> None:
    """PE and missed-departure branches are non-medical with empty applicable."""
    required = RequiredDocumentsConfig()
    for branch in ("personal_effects", "missed_departure", "abstention"):
        rule_set = rule_set_for_claim(
            branch=branch,  # type: ignore[arg-type]
            classified_codes={"1"},
            required_documents=required,
        )
        assert rule_set.name == f"{branch}_non_medical"
        assert rule_set.applicable == frozenset()
        assert set(rule_set.skipped) == {
            "identity",
            "signature",
            "healthy",
            "not_authentic",
            "incomplete",
            "suspicious_dating",
            "departure",
        }


def test_rule_set_cancellation_identity_group_only() -> None:
    """Identity-group medical code enables only the identity gated check."""
    required = RequiredDocumentsConfig(
        identity_required_codes=["1"],
        signature_required_codes=["4"],
    )
    rule_set = rule_set_for_claim(
        branch="cancellation",
        classified_codes={"1"},
        required_documents=required,
    )
    assert rule_set.name == "cancellation_medical"
    assert rule_set.applicable == frozenset({"identity"})
    assert "identity" not in rule_set.skipped
    assert set(rule_set.skipped) == {
        "signature",
        "healthy",
        "not_authentic",
        "incomplete",
        "suspicious_dating",
        "departure",
    }


def test_rule_set_cancellation_signature_group_only() -> None:
    """Signature-group medical code enables the six signature-group checks."""
    required = RequiredDocumentsConfig(
        identity_required_codes=["1"],
        signature_required_codes=["4"],
    )
    rule_set = rule_set_for_claim(
        branch="cancellation",
        classified_codes={"4"},
        required_documents=required,
    )
    assert rule_set.name == "cancellation_medical"
    assert rule_set.applicable == frozenset({
        "signature",
        "healthy",
        "not_authentic",
        "incomplete",
        "suspicious_dating",
        "departure",
    })
    assert rule_set.skipped == ("identity",)


def test_rule_set_cancellation_both_groups() -> None:
    """Both identity and signature codes enable all seven gated checks."""
    required = RequiredDocumentsConfig(
        identity_required_codes=["1"],
        signature_required_codes=["4"],
    )
    rule_set = rule_set_for_claim(
        branch="cancellation",
        classified_codes={"1", "4"},
        required_documents=required,
    )
    assert rule_set.name == "cancellation_medical"
    assert len(rule_set.applicable) == 7
    assert rule_set.skipped == ()


def test_rule_set_cancellation_non_medical_code() -> None:
    """Police/jury codes with empty group intersection yield non-medical."""
    required = RequiredDocumentsConfig(
        identity_required_codes=["1"],
        signature_required_codes=["4"],
    )
    rule_set = rule_set_for_claim(
        branch="cancellation",
        classified_codes={"2"},
        required_documents=required,
    )
    assert rule_set.name == "cancellation_non_medical"
    assert rule_set.applicable == frozenset()
