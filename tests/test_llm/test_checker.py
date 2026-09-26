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
        identity_prompt="check whether claimant name matches document",
        healthy_prompt="check whether document says patient is healthy",
        authenticity_prompt="check authenticity of supporting document",
        incomplete_prompt="check whether medical fields are incomplete",
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


def test_checker_identity_false_when_name_obscured() -> None:
    chat = _chat_returning({"result": "mismatch"})
    checker = _make_checker(chat)

    result = checker.check(
        claim="# Supporting documents\n\n**name**: Roy Hoffman\n",
        text="Patient: R\n*19.12.1945\n",
        mode="identity",
    )

    assert result is False
    chat.assert_called_once()
    call_kwargs = chat.call_args.kwargs
    user = call_kwargs["messages"][1]["content"]
    assert "Booking / internal" in user
    assert "Roy Hoffman" in user
    assert "Patient: R" in user


def test_checker_identity_deterministic_containment_skips_llm() -> None:
    """Lowercase name containment in OCR → match without calling the LLM."""
    chat = MagicMock()
    checker = _make_checker(chat)

    status = checker.check_identity(
        "# Supporting documents\n\n**name**: Amy Ndiaye\n",
        "Je soussigné certifie que Mme Amy NDIAYE, née le 21/12/1981 "
        "est hospitalisée depuis le 01/12/2022.\n",
    )

    assert status == "match"
    chat.assert_not_called()


def test_checker_identity_deterministic_token_containment_handles_glue_and_order() -> None:
    """All booking-name tokens in OCR (glued / reordered) → match, skip LLM."""
    chat = MagicMock()
    checker = _make_checker(chat)

    # Claim-3 style: patient name glued to the next word; doctor name first.
    status = checker.check_identity(
        "**name**: Kacou Meitiale Evelyne\n",
        "docteur KOUASSI KONE FRANCOIS que l'état de santé de "
        "Mme KACOU MEITIALE EVELYNEnécessite unehospitalisation\n",
    )
    assert status == "match"
    chat.assert_not_called()

    # Claim-9 style: token reorder (Daisy vs DAYSI still needs LLM — Daysi typo).
    # Exact token reorder with matching spelling skips LLM.
    status = checker.check_identity(
        "**name**: Bastidas Angulo Daisy Mariuxi\n",
        "paciente BASTIDAS ANGULO DAISY MARIUXI cédula\n",
    )
    assert status == "match"
    chat.assert_not_called()


def test_checker_identity_falls_back_to_llm_when_not_contained() -> None:
    chat = _chat_returning({"result": "mismatch"})
    checker = _make_checker(chat)

    status = checker.check_identity(
        "**name**: Olivier Bayante\n",
        "31. X. 20u\nSignature\nuv\n",
    )

    assert status == "mismatch"
    chat.assert_called_once()


def test_checker_identity_true_when_names_match() -> None:
    """Spelling variants still use the LLM (Piccirilly vs PICCIRILLI)."""
    chat = _chat_returning({"result": "match"})
    checker = _make_checker(chat)

    result = checker.check(
        claim="# Supporting documents\n\n**name**: Piccirilly Francesca\n",
        text="Patient: PICCIRILLI FRANCESCA\n",
        mode="identity",
    )

    assert result is True
    chat.assert_called_once()


def test_checker_identity_unclear_when_no_patient_field() -> None:
    chat = _chat_returning({"result": "unclear"})
    checker = _make_checker(chat)

    status = checker.check_identity(
        "# Supporting documents\n\n**name**: Olivier Bayante\n",
        "Dr. Rossi\nAmbulatorio\n",
    )

    assert status == "unclear"
    assert checker.check(
        claim="# Supporting documents\n\n**name**: Olivier Bayante\n",
        text="Dr. Rossi\nAmbulatorio\n",
        mode="identity",
    ) is False


