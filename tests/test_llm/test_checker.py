from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

from compliance.llm.checker import Checker

if TYPE_CHECKING:
    from conftest import ChatReturningFactory


def _make_checker(chat: MagicMock, *, identity_max_edit_distance: int = 3) -> Checker:
    return Checker(
        model_name="test-model",
        containment_prompt="check containment of claim in text",
        contradicts_prompt="check whether claim contradicts text",
        identity_prompt="extract person name as JSON",
        healthy_prompt="check whether document says patient is healthy",
        authenticity_prompt="check authenticity of supporting document",
        incomplete_prompt="check whether medical fields are incomplete",
        chat_fn=chat,
        identity_max_edit_distance=identity_max_edit_distance,
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


def test_checker_containment_llm_fallback_true(
    chat_returning_factory: ChatReturningFactory,
) -> None:
    chat = chat_returning_factory({"result": True})
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


def test_checker_containment_llm_fallback_false(
    chat_returning_factory: ChatReturningFactory,
) -> None:
    chat = chat_returning_factory({"result": False})
    checker = _make_checker(chat)

    result = checker.check(
        claim="the passenger was hospitalized",
        text="Booking confirmation for flight XY9.",
        mode="containment",
    )

    assert result is False
    chat.assert_called_once()


def test_checker_contradicts_true_when_claim_conflicts(
    chat_returning_factory: ChatReturningFactory,
) -> None:
    chat = chat_returning_factory({"result": True})
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


def test_checker_contradicts_false_when_supported(
    chat_returning_factory: ChatReturningFactory,
) -> None:
    chat = chat_returning_factory({"result": False})
    checker = _make_checker(chat)

    result = checker.check(
        claim="The flight departed on time",
        text="The flight departed on time.",
        mode="contradicts",
    )

    assert result is False
    chat.assert_called_once()


def test_checker_identity_false_when_name_obscured(
    chat_returning_factory: ChatReturningFactory,
) -> None:
    """Extracted initial vs full booking name → edit distance fails → mismatch."""
    chat = chat_returning_factory({"name": "R"})
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
    assert "patient / subject" in user.lower() or "Patient: R" in user
    assert "Patient: R" in user


def test_checker_identity_deterministic_containment_skips_llm() -> None:
    """Lowercase name containment in OCR → match without calling the LLM."""
    chat = MagicMock()
    checker = _make_checker(chat)

    status = checker.check_identity(
        "# Supporting documents\n\n**name**: Amy Ndiaye\n",
        "Je soussigné certifie que Mme Amy NDIAYE, née le 21/12/1981 est hospitalisée depuis le 01/12/2022.\n",
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
        "docteur KOUASSI KONE FRANCOIS que l'état de santé de Mme KACOU MEITIALE EVELYNEnécessite unehospitalisation\n",
    )
    assert status == "match"
    chat.assert_not_called()

    # Exact token reorder with matching spelling skips LLM.
    status = checker.check_identity(
        "**name**: Bastidas Angulo Daisy Mariuxi\n",
        "paciente BASTIDAS ANGULO DAISY MARIUXI cédula\n",
    )
    assert status == "match"
    chat.assert_not_called()


def test_checker_identity_partner_note_skips_containment_requester_false_pass(
    chat_returning_factory: ChatReturningFactory,
) -> None:
    """Booking ``(partner)`` name in OCR as requester must not short-circuit match.

    Claim-6 shape: partner tokens appear under 'a solicitud del…' while the
    patient is a different person → extract + edit-distance → mismatch.
    """
    chat = chat_returning_factory({"name": "VELOSA RUIZ JORGE LUIS"})
    checker = _make_checker(chat)

    status = checker.check_identity(
        "**name**: Marta Isabel Rojas Valbuena (partner)\n",
        "el paciente VELOSA RUIZ JORGE LUIS identificado con C.C 19.092.121, "
        "se encuentra hospitalizado. La presente se expide a solicitud del "
        "Señora ROJAS VALBUENA MARTA ISABEL Identificada con C.C. 41.541.380.\n",
    )

    assert status == "mismatch"
    chat.assert_called_once()
    user = chat.call_args.kwargs["messages"][1]["content"]
    assert "solicitud" in user.lower() or "patient" in user.lower()


def test_checker_identity_extract_null_when_not_contained(
    chat_returning_factory: ChatReturningFactory,
) -> None:
    """No patient name in OCR → extraction null → unclear."""
    chat = chat_returning_factory({"name": None})
    checker = _make_checker(chat)

    status = checker.check_identity(
        "**name**: Olivier Bayante\n",
        "31. X. 20u\nSignature\nuv\n",
    )

    assert status == "unclear"
    chat.assert_called_once()


def test_checker_identity_true_when_edit_distance_within_threshold(
    chat_returning_factory: ChatReturningFactory,
) -> None:
    """OCR spelling variant within edit distance (Piccirilly vs PICCIRILLI)."""
    chat = chat_returning_factory({"name": "PICCIRILLI FRANCESCA"})
    checker = _make_checker(chat)

    result = checker.check(
        claim="# Supporting documents\n\n**name**: Piccirilly Francesca\n",
        text="Patient: PICCIRILLI FRANCESCA\n",
        mode="identity",
    )

    assert result is True
    chat.assert_called_once()


def test_checker_identity_mismatch_when_edit_distance_above_threshold(
    chat_returning_factory: ChatReturningFactory,
) -> None:
    """Different person names → distance above threshold → mismatch."""
    chat = chat_returning_factory({"name": "Maria Rossi"})
    checker = _make_checker(chat, identity_max_edit_distance=3)

    status = checker.check_identity(
        "**name**: Roy Hoffman\n",
        "Patient: Maria Rossi\n",
    )

    assert status == "mismatch"
    chat.assert_called_once()


def test_checker_identity_unclear_when_no_patient_field(
    chat_returning_factory: ChatReturningFactory,
) -> None:
    chat = chat_returning_factory({"name": None})
    checker = _make_checker(chat)

    status = checker.check_identity(
        "# Supporting documents\n\n**name**: Olivier Bayante\n",
        "Dr. Rossi\nAmbulatorio\n",
    )

    assert status == "unclear"
    assert (
        checker.check(
            claim="# Supporting documents\n\n**name**: Olivier Bayante\n",
            text="Dr. Rossi\nAmbulatorio\n",
            mode="identity",
        )
        is False
    )


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


def test_checker_healthy_true_when_document_says_healthy(
    chat_returning_factory: ChatReturningFactory,
) -> None:
    chat = chat_returning_factory({"result": True})
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


def test_checker_healthy_false_when_illness_documented(
    chat_returning_factory: ChatReturningFactory,
) -> None:
    chat = chat_returning_factory({"result": False})
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


def test_checker_unparseable_llm_response_returns_false(
    chat_returning_factory: ChatReturningFactory,
) -> None:
    chat = chat_returning_factory("")
    checker = _make_checker(chat)

    result = checker.check(
        claim="something not in text",
        text="unrelated reference",
        mode="containment",
    )

    assert result is False
    chat.assert_called_once()


# --- Phase 07 authenticity (R027) + incomplete (R028) ---


def test_checker_not_authentic_true_when_ocr_format_suspect(
    chat_returning_factory: ChatReturningFactory,
) -> None:
    """mode=not_authentic: True = authenticity violation (OCR/format path, no Benford).

    Message layout mirrors healthy: claim may be empty; user content is OCR-focused
    (Supporting document + text).
    """
    chat = chat_returning_factory({"result": True})
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


def test_checker_not_authentic_false_on_llm_false(
    chat_returning_factory: ChatReturningFactory,
) -> None:
    """mode=not_authentic: LLM {"result": false} → False (document looks authentic)."""
    chat = chat_returning_factory({"result": False})
    checker = _make_checker(chat)

    result = checker.check(
        claim="",
        text="# Medical certificate\n\nSigned hospital letterhead with diagnosis.\n",
        mode="not_authentic",
    )

    assert result is False
    chat.assert_called_once()


def test_checker_not_authentic_parse_failure_fail_closed_true(
    chat_returning_factory: ChatReturningFactory,
) -> None:
    """Deny-on-True mode: malformed JSON / missing result → fail-closed True."""
    chat = chat_returning_factory("")
    checker = _make_checker(chat)

    result = checker.check(
        claim="",
        text="some OCR text",
        mode="not_authentic",
    )

    assert result is True
    chat.assert_called_once()


def test_checker_incomplete_true_when_required_medical_fields_missing(
    chat_returning_factory: ChatReturningFactory,
) -> None:
    """mode=incomplete: True when discharge/diagnosis/condition fields are absent."""
    chat = chat_returning_factory({"result": True})
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


def test_checker_incomplete_parse_failure_fail_closed_true(
    chat_returning_factory: ChatReturningFactory,
) -> None:
    """Deny-on-True mode: missing result key → fail-closed True (unlike containment)."""
    chat = chat_returning_factory({"other": True})
    checker = _make_checker(chat)

    result = checker.check(
        claim="",
        text="some OCR text",
        mode="incomplete",
    )

    assert result is True
    chat.assert_called_once()
