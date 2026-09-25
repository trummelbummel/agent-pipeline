from __future__ import annotations

from typing import Any, Callable

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
