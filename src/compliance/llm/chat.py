from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from typing import Any

import httpx
import ollama

from compliance.config.settings import TransportRetryConfig

logger = logging.getLogger(__name__)

ChatFn = Callable[..., Any]

# ollama maps connect failures to the builtin ConnectionError and lets httpx
# timeouts and read errors through; ResponseError covers server HTTP errors.
TRANSPORT_ERRORS: tuple[type[Exception], ...] = (
    ConnectionError,
    TimeoutError,
    httpx.TransportError,
    ollama.ResponseError,
)


def response_content(response: Any) -> str:
    """Pull message content from an ollama-style chat response.

    :param response: Chat response object or mapping.
    :return: Message content string.
    """
    if hasattr(response, "message"):
        message = response.message
        return str(getattr(message, "content", "") or "")
    if isinstance(response, dict):
        message = response.get("message", {})
        if isinstance(message, dict):
            return str(message.get("content", "") or "")
    return str(response or "")


def parse_llm_json_object(content: str, *, context: str) -> dict[str, Any] | None:
    """Parse LLM text as a JSON object, or None when empty/invalid.

    :param content: Raw model message content.
    :param context: Short label for WARNING logs (e.g. ``checker``, ``classification``).
    :return: Parsed object dict, or None on failure.
    """
    content = content.strip()
    if not content:
        logger.warning("Empty LLM %s response", context)
        return None
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        logger.warning("Failed to parse LLM %s JSON", context)
        return None
    if not isinstance(parsed, dict):
        logger.warning("LLM %s JSON was not an object", context)
        return None
    return parsed


def chat_content_with_retry(
    chat_fn: ChatFn,
    retry: TransportRetryConfig,
    *,
    context: str,
    **chat_kwargs: Any,
) -> str | None:
    """Call ``chat_fn`` with bounded transport retry and exponential backoff.

    Makes up to ``retry.max_retries + 1`` attempts. On success returns
    ``response_content(...)``. Catches only ``TRANSPORT_ERRORS``; other
    exceptions propagate. After the final transport failure returns ``None``.

    :param chat_fn: Chat callable (typically ``ollama.chat`` or a test seam).
    :param retry: Max retries and base backoff seconds.
    :param context: Short label for WARNING logs (never logs kwargs or content).
    :param chat_kwargs: Forwarded to ``chat_fn`` (model, messages, format, ...).
    :return: Message content string, or ``None`` when all attempts fail.
    """
    total_attempts = retry.max_retries + 1
    for attempt in range(total_attempts):
        try:
            response = chat_fn(**chat_kwargs)
        except TRANSPORT_ERRORS as exc:
            logger.warning(
                "LLM transport error context=%s attempt=%s/%s error_type=%s",
                context,
                attempt + 1,
                total_attempts,
                type(exc).__name__,
            )
            if attempt + 1 >= total_attempts:
                return None
            time.sleep(retry.backoff_seconds * (2**attempt))
            continue
        else:
            return response_content(response)
    return None
