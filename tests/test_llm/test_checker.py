from __future__ import annotations

from unittest.mock import MagicMock

from compliance.llm.checker import Checker


def test_checker_containment_deterministic_hit_skips_llm() -> None:
    chat = MagicMock()
    checker = Checker(
        model_name="test-model",
        containment_prompt="check containment",
        contradicts_prompt="check contradicts",
        chat_fn=chat,
    )

    result = checker.check(
        claim="  Flight  AB-123  ",
        text="Passenger boarded flight ab-123 on time.",
        mode="containment",
    )

    assert result is True
    chat.assert_not_called()
