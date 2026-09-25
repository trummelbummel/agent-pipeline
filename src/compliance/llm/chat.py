from __future__ import annotations

import json
import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)

ChatFn = Callable[..., Any]


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
