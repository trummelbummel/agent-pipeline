from __future__ import annotations

import json
from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

from compliance.llm.checks import CheckContext, CheckOutcome
from compliance.llm.checks.identity import IdentityCheck

if TYPE_CHECKING:
    from conftest import ChatReturningFactory

    from tests.test_llm.test_checks.conftest import ClientFactory


def _identity(chat: MagicMock, client_factory: ClientFactory, *, max_edit_distance: int = 3) -> IdentityCheck:
    return IdentityCheck(client_factory(chat), "extract person name as JSON", max_edit_distance)


def _context(booking: str, document: str) -> CheckContext:
    return CheckContext(description="", document=document, booking=booking)


def test_identity_violation_when_name_obscured(
    chat_returning_factory: ChatReturningFactory,
    client_factory: ClientFactory,
) -> None:
    """Extracted initial vs full booking name -> edit distance fails -> VIOLATION."""
    chat = chat_returning_factory({"name": "R"})

    result = _identity(chat, client_factory).run(
        _context("# Supporting documents\n\n**name**: Roy Hoffman\n", "Patient: R\n*19.12.1945\n")
    )

    assert result == CheckOutcome.VIOLATION
    chat.assert_called_once()
    user = chat.call_args.kwargs["messages"][1]["content"]
    assert "patient / subject" in user.lower()
    assert "Patient: R" in user


def test_identity_deterministic_containment_skips_llm(client_factory: ClientFactory) -> None:
    """Lowercase name containment in OCR -> PASS without calling the LLM."""
    chat = MagicMock()

    result = _identity(chat, client_factory).run(
        _context(
            "# Supporting documents\n\n**name**: Amy Ndiaye\n",
            "Je soussigné certifie que Mme Amy NDIAYE, née le 21/12/1981 est hospitalisée depuis le 01/12/2022.\n",
        )
    )

    assert result == CheckOutcome.PASS
    chat.assert_not_called()


def test_identity_deterministic_token_containment_handles_glue_and_order(client_factory: ClientFactory) -> None:
    """All booking-name tokens in OCR (glued / reordered) -> PASS, skip LLM."""
    chat = MagicMock()
    check = _identity(chat, client_factory)

    # Claim-3 style: patient name glued to the next word; doctor name first.
    assert (
        check.run(
            _context(
                "**name**: Kacou Meitiale Evelyne\n",
                "docteur KOUASSI KONE FRANCOIS que l'état de santé de Mme KACOU MEITIALE "
                "EVELYNEnécessite unehospitalisation\n",
            )
        )
        == CheckOutcome.PASS
    )
    assert (
        check.run(
            _context("**name**: Bastidas Angulo Daisy Mariuxi\n", "paciente BASTIDAS ANGULO DAISY MARIUXI cédula\n")
        )
        == CheckOutcome.PASS
    )
    chat.assert_not_called()


def test_identity_partner_note_skips_containment_requester_false_pass(
    chat_returning_factory: ChatReturningFactory,
    client_factory: ClientFactory,
) -> None:
    """Booking ``(partner)`` name in OCR as requester must not short-circuit match.

    Claim-6 shape: partner tokens appear under 'a solicitud del…' while the
    patient is a different person -> extract + edit-distance -> VIOLATION.
    """
    chat = chat_returning_factory({"name": "VELOSA RUIZ JORGE LUIS"})

    result = _identity(chat, client_factory).run(
        _context(
            "**name**: Marta Isabel Rojas Valbuena (partner)\n",
            "el paciente VELOSA RUIZ JORGE LUIS identificado con C.C 19.092.121, "
            "se encuentra hospitalizado. La presente se expide a solicitud del "
            "Señora ROJAS VALBUENA MARTA ISABEL Identificada con C.C. 41.541.380.\n",
        )
    )

    assert result == CheckOutcome.VIOLATION
    chat.assert_called_once()
    assert "solicitud" in chat.call_args.kwargs["messages"][1]["content"].lower()


