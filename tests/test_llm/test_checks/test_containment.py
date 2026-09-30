from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from compliance.llm.checks import CheckContext, CheckOutcome
from compliance.llm.checks.boolean import PASS_WHEN_TRUE, BooleanLlmCheck, claim_and_document_message
from compliance.llm.checks.containment import ContainmentCheck

if TYPE_CHECKING:
    from conftest import ChatReturningFactory

    from tests.test_llm.test_checks.conftest import ClientFactory


def _containment(chat: MagicMock, client_factory: ClientFactory) -> ContainmentCheck:
    return ContainmentCheck(
        BooleanLlmCheck(
            "containment",
            client_factory(chat),
            "check containment of claim in text",
            PASS_WHEN_TRUE,
            claim_and_document_message,
        )
    )


def _context(description: str, document: str) -> CheckContext:
    return CheckContext(description=description, document=document, booking="")


def test_containment_deterministic_hit_skips_llm(client_factory: ClientFactory) -> None:
    chat = MagicMock()

    result = _containment(chat, client_factory).run(
        _context("  Flight  AB-123  ", "Passenger boarded flight ab-123 on time.")
    )

    assert result == CheckOutcome.PASS
    chat.assert_not_called()


def test_containment_llm_fallback_true(
    chat_returning_factory: ChatReturningFactory,
    client_factory: ClientFactory,
) -> None:
    chat = chat_returning_factory({"result": True})

    result = _containment(chat, client_factory).run(
        _context("the passenger was hospitalized", "Booking confirmation for flight XY9.")
    )

    assert result == CheckOutcome.PASS
    chat.assert_called_once()
    call_kwargs = chat.call_args.kwargs
    assert call_kwargs["model"] == "test-model"
    assert call_kwargs["format"] == "json"
    assert "check containment" in call_kwargs["messages"][0]["content"]


def test_containment_llm_fallback_false_is_abstain(
    chat_returning_factory: ChatReturningFactory,
    client_factory: ClientFactory,
) -> None:
    """Containment result false is recorded ABSTAIN; it never drives DENY (P-01)."""
    chat = chat_returning_factory({"result": False})

    result = _containment(chat, client_factory).run(
        _context("the passenger was hospitalized", "Booking confirmation for flight XY9.")
    )

    assert result == CheckOutcome.ABSTAIN
    chat.assert_called_once()


def test_containment_unparseable_llm_response_returns_error(
    chat_returning_factory: ChatReturningFactory,
    client_factory: ClientFactory,
) -> None:
    chat = chat_returning_factory("")

    result = _containment(chat, client_factory).run(_context("something not in text", "unrelated reference"))

    assert result == CheckOutcome.ERROR
    chat.assert_called_once()
