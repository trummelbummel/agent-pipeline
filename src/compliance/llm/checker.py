from __future__ import annotations

import json
import logging
import re
import unicodedata
from typing import Literal

import ollama

from compliance.llm.chat import ChatFn, response_content

logger = logging.getLogger(__name__)


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
        :raises ValueError: When ``mode`` is not a supported checker mode.
        """
        if mode == "containment":
            return self._containment_result(claim, text)
        if mode == "contradicts":
            return self._llm_boolean_result(self.contradicts_prompt, claim, text)
        raise ValueError(f"Unsupported checker mode: {mode!r}")

    def _containment_result(self, claim: str, text: str) -> bool:
        normalized_claim = self._normalized_text(claim)
        if normalized_claim and normalized_claim in self._normalized_text(text):
            return True
        return self._llm_boolean_result(self.containment_prompt, claim, text)

    def _llm_boolean_result(self, prompt: str, claim: str, text: str) -> bool:
        response = self._chat(
            model=self.model_name,
            messages=self._check_messages(prompt, claim, text),
            format="json",
        )
        return self._parse_boolean_result(response_content(response))

    @staticmethod
    def _check_messages(prompt: str, claim: str, text: str) -> list[dict[str, str]]:
        return [
            {"role": "system", "content": prompt},
            {
                "role": "user",
                "content": f"Claim:\n{claim}\n\nText:\n{text}",
            },
        ]

    @staticmethod
    def _parse_boolean_result(content: str) -> bool:
        content = content.strip()
        if not content:
            logger.warning("Empty LLM checker response")
            return False
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            logger.warning("Failed to parse LLM checker JSON")
            return False
        if not isinstance(parsed, dict):
            logger.warning("LLM checker JSON was not an object")
            return False
        result = parsed.get("result")
        if not isinstance(result, bool):
            logger.warning("LLM checker JSON missing bool result")
            return False
        return result

    @staticmethod
    def _normalized_text(value: str) -> str:
        collapsed = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value).casefold())
        return collapsed.strip()
