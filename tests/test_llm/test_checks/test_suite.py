from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

from compliance.config.settings import CheckingConfig, TransportRetryConfig
from compliance.llm.checks import CheckContext, CheckOutcome, CheckSuite


def _checking() -> CheckingConfig:
    return CheckingConfig(
        model="suite-model",
        containment_prompt="containment prompt",
        contradicts_prompt="contradicts prompt",
        identity_prompt="identity prompt",
        healthy_prompt="healthy prompt",
        incomplete_prompt="incomplete prompt",
        transport_retry=TransportRetryConfig(max_retries=0, backoff_seconds=0.0),
    )


def _responses(*payloads: dict[str, object]) -> MagicMock:
    return MagicMock(
        side_effect=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(p))) for p in payloads],
    )


def test_suite_runs_selected_checks_in_fixed_order() -> None:
    """Selection order is ignored: containment → contradicts → healthy → incomplete; identity unselected."""
    chat = _responses({"result": False}, {"result": True}, {"result": False}, {"result": True})
    suite = CheckSuite.from_config(_checking(), chat)

    outcomes = suite.run(
        ["incomplete", "healthy", "contradicts", "containment"],
        CheckContext(description="claim text", document="unrelated document", booking="**name**: Ada Lovelace\n"),
    )

    assert list(outcomes) == ["containment", "contradicts", "healthy", "incomplete"]
    assert outcomes == {
        "containment": CheckOutcome.ABSTAIN,
        "contradicts": CheckOutcome.VIOLATION,
        "healthy": CheckOutcome.PASS,
        "incomplete": CheckOutcome.VIOLATION,
    }
    system_prompts = [call.kwargs["messages"][0]["content"] for call in chat.call_args_list]
    assert system_prompts == ["containment prompt", "contradicts prompt", "healthy prompt", "incomplete prompt"]
    assert {call.kwargs["model"] for call in chat.call_args_list} == {"suite-model"}


def test_suite_identity_uses_configured_edit_distance() -> None:
    """``identity_max_edit_distance`` from config reaches the identity check."""
    context = CheckContext(description="", document="Patient: Roy Hofman\n", booking="**name**: Roy Hoffmann\n")
    strict = _checking().model_copy(update={"identity_max_edit_distance": 0})

    lenient_outcome = CheckSuite.from_config(_checking(), _responses({"name": "Roy Hofman"})).run(["identity"], context)
    strict_outcome = CheckSuite.from_config(strict, _responses({"name": "Roy Hofman"})).run(["identity"], context)

    assert lenient_outcome == {"identity": CheckOutcome.PASS}
    assert strict_outcome == {"identity": CheckOutcome.VIOLATION}
