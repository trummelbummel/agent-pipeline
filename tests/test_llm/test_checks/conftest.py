from __future__ import annotations

from collections.abc import Callable
from unittest.mock import MagicMock

import pytest

from compliance.config.settings import TransportRetryConfig
from compliance.llm.checks.client import LlmCheckClient

ClientFactory = Callable[..., LlmCheckClient]


@pytest.fixture
def client_factory() -> ClientFactory:
    """Build an ``LlmCheckClient`` over a chat mock with no retry backoff."""

    def _build(chat: MagicMock, *, max_retries: int = 2) -> LlmCheckClient:
        return LlmCheckClient(
            "test-model",
            chat,
            TransportRetryConfig(max_retries=max_retries, backoff_seconds=0.0),
        )

    return _build
