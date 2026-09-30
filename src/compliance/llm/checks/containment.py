"""Containment check: deterministic substring hit, else LLM entailment."""

from __future__ import annotations

from compliance.llm.checks.base import CheckContext, CheckerMode, CheckOutcome, normalized_text
from compliance.llm.checks.boolean import BooleanLlmCheck


class ContainmentCheck:
    """Claim narrative contained in / entailed by the supporting document."""

    name: CheckerMode = "containment"

    def __init__(self, fallback: BooleanLlmCheck) -> None:
        """Bind the LLM check used when the deterministic match misses.

        :param fallback: Containment LLM check (PASS on true, ABSTAIN on false).
        """
        self._fallback = fallback

    def run(self, context: CheckContext) -> CheckOutcome:
        """PASS on a normalized substring hit without an LLM call, else ask the LLM.

        :param context: Claim texts.
        :return: Containment outcome per the policy matrix.
        """
        claim = normalized_text(context.description)
        if claim and claim in normalized_text(context.document):
            return CheckOutcome.PASS
        return self._fallback.run(context)
