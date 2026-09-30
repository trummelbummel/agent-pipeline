"""LLM boolean checks (contradicts, healthy, incomplete, containment fallback)."""

from __future__ import annotations

from collections.abc import Callable
from typing import NamedTuple

from compliance.llm.checks.base import CheckContext, CheckerMode, CheckOutcome
from compliance.llm.checks.client import LlmCheckClient

MessageBuilder = Callable[[CheckContext], str]


class Polarity(NamedTuple):
    """Outcome for each value of the LLM boolean result.

    :param when_true: Outcome when the LLM answers ``{"result": true}``.
    :param when_false: Outcome when the LLM answers ``{"result": false}``.
    """

    when_true: CheckOutcome
    when_false: CheckOutcome


VIOLATION_WHEN_TRUE = Polarity(CheckOutcome.VIOLATION, CheckOutcome.PASS)
PASS_WHEN_TRUE = Polarity(CheckOutcome.PASS, CheckOutcome.ABSTAIN)


def claim_and_document_message(context: CheckContext) -> str:
    """User message pairing the claim narrative with the document text.

    :param context: Claim texts.
    :return: User content for claim-vs-document checks.
    """
    return f"Claim:\n{context.description}\n\nText:\n{context.document}"


def document_only_message(context: CheckContext) -> str:
    """User message carrying only the supporting-document OCR.

    :param context: Claim texts.
    :return: User content for document-only medical checks.
    """
    return f"Supporting document (OCR):\n{context.document}"


class BooleanLlmCheck:
    """A check answered by one ``{"result": bool}`` LLM call."""

    def __init__(
        self,
        name: CheckerMode,
        client: LlmCheckClient,
        prompt: str,
        polarity: Polarity,
        message: MessageBuilder,
    ) -> None:
        """Bind the check's prompt, polarity, and user-message shape.

        :param name: Mode key recorded in ``checker_outcomes``.
        :param client: Shared LLM client.
        :param prompt: Check-specific system prompt from config.
        :param polarity: Outcome for a true / false LLM result.
        :param message: Builds the user message from the claim texts.
        """
        self.name = name
        self._client = client
        self._prompt = prompt
        self._polarity = polarity
        self._message = message

    def run(self, context: CheckContext) -> CheckOutcome:
        """Ask the LLM and resolve the boolean through this check's polarity.

        :param context: Claim texts.
        :return: ERROR when no valid boolean came back; else the polarity outcome.
        """
        result = self._client.boolean_result(self._prompt, self._message(context), context=f"checker {self.name}")
        if result is None:
            return CheckOutcome.ERROR
        return self._polarity.when_true if result else self._polarity.when_false
