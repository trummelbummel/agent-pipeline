from __future__ import annotations

from typing import Literal

import ollama

from compliance.llm.chat import ChatFn


class Checker:
    """Claim-vs-text checker with containment and contradiction modes (stub)."""

    def __init__(
        self,
        model_name: str,
        containment_prompt: str,
        contradicts_prompt: str,
        chat_fn: ChatFn | None = None,
    ) -> None:
        """Bind model, prompts, and optional chat seam.

        :param model_name: LLM model name from config.
        :param containment_prompt: System prompt for containment mode.
        :param contradicts_prompt: System prompt for contradicts mode.
        :param chat_fn: Optional chat callable for tests; defaults to ollama.chat.
        """
        self.model_name = model_name
        self.containment_prompt = containment_prompt
        self.contradicts_prompt = contradicts_prompt
        self._chat: ChatFn = chat_fn or ollama.chat

    def check(
        self,
        claim: str,
        text: str,
        mode: Literal["containment", "contradicts"],
    ) -> bool:
        """Check whether claim is contained in or contradicts text (stub).

        :param claim: Claim string to evaluate.
        :param text: Reference text to check against.
        :param mode: ``containment`` or ``contradicts``.
        :return: Always False in the RED stub.
        """
        return False