@pytest.mark.parametrize(
    "document",
    [
        pytest.param("31. X. 20u\nSignature\nuv\n", id="illegible_ocr"),
        pytest.param("Dr. Rossi\nAmbulatorio\n", id="doctor_only"),
    ],
)
def test_identity_violation_when_no_patient_name(
    document: str,
    chat_returning_factory: ChatReturningFactory,
    client_factory: ClientFactory,
) -> None:
    """Redacted / missing patient field -> extraction null -> VIOLATION (unverifiable → DENY)."""
    chat = chat_returning_factory({"name": None})

    result = _identity(chat, client_factory).run(_context("**name**: Olivier Bayante\n", document))

    assert result == CheckOutcome.VIOLATION
    chat.assert_called_once()


def test_identity_pass_when_edit_distance_within_threshold(
    chat_returning_factory: ChatReturningFactory,
    client_factory: ClientFactory,
) -> None:
    """OCR spelling variant within edit distance (Piccirilly vs PICCIRILLI)."""
    chat = chat_returning_factory({"name": "PICCIRILLI FRANCESCA"})

    result = _identity(chat, client_factory).run(
        _context("# Supporting documents\n\n**name**: Piccirilly Francesca\n", "Patient: PICCIRILLI FRANCESCA\n")
    )

    assert result == CheckOutcome.PASS
    chat.assert_called_once()


def test_identity_violation_when_edit_distance_above_threshold(
    chat_returning_factory: ChatReturningFactory,
    client_factory: ClientFactory,
) -> None:
    """Different person names -> distance above threshold -> VIOLATION."""
    chat = chat_returning_factory({"name": "Maria Rossi"})

    result = _identity(chat, client_factory, max_edit_distance=3).run(
        _context("**name**: Roy Hoffman\n", "Patient: Maria Rossi\n")
    )

    assert result == CheckOutcome.VIOLATION
    chat.assert_called_once()


@pytest.mark.parametrize(
    ("document_payload", "expected"),
    [
        pytest.param({"name": 7}, CheckOutcome.ERROR, id="schema_invalid_name_type"),
        pytest.param({"name": "   "}, CheckOutcome.VIOLATION, id="blank_name"),
    ],
)
def test_identity_extraction_outcomes_document_side(
    document_payload: dict[str, object],
    expected: CheckOutcome,
    client_factory: ClientFactory,
) -> None:
    """Document-side extraction: schema-invalid name type -> ERROR; blank -> VIOLATION."""
    chat = MagicMock(return_value=SimpleNamespace(message=SimpleNamespace(content=json.dumps(document_payload))))

    result = _identity(chat, client_factory).run(
        _context("**name**: Roy Hoffman\n", "unrelated OCR text with no name field\n")
    )

    assert result == expected
    chat.assert_called_once()


def test_identity_unparseable_booking_extraction_gives_error(client_factory: ClientFactory) -> None:
    """Unparseable booking-name extraction (no markdown field) -> ERROR; both extractions still run."""
    chat = MagicMock(
        side_effect=[
            SimpleNamespace(message=SimpleNamespace(content="not json")),
            SimpleNamespace(message=SimpleNamespace(content=json.dumps({"name": "Someone"}))),
        ]
    )

    result = _identity(chat, client_factory).run(_context("no name field here at all\n", "Patient: Someone\n"))

    assert result == CheckOutcome.ERROR
    assert chat.call_count == 2


def test_identity_transport_error_is_error(client_factory: ClientFactory) -> None:
    """Document extraction that always raises ConnectionError → ERROR after retries."""
    chat = MagicMock(side_effect=[ConnectionError("down")] * 3)

    result = _identity(chat, client_factory).run(
        _context("**name**: Roy Hoffman\n", "unrelated OCR text with no name field\n")
    )

    assert result == CheckOutcome.ERROR
    assert chat.call_count == 3
