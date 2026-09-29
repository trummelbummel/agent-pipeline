"""Per-coverage medical rule matrix (SR-010).

Pure: branch + classified document codes + required-document config in;
``CheckerRuleSet`` out. No filesystem and no LLM.
"""

from __future__ import annotations

from typing import Literal, NamedTuple

from compliance.config.settings import RequiredDocumentsConfig
from compliance.policy.coverage import CoverageBranch

GatedCheck = Literal[
    "identity",
    "signature",
    "healthy",
    "incomplete",
    "suspicious_dating",
    "departure",
]

# Checks whose semantics are specific to a medical document (rule matrix D-01).
_GATED_CHECKS: tuple[GatedCheck, ...] = (
    "identity",
    "signature",
    "healthy",
    "incomplete",
    "suspicious_dating",
    "departure",
)

# Code-group → gated checks they enable on the cancellation branch (P-03).
# Producer pairs each entry with the matching RequiredDocumentsConfig list.
_IDENTITY_GROUP_CHECKS: frozenset[GatedCheck] = frozenset({"identity"})
_SIGNATURE_GROUP_CHECKS: frozenset[GatedCheck] = frozenset({
    "signature",
    "healthy",
    "incomplete",
    "suspicious_dating",
    "departure",
})
_RULE_SET_CODE_GROUPS: tuple[frozenset[GatedCheck], ...] = (
    _IDENTITY_GROUP_CHECKS,
    _SIGNATURE_GROUP_CHECKS,
)

__all__ = [
    "CheckerRuleSet",
    "GatedCheck",
    "rule_set_for_claim",
]


class CheckerRuleSet(NamedTuple):
    """Per-claim set of medical checks that apply (SR-010).

    Rule matrix (routed path → applicable gated checks):

    - ``cancellation_medical`` — all six when classified codes hit the
      configured identity/signature required-document lists
    - ``cancellation_non_medical`` — none (police report, jury summons, …)
    - ``missed_departure_medical`` — all six when classified codes hit
      ``missed_departure_medical_codes`` (medical / hospital evidence on a
      missed-departure claim)
    - ``missed_departure_non_medical`` — none (incident report, booking proof)
    - ``personal_effects_non_medical`` — none

    Ungated always: missing_documentation, containment, contradicts.

    :param name: Rule-set identifier written to ``checker_rule_set``.
    :param applicable: Gated checks that run and record a result.
    """

    name: str
    applicable: frozenset[GatedCheck]

    @property
    def skipped(self) -> tuple[GatedCheck, ...]:
        """Gated checks absent from ``applicable``, in canonical order.

        :return: ``_GATED_CHECKS`` members not in ``applicable``.
        """
        return tuple(check for check in _GATED_CHECKS if check not in self.applicable)


def rule_set_for_claim(
    *,
    branch: CoverageBranch,
    classified_codes: set[str],
    required_documents: RequiredDocumentsConfig,
) -> CheckerRuleSet:
    """Compute the single per-claim medical rule set from branch + document codes.

    ``missed_departure`` enables every gated medical check only when a classified
    document code is in ``missed_departure_medical_codes``; otherwise it is
    ``missed_departure_non_medical``. ``personal_effects`` and ``abstention``
    yield an empty applicable set named ``{branch}_non_medical``. On
    cancellation, each configured code group (identity / signature required
    codes) enables its gated checks when any classified document code
    intersects that group; the set is named ``cancellation_medical`` when
    anything applies, else ``cancellation_non_medical``.

    :param branch: Routed coverage branch for this claim.
    :param classified_codes: Non-abstention document codes from the document stage.
    :param required_documents: Config pairing identity/signature/missed-medical
        code lists with gated-check groups.
    :return: Named rule set deciding which gated checks run.
    """
    if branch == "missed_departure":
        medical_codes = set(required_documents.missed_departure_medical_codes)
        if medical_codes and classified_codes & medical_codes:
            return CheckerRuleSet(name="missed_departure_medical", applicable=frozenset(_GATED_CHECKS))
        return CheckerRuleSet(name="missed_departure_non_medical", applicable=frozenset())

    if branch != "cancellation":
        return CheckerRuleSet(name=f"{branch}_non_medical", applicable=frozenset())

    code_lists = (
        required_documents.identity_required_codes,
        required_documents.signature_required_codes,
    )
    applicable: set[GatedCheck] = set()
    for codes, checks in zip(code_lists, _RULE_SET_CODE_GROUPS, strict=True):
        if codes and classified_codes & set(codes):
            applicable |= checks
    name = "cancellation_medical" if applicable else "cancellation_non_medical"
    return CheckerRuleSet(name=name, applicable=frozenset(applicable))
