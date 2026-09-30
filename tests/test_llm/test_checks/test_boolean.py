from __future__ import annotations

import json
from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import httpx
import ollama
import pytest

from compliance.llm.checks import CheckContext, CheckOutcome
from compliance.llm.checks.boolean import (
    VIOLATION_WHEN_TRUE,
    BooleanLlmCheck,
    claim_and_document_message,
    document_only_message,
)

if TYPE_CHECKING:
    from conftest import ChatReturningFactory

    from tests.test_llm.test_checks.conftest import ClientFactory


def _contradicts(chat: MagicMock, client_factory: ClientFactory, *, max_retries: int = 2) -> BooleanLlmCheck:
    return BooleanLlmCheck(
        "contradicts",
        client_factory(chat, max_retries=max_retries),
        "check whether claim contradicts text",
        VIOLATION_WHEN_TRUE,
        claim_and_document_message,
    )


def _document_check(chat: MagicMock, client_factory: ClientFactory, *, name: str) -> BooleanLlmCheck:
    return BooleanLlmCheck(
        name,  # type: ignore[arg-type]
        client_factory(chat),
        f"check {name} medical document",
        VIOLATION_WHEN_TRUE,
        document_only_message,
    )


_CONFLICT = CheckContext(description="The flight was cancelled", document="The flight departed on time.", booking="")


def test_contradicts_true_when_claim_conflicts(
    chat_returning_factory: ChatReturningFactory,
    client_factory: ClientFactory,
) -> None:
    chat = chat_returning_factory({"result": True})

    result = _contradicts(chat, client_factory).run(_CONFLICT)

    assert result == CheckOutcome.VIOLATION
    chat.assert_called_once()
    call_kwargs = chat.call_args.kwargs
    assert call_kwargs["format"] == "json"
    assert "contradicts" in call_kwargs["messages"][0]["content"]


def test_contradicts_false_when_supported(
    chat_returning_factory: ChatReturningFactory,
    client_factory: ClientFactory,
) -> None:
    chat = chat_returning_factory({"result": False})

    result = _contradicts(chat, client_factory).run(
        CheckContext(description="The flight departed on time", document="The flight departed on time.", booking="")
    )

    assert result == CheckOutcome.PASS
    chat.assert_called_once()


def test_healthy_true_when_document_says_healthy(
    chat_returning_factory: ChatReturningFactory,
    client_factory: ClientFactory,
) -> None:
    chat = chat_returning_factory({"result": True})

    result = _document_check(chat, client_factory, name="healthy").run(
        CheckContext(
            description="",
            document="En el momento se encuentra CLÍNICAMENTE SANA\nAPTO PARA ACTIVIDAD FÍSICA: SI\n",
            booking="",
        )
    )

    assert result == CheckOutcome.VIOLATION
    chat.assert_called_once()
    user = chat.call_args.kwargs["messages"][1]["content"]
    assert "CLÍNICAMENTE SANA" in user
    assert "Supporting document" in user


def test_healthy_false_when_illness_documented(
    chat_returning_factory: ChatReturningFactory,
    client_factory: ClientFactory,
) -> None:
    chat = chat_returning_factory({"result": False})

    result = _document_check(chat, client_factory, name="healthy").run(
        CheckContext(description="", document="Patient hospitalized for acute appendicitis.\n", booking="")
    )

    assert result == CheckOutcome.PASS
    chat.assert_called_once()


def test_incomplete_true_when_required_medical_fields_missing(
    chat_returning_factory: ChatReturningFactory,
    client_factory: ClientFactory,
) -> None:
    """True when discharge/diagnosis/condition fields are absent."""
    chat = chat_returning_factory({"result": True})

    result = _document_check(chat, client_factory, name="incomplete").run(
        CheckContext(description="", document="# CERTIFICADO MÉDICO\n\nPatient name only. No diagnosis.\n", booking="")
    )

    assert result == CheckOutcome.VIOLATION
    chat.assert_called_once()
    user = chat.call_args.kwargs["messages"][1]["content"]
    assert "Supporting document" in user
    assert "No diagnosis" in user


def test_incomplete_parse_failure_returns_error(
    chat_returning_factory: ChatReturningFactory,
    client_factory: ClientFactory,
) -> None:
    """Missing result key -> ERROR (D-01; no longer fail-closed True)."""
    chat = chat_returning_factory({"other": True})

    result = _document_check(chat, client_factory, name="incomplete").run(
        CheckContext(description="", document="some OCR text", booking="")
    )

    assert result == CheckOutcome.ERROR
    chat.assert_called_once()


@pytest.mark.parametrize(
    "exc",
    [
        pytest.param(ConnectionError("down"), id="connection_error"),
        pytest.param(httpx.ConnectTimeout("timeout"), id="connect_timeout"),
        pytest.param(ollama.ResponseError("unavailable", status_code=503), id="response_error_503"),
    ],
)
@pytest.mark.parametrize("max_retries", [0, 2])
def test_transport_retry_count_honoured(exc: Exception, max_retries: int, client_factory: ClientFactory) -> None:
    """Transport failures retry max_retries times then return ERROR (D-03)."""
    chat = MagicMock(side_effect=[exc] * (max_retries + 1))

    result = _contradicts(chat, client_factory, max_retries=max_retries).run(_CONFLICT)

    assert result == CheckOutcome.ERROR
    assert chat.call_count == max_retries + 1


def test_transport_recovers_after_transient_failure(client_factory: ClientFactory) -> None:
    """One ConnectionError then valid True → VIOLATION after exactly 2 calls."""
    chat = MagicMock(
        side_effect=[
            ConnectionError("transient"),
            SimpleNamespace(message=SimpleNamespace(content=json.dumps({"result": True}))),
        ]
    )

    result = _contradicts(chat, client_factory).run(_CONFLICT)

    assert result == CheckOutcome.VIOLATION
    assert chat.call_count == 2
