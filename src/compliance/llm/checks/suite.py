"""Ordered composition of claim checks built once from ``CheckingConfig``."""

from __future__ import annotations

from collections.abc import Collection, Sequence

from compliance.config.settings import CheckingConfig
from compliance.llm.chat import ChatFn
from compliance.llm.checks.base import Check, CheckContext, CheckerMode, CheckOutcome
from compliance.llm.checks.boolean import (
    PASS_WHEN_TRUE,
    VIOLATION_WHEN_TRUE,
    BooleanLlmCheck,
    claim_and_document_message,
    document_only_message,
)
from compliance.llm.checks.client import LlmCheckClient
from compliance.llm.checks.containment import ContainmentCheck
from compliance.llm.checks.identity import IdentityCheck


class CheckSuite:
    """Checks in fixed execution order; runs the subset a claim selects."""

    def __init__(self, checks: Sequence[Check]) -> None:
        """Bind checks in the order they must execute.

        :param checks: Checks in execution order (chat call order depends on it).
        """
        self._checks = tuple(checks)

    @classmethod
    def from_config(cls, checking: CheckingConfig, chat_fn: ChatFn) -> CheckSuite:
        """Build every check once, sharing one LLM client.

        Order: containment → contradicts → identity → healthy → incomplete.

        :param checking: Checking config (model, prompts, thresholds, retry).
        :param chat_fn: Chat callable shared by every LLM-backed check.
        :return: Suite ready to run for any claim.
        """
        client = LlmCheckClient(checking.model, chat_fn, checking.transport_retry)
        return cls([
            ContainmentCheck(
                BooleanLlmCheck(
                    "containment",
                    client,
                    checking.containment_prompt,
                    PASS_WHEN_TRUE,
                    claim_and_document_message,
                )
            ),
            BooleanLlmCheck(
                "contradicts",
                client,
                checking.contradicts_prompt,
                VIOLATION_WHEN_TRUE,
                claim_and_document_message,
            ),
            IdentityCheck(client, checking.identity_prompt, checking.identity_max_edit_distance),
            BooleanLlmCheck("healthy", client, checking.healthy_prompt, VIOLATION_WHEN_TRUE, document_only_message),
            BooleanLlmCheck(
                "incomplete",
                client,
                checking.incomplete_prompt,
                VIOLATION_WHEN_TRUE,
                document_only_message,
            ),
        ])

    def run(self, modes: Collection[CheckerMode], context: CheckContext) -> dict[CheckerMode, CheckOutcome]:
        """Run the selected checks in suite order.

        :param modes: Check names to run for this claim.
        :param context: Claim texts.
        :return: Outcome for every check that ran, in execution order.
        """
        return {check.name: check.run(context) for check in self._checks if check.name in modes}
