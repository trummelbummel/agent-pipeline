from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from compliance.llm.checker import Checker


def _chat_returning(payload: dict[str, Any] | str) -> MagicMock:
    content = payload if isinstance(payload, str) else json.dumps(payload)
    response = SimpleNamespace(message=SimpleNamespace(content=content))
    return MagicMock(return_value=response)


def _make_checker(chat: MagicMock) -> Checker:
    return Checker(
        model_name="test-model",
        containment_prompt="check containment of claim in text",
        contradicts_prompt="check whether claim contradicts text",
        chat_fn=chat,
    )


def test_checker_containment_deterministic_hit_skips_llm() -> None:
    chat = MagicMock()
    checker = _make_checker(chat)

    result = checker.check(
        claim="  Flight  AB-123  ",
        text="Passenger boarded flight ab-123 on time.",
        mode="containment",
    )

    assert result is True
    chat.assert_not_called()


def test_checker_containment_llm_fallback_true() -> None:
    chat = _chat_returning({"result": True})
    checker = _make_checker(chat)

    result = checker.check(
        claim="the passenger was hospitalized",
        text="Booking confirmation for flight XY9.",
        mode="containment",
    )

    assert result is True
    chat.assert_called_once()
    call_kwargs = chat.call_args.kwargs
    assert call_kwargs["model"] == "test-model"
    assert call_kwargs["format"] == "json"
    assert "check containment" in call_kwargs["messages"][0]["content"]


def test_checker_containment_llm_fallback_false() -> None:
    chat = _chat_returning({"result": False})
    checker = _make_checker(chat)

    result = checker.check(
        claim="the passenger was hospitalized",
        text="Booking confirmation for flight XY9.",
        mode="containment",
    )

    assert result is False
    chat.assert_called_once()


def test_checker_contradicts_true_when_claim_conflicts() -> None:
    chat = _chat_returning({"result": True})
    checker = _make_checker(chat)

    result = checker.check(
        claim="The flight was cancelled",
        text="The flight departed on time.",
        mode="contradicts",
    )

    assert result is True
    chat.assert_called_once()
    call_kwargs = chat.call_args.kwargs
    assert call_kwargs["format"] == "json"
    assert "contradicts" in call_kwargs["messages"][0]["content"]


def test_checker_contradicts_false_when_supported() -> None:
    chat = _chat_returning({"result": False})
    checker = _make_checker(chat)

    result = checker.check(
        claim="The flight departed on time",
        text="The flight departed on time.",
        mode="contradicts",
    )

    assert result is False
    chat.assert_called_once()


def test_checker_invalid_mode_raises() -> None:
    checker = _make_checker(MagicMock())
    with pytest.raises(ValueError):
        checker.check("claim", "text", mode="unsupported")  # type: ignore[arg-type]


def test_checker_unparseable_llm_response_returns_false() -> None:
    chat = _chat_returning("")
    checker = _make_checker(chat)

    result = checker.check(
        claim="something not in text",
        text="unrelated reference",
        mode="containment",
    )

    assert result is False
    chat.assert_called_once()
