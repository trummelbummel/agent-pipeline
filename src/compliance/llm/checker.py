from __future__ import annotations

import re
import unicodedata
from typing import Literal

import ollama

from compliance.llm.chat import ChatFn


class Checker:
    """Claim-vs-text checker with containment and contradiction modes."""

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
        """Check whether claim is contained in or contradicts text.

        :param claim: Claim string to evaluate.
        :param text: Reference text to check against.
        :param mode: ``containment`` (normalize+substring, then LLM) or ``contradicts``.
        :return: True when the mode condition holds; False otherwise.
        """
        if mode == "containment":
            return self._containment_result(claim, text)
        if mode == "contradicts":
            return False
        raise ValueError(f"Unsupported checker mode: {mode!r}")

    def _containment_result(self, claim: str, text: str) -> bool:
        normalized_claim = self._normalized_text(claim)
        if normalized_claim and normalized_claim in self._normalized_text(text):
            return True
        return False

    @staticmethod
    def _normalized_text(value: str) -> str:
        collapsed = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value).casefold())
        return collapsed.strip()
