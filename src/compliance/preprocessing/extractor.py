from __future__ import annotations

import json
import logging
from typing import Any

import ollama
from pydantic import BaseModel

from compliance.llm.chat import ChatFn, response_content
from compliance.models.claim import _MISSING

logger = logging.getLogger(__name__)


class InformationExtractor:
    """Extract structured fields from free text into a Pydantic model via LLM."""

    def __init__(
        self,
        target_model: type[BaseModel],
        model_name: str,
        prompt: str,
        chat_fn: ChatFn | None = None,
    ) -> None:
        """Create an extractor bound to a schema, model, and prompt.

        :param target_model: Pydantic model class to populate.
        :param model_name: LLM model name from config (never hardcoded).
        :param prompt: Extraction instruction prompt from config.
        :param chat_fn: Optional chat callable for tests; defaults to ollama.chat.
        """
        self.target_model = target_model
        self.model_name = model_name
        self.prompt = prompt
        self._chat: ChatFn = chat_fn or ollama.chat

    def extract(self, text: str) -> BaseModel:
        """Call the LLM and parse the response into ``target_model``.

        Missing or null fields become np.nan.

        :param text: Free-text input (e.g. description.txt contents).
        :return: Validated instance of ``target_model``.
        """
        schema = self.target_model.model_json_schema()
        response = self._chat(
            model=self.model_name,
            messages=[
                {"role": "system", "content": self.prompt},
                {
                    "role": "user",
                    "content": (
                        "Extract fields matching this JSON schema:\n"
                        f"{json.dumps(schema)}\n\n"
                        f"Text:\n{text}"
                    ),
                },
            ],
            format="json",
        )
        content = response_content(response)
        raw = self._parse_json(content)
        filled = self._fill_missing(raw)
        return self.target_model.model_validate(filled)

    @staticmethod
    def _parse_json(content: str) -> dict[str, Any]:
        """Parse LLM JSON content into a dict.

        :param content: Raw model output expected to be JSON.
        :return: Parsed object, or empty dict on failure.
        """
        content = content.strip()
        if not content:
            logger.warning("Empty LLM extraction response")
            return {}
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            logger.warning("Failed to parse LLM extraction JSON")
            return {}
        if not isinstance(parsed, dict):
            logger.warning("LLM extraction JSON was not an object")
            return {}
        return parsed

    def _fill_missing(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Ensure every model field is present; null/absent → np.nan.

        :param raw: Parsed LLM field dict.
        :return: Dict suitable for ``target_model.model_validate``.
        """
        filled: dict[str, Any] = {}
        for name in self.target_model.model_fields:
            if name not in raw or raw[name] is None:
                filled[name] = _MISSING
            else:
                filled[name] = raw[name]
        return filled
