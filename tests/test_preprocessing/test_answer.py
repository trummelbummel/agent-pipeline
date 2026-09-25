from __future__ import annotations

from pathlib import Path

import pytest

from compliance.models.claim import is_nan_scalar
from compliance.preprocessing.answer import AnswerReader


def test_answer_minimal(tmp_path: Path) -> None:
    path = tmp_path / "answer.json"
    path.write_text('{"decision": "APPROVE"}', encoding="utf-8")

    result = AnswerReader().read(path)

    assert result.decision == "APPROVE"
    assert is_nan_scalar(result.explanation)
    assert is_nan_scalar(result.acceptable_decision)


def test_answer_standard(tmp_path: Path) -> None:
    path = tmp_path / "answer.json"
    path.write_text(
        '{"decision": "DENY", "explanation": "medical document missing"}',
        encoding="utf-8",
    )

    result = AnswerReader().read(path)

    assert result.decision == "DENY"
    assert result.explanation == "medical document missing"
    assert is_nan_scalar(result.acceptable_decision)


def test_answer_uncertain(tmp_path: Path) -> None:
    path = tmp_path / "answer.json"
    path.write_text(
        '{"decision": "UNCERTAIN", "explanation": "unclear", "acceptable_decision": "DENY"}',
        encoding="utf-8",
    )

    result = AnswerReader().read(path)

    assert result.decision == "UNCERTAIN"
    assert result.explanation == "unclear"
    assert result.acceptable_decision == "DENY"


def test_answer_real_claim_10() -> None:
    path = Path("data/raw/claim 10/answer.json")
    if not path.is_file():
        pytest.skip("sample claim 10 not present")

    result = AnswerReader().read(path)

    assert result.decision == "DENY"
    assert isinstance(result.explanation, str)
    assert is_nan_scalar(result.acceptable_decision)