def test_checker_identity_accepts_legacy_bool_result() -> None:
    chat = _chat_returning({"result": True})
    checker = _make_checker(chat)

    # Spelling differs enough that containment misses → LLM legacy bool True.
    assert (
        checker.check_identity(
            "**name**: Ada Lovelace\n",
            "Patient: Augusta Ada King\n",
        )
        == "match"
    )
    chat.assert_called_once()


def test_checker_identity_exact_containment_skips_llm_for_ada() -> None:
    chat = MagicMock()
    checker = _make_checker(chat)

    assert (
        checker.check_identity(
            "**name**: Ada Lovelace\n",
            "Patient: Ada Lovelace\n",
        )
        == "match"
    )
    chat.assert_not_called()


def test_checker_healthy_true_when_document_says_healthy() -> None:
    chat = _chat_returning({"result": True})
    checker = _make_checker(chat)

    result = checker.check(
        claim="",
        text="En el momento se encuentra CLÍNICAMENTE SANA\nAPTO PARA ACTIVIDAD FÍSICA: SI\n",
        mode="healthy",
    )

    assert result is True
    chat.assert_called_once()
    user = chat.call_args.kwargs["messages"][1]["content"]
    assert "CLÍNICAMENTE SANA" in user
    assert "Supporting document" in user


def test_checker_healthy_false_when_illness_documented() -> None:
    chat = _chat_returning({"result": False})
    checker = _make_checker(chat)

    result = checker.check(
        claim="",
        text="Patient hospitalized for acute appendicitis.\n",
        mode="healthy",
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


# --- Phase 07 authenticity (R027) + incomplete (R028) ---


def test_checker_not_authentic_true_when_ocr_format_suspect() -> None:
    """mode=not_authentic: True = authenticity violation (OCR/format path, no Benford).

    Message layout mirrors healthy: claim may be empty; user content is OCR-focused
    (Supporting document + text).
    """
    chat = _chat_returning({"result": True})
    checker = _make_checker(chat)

    result = checker.check(
        claim="",
        text="# Hospital admission\n\nPatient admitted; garbled OCR ###@@\n",
        mode="not_authentic",
    )

    assert result is True
    chat.assert_called_once()
    user = chat.call_args.kwargs["messages"][1]["content"]
    assert "Supporting document" in user
    assert "garbled OCR" in user


def test_checker_not_authentic_false_on_llm_false() -> None:
    """mode=not_authentic: LLM {"result": false} → False (document looks authentic)."""
    chat = _chat_returning({"result": False})
    checker = _make_checker(chat)

    result = checker.check(
        claim="",
        text="# Medical certificate\n\nSigned hospital letterhead with diagnosis.\n",
        mode="not_authentic",
    )

    assert result is False
    chat.assert_called_once()


def test_checker_not_authentic_parse_failure_fail_closed_true() -> None:
    """Deny-on-True mode: malformed JSON / missing result → fail-closed True."""
    chat = _chat_returning("")
    checker = _make_checker(chat)

    result = checker.check(
        claim="",
        text="some OCR text",
        mode="not_authentic",
    )

    assert result is True
    chat.assert_called_once()


def test_checker_incomplete_true_when_required_medical_fields_missing() -> None:
    """mode=incomplete: True when discharge/diagnosis/condition fields are absent."""
    chat = _chat_returning({"result": True})
    checker = _make_checker(chat)

    result = checker.check(
        claim="",
        text="# CERTIFICADO MÉDICO\n\nPatient name only. No diagnosis.\n",
        mode="incomplete",
    )

    assert result is True
    chat.assert_called_once()
    user = chat.call_args.kwargs["messages"][1]["content"]
    assert "Supporting document" in user
    assert "No diagnosis" in user


def test_checker_incomplete_parse_failure_fail_closed_true() -> None:
    """Deny-on-True mode: missing result key → fail-closed True (unlike containment)."""
    chat = _chat_returning({"other": True})
    checker = _make_checker(chat)

    result = checker.check(
        claim="",
        text="some OCR text",
        mode="incomplete",
    )

    assert result is True
    chat.assert_called_once()
