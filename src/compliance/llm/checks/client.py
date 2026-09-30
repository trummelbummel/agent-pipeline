"""Shared LLM transport + JSON contracts for composable checks."""

from __future__ import annotations

import logging
from typing import NamedTuple

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from compliance.config.settings import TransportRetryConfig
from compliance.llm.chat import ChatFn, chat_content_with_retry, parse_llm_json_object

logger = logging.getLogger(__name__)


class BooleanCheckResult(BaseModel):
    """LLM JSON contract for boolean checks."""

    model_config = ConfigDict(strict=True)

    result: bool = Field(description="True when the check condition holds")


class ExtractedNameResult(BaseModel):
    """LLM JSON contract for patient / claimant name extraction."""

    model_config = ConfigDict(strict=True)

    name: str | None = Field(description="Extracted person name, or null when no clear name field")


class NameExtraction(NamedTuple):
    """Structured result of extracting a person name from free text.

    :param name: Non-empty extracted name, or None when null/blank/absent.
    :param failed: True when the LLM content was unparseable, failed
        ``ExtractedNameResult`` validation, or transport failed after retries.
    """

    name: str | None
    failed: bool


class LlmCheckClient:
    """One model + chat seam + retry policy shared by every LLM-backed check."""

    def __init__(self, model_name: str, chat_fn: ChatFn, transport_retry: TransportRetryConfig) -> None:
        """Bind the model and transport shared by all checks.

        :param model_name: Ollama model name used for every check call.
        :param chat_fn: Chat callable (``ollama.chat`` or a test seam).
        :param transport_retry: Bounded retry for chat transport failures.
        """
        self._model_name = model_name
        self._chat = chat_fn
        self._transport_retry = transport_retry

    def boolean_result(self, system_prompt: str, user_content: str, *, context: str) -> bool | None:
        """Ask for ``{"result": bool}`` and return the validated boolean.

        :param system_prompt: Check-specific system prompt from config.
        :param user_content: User message carrying the claim / document text.
        :param context: Retry log label (e.g. ``checker contradicts``).
        :return: The parsed boolean, or None on transport failure or
            empty / malformed / schema-invalid content.
        """
        content = self._json_chat(system_prompt, user_content, context=context)
        if content is None:
            return None
        parsed = parse_llm_json_object(content, context="checker")
        if parsed is None:
            return None
        try:
            return BooleanCheckResult.model_validate(parsed).result
        except ValidationError:
            logger.warning("LLM checker JSON missing bool result")
            return None

    def extracted_name(self, system_prompt: str, user_content: str, *, context: str) -> NameExtraction:
        """Ask for ``{"name": "..."}`` / ``{"name": null}`` and return the name.

        :param system_prompt: Name-extraction system prompt from config.
        :param user_content: User message carrying booking or OCR text.
        :param context: Retry log label (e.g. ``checker identity document_patient``).
        :return: ``failed=True`` on transport failure or invalid content;
            otherwise a stripped non-empty name or None (null/blank).
        """
        content = self._json_chat(system_prompt, user_content, context=context)
        if content is None:
            return NameExtraction(name=None, failed=True)
        parsed = parse_llm_json_object(content, context="checker identity name")
        if parsed is None:
            return NameExtraction(name=None, failed=True)
        try:
            name = ExtractedNameResult.model_validate(parsed).name
        except ValidationError:
            logger.warning("LLM identity name JSON invalid")
            return NameExtraction(name=None, failed=True)
        cleaned = name.strip() if name is not None else ""
        return NameExtraction(name=cleaned or None, failed=False)

    def _json_chat(self, system_prompt: str, user_content: str, *, context: str) -> str | None:
        return chat_content_with_retry(
            self._chat,
            self._transport_retry,
            context=context,
            model=self._model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            format="json",
        )
