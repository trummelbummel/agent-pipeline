"""Identity check: booking passenger vs patient name on the medical OCR."""

from __future__ import annotations

import re

from compliance.llm.checks.base import CheckContext, CheckerMode, CheckOutcome, normalized_text
from compliance.llm.checks.client import LlmCheckClient, NameExtraction

_BOOKING_NAME_FIELD = re.compile(r"(?im)^\s*(?:\*\*)?name(?:\*\*)?\s*:\s*(.+?)\s*$")
# Booking name notes like ``(partner)`` mean the passenger is not the patient —
# containment against requester text in OCR would false-pass identity.
_BOOKING_ROLE_NOTE = re.compile(
    r"(?i)\(\s*(partner|spouse|wife|husband|child|son|daughter|"
    r"mother|father|parent|friend|relative)\s*\)"
)
_PARENTHETICAL = re.compile(r"\([^)]*\)")

_BOOKING_USER_PREFIX = "Extract the passenger / claimant name from this booking or internal record text:\n"
_DOCUMENT_USER_PREFIX = (
    "Extract the patient / subject / insured name from this medical "
    "supporting-document OCR. Prefer names next to patient / paciente / "
    "subject markers. Ignore doctor, facility, letterhead, signature-block, "
    "and requester / applicant / 'solicitud del' / 'a solicitud de' names "
    "(those are not the patient):\n"
)


class IdentityCheck:
    """Booking passenger must be the patient named on the medical document."""

    name: CheckerMode = "identity"

    def __init__(self, client: LlmCheckClient, prompt: str, max_edit_distance: int) -> None:
        """Bind the extraction prompt and name-match threshold.

        :param client: Shared LLM client used for name extraction.
        :param prompt: System prompt extracting ``{"name": ...}`` as JSON.
        :param max_edit_distance: Inclusive lowercased Levenshtein threshold
            for a name match after extraction.
        """
        self._client = client
        self._prompt = prompt
        self._max_edit_distance = max_edit_distance

    def run(self, context: CheckContext) -> CheckOutcome:
        """Compare the booking name to the patient/subject name on the OCR.

        Order:
        1. Deterministic containment of the booking ``**name**`` field in OCR
           (skipped when the name carries a role note such as ``(partner)``)
           -> PASS, no LLM call.
        2. Booking name: the markdown field when present, else an LLM
           extraction. Document name: always an LLM extraction (booking first).
        3. Either extraction failed -> ERROR; either name missing -> VIOLATION;
           within ``max_edit_distance`` -> PASS, else VIOLATION.

        :param context: Claim texts (``booking`` and ``document`` are read).
        :return: Identity outcome per the policy matrix.
        """
        booking_name = _booking_name(context.booking)
        if (
            booking_name
            and _BOOKING_ROLE_NOTE.search(booking_name) is None
            and _name_contained(booking_name, context.document)
        ):
            return CheckOutcome.PASS
        booking = (
            NameExtraction(name=booking_name, failed=False)
            if booking_name
            else self._extract(_BOOKING_USER_PREFIX + context.booking, role="booking_claimant")
        )
        document = self._extract(_DOCUMENT_USER_PREFIX + context.document, role="document_patient")
        return self._identity_outcome(booking, document)

    def _extract(self, user_content: str, *, role: str) -> NameExtraction:
        return self._client.extracted_name(self._prompt, user_content, context=f"checker identity {role}")

    def _identity_outcome(self, booking: NameExtraction, document: NameExtraction) -> CheckOutcome:
        if booking.failed or document.failed:
            return CheckOutcome.ERROR
        if not booking.name or not document.name:
            return CheckOutcome.VIOLATION
        if _names_within_edit_distance(booking.name, document.name, max_distance=self._max_edit_distance):
            return CheckOutcome.PASS
        return CheckOutcome.VIOLATION


def _booking_name(booking_text: str) -> str | None:
    """Extract the passenger ``name`` field from booking markdown.

    :param booking_text: ``supporting_documents.md`` body.
    :return: Raw name string, or None when the field is absent or blank.
    """
    match = _BOOKING_NAME_FIELD.search(booking_text)
    if match is None:
        return None
    return match.group(1).strip() or None


def _name_tokens(name: str) -> list[str]:
    return [token for token in name.split() if len(token) >= 2]


def _name_contained(booking_name: str, document_text: str) -> bool:
    """True when the booking name (or all its tokens, any order) appears in the OCR.

    :param booking_name: Passenger name from booking markdown.
    :param document_text: Supporting-document OCR text.
    :return: Whether the deterministic identity match succeeds.
    """
    name = normalized_text(_PARENTHETICAL.sub(" ", booking_name))
    document = normalized_text(document_text)
    if not name or not document:
        return False
    if name in document:
        return True
    tokens = _name_tokens(name)
    if len(tokens) < 2:
        return bool(tokens) and len(tokens[0]) >= 3 and tokens[0] in document
    return all(token in document for token in tokens)


def _names_within_edit_distance(booking_name: str, document_name: str, *, max_distance: int) -> bool:
    """True when names match within ``max_distance`` edits, whole or token-wise.

    Token-wise matching is order-independent: every booking token must find a
    distinct document token within ``max_distance``.

    :param booking_name: Claimant name from booking.
    :param document_name: Patient name extracted from OCR.
    :param max_distance: Inclusive Levenshtein threshold.
    :return: Whether identity should pass.
    """
    left = normalized_text(_PARENTHETICAL.sub(" ", booking_name))
    right = normalized_text(_PARENTHETICAL.sub(" ", document_name))
    if not left or not right:
        return False
    if _levenshtein(left, right) <= max_distance:
        return True
    left_tokens = _name_tokens(left)
    right_tokens = _name_tokens(right)
    if not left_tokens or not right_tokens:
        return False
    used: set[int] = set()
    for token in left_tokens:
        match_idx: int | None = None
        best = max_distance + 1
        for idx, other in enumerate(right_tokens):
            if idx in used:
                continue
            distance = _levenshtein(token, other)
            if distance < best:
                best = distance
                match_idx = idx
        if match_idx is None:
            return False
        used.add(match_idx)
    return True


def _levenshtein(left: str, right: str) -> int:
    """Classic Levenshtein edit distance between two strings.

    :param left: First string.
    :param right: Second string.
    :return: Minimum insert/delete/substitute count.
    """
    if left == right:
        return 0
    if not left:
        return len(right)
    if not right:
        return len(left)
    prev = list(range(len(right) + 1))
    for i, ch_left in enumerate(left, start=1):
        curr = [i]
        for j, ch_right in enumerate(right, start=1):
            curr.append(min(curr[j - 1] + 1, prev[j] + 1, prev[j - 1] + (ch_left != ch_right)))
        prev = curr
    return prev[-1]
