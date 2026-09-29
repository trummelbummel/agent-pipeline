from __future__ import annotations

import logging
import re
import unicodedata
from typing import Literal

import ollama
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from compliance.llm.chat import ChatFn, parse_llm_json_object, response_content

logger = logging.getLogger(__name__)

CheckerMode = Literal[
    "containment",
    "contradicts",
    "identity",
    "healthy",
    "not_authentic",
    "incomplete",
]
IdentityStatus = Literal["match", "mismatch", "unclear"]

# Deny-on-True modes: parse / validation failure → True (violation / fail-closed).
_DENY_ON_TRUE_MODES: frozenset[CheckerMode] = frozenset({"not_authentic", "incomplete"})

_BOOKING_NAME_FIELD = re.compile(r"(?im)^\s*(?:\*\*)?name(?:\*\*)?\s*:\s*(.+?)\s*$")
# Booking name notes like ``(partner)`` mean the passenger is not the patient —
# containment against requester text in OCR would false-pass identity.
_BOOKING_ROLE_NOTE = re.compile(
    r"(?i)\(\s*(partner|spouse|wife|husband|child|son|daughter|"
    r"mother|father|parent|friend|relative)\s*\)"
)


class BooleanCheckResult(BaseModel):
    """LLM JSON contract for Checker boolean modes."""

    model_config = ConfigDict(strict=True)

    result: bool = Field(description="True when the mode condition holds")


class ExtractedNameResult(BaseModel):
    """LLM JSON contract for patient / claimant name extraction."""

    model_config = ConfigDict(strict=True)

    name: str | None = Field(description="Extracted person name, or null when no clear name field")


class UnsupportedCheckerModeError(ValueError):
    """A ``CheckerMode`` value was passed that ``Checker.check`` does not dispatch."""

    def __init__(self, mode: str) -> None:
        """Build the unsupported-mode message from the offending mode value.

        :param mode: The unsupported mode value that was passed to ``check``.
        """
        super().__init__(f"Unsupported checker mode: {mode!r}")


class Checker:
    """Claim-vs-text checker: containment, contradicts, identity, healthy, authenticity."""

    def __init__(
        self,
        model_name: str,
        containment_prompt: str,
        contradicts_prompt: str,
        identity_prompt: str,
        healthy_prompt: str,
        authenticity_prompt: str,
        incomplete_prompt: str,
        chat_fn: ChatFn | None = None,
        *,
        identity_max_edit_distance: int = 3,
    ) -> None:
        """Bind model, prompts, and optional chat seam.

        :param model_name: LLM model name from config.
        :param containment_prompt: System prompt for containment mode.
        :param contradicts_prompt: System prompt for contradiction mode.
        :param identity_prompt: System prompt that extracts a person name as JSON
            ``{"name": "..."}`` or ``{"name": null}``.
        :param healthy_prompt: System prompt for healthy-certificate detection.
        :param authenticity_prompt: System prompt for document authenticity / format
            (True = not authentic → violation).
        :param incomplete_prompt: System prompt for incomplete medical fields
            (True = required fields missing → violation).
        :param chat_fn: Optional chat callable for tests; defaults to ollama.chat.
        :param identity_max_edit_distance: Max Levenshtein distance (lowercased
            names) for identity ``match`` after name extraction.
        """
        self.model_name = model_name
        self.containment_prompt = containment_prompt
        self.contradicts_prompt = contradicts_prompt
        self.identity_prompt = identity_prompt
        self.healthy_prompt = healthy_prompt
        self.authenticity_prompt = authenticity_prompt
        self.incomplete_prompt = incomplete_prompt
        self.identity_max_edit_distance = identity_max_edit_distance
        self._chat: ChatFn = chat_fn or ollama.chat

    def check(
        self,
        claim: str,
        text: str,
        mode: CheckerMode,
    ) -> bool:
        """Check claim against text for the selected mode.

        :param claim: Claim / booking text (unused for OCR-focused modes).
        :param text: Supporting document OCR text (primary input for healthy /
            not_authentic / incomplete).
        :param mode: ``containment``, ``contradicts``, ``identity``, ``healthy``,
            ``not_authentic``, or ``incomplete``.
        :return: True when the mode condition holds; for ``identity``, True only on
            ``match`` (``mismatch`` / ``unclear`` → False). Prefer ``check_identity``
            when the three-way outcome matters. For ``not_authentic`` /
            ``incomplete``, True means violation (fail-closed on parse errors).
        :raises UnsupportedCheckerModeError: When ``mode`` is not a supported checker mode
            (a ``ValueError`` subclass).
        """
        if mode == "containment":
            return self._containment_result(claim, text)
        if mode == "contradicts":
            return self._llm_boolean_result(self.contradicts_prompt, claim, text, mode=mode)
        if mode == "identity":
            return self.check_identity(claim, text) == "match"
        if mode == "healthy":
            return self._llm_boolean_result(self.healthy_prompt, claim, text, mode=mode)
        if mode == "not_authentic":
            return self._llm_boolean_result(self.authenticity_prompt, claim, text, mode=mode)
        if mode == "incomplete":
            return self._llm_boolean_result(self.incomplete_prompt, claim, text, mode=mode)
        raise UnsupportedCheckerModeError(mode)

    def check_identity(self, booking_text: str, document_text: str) -> IdentityStatus:
        """Compare booking name to patient/subject name on the medical OCR.

        Order:
        1. Deterministic containment of the booking ``**name**`` field in OCR
           (skipped when the booking name has a role note such as ``(partner)``,
           so a requester name in the letter cannot false-pass).
        2. Extract booking name (markdown field, else LLM) and patient name (LLM).
        3. Lowercased Levenshtein distance ≤ ``identity_max_edit_distance`` → match
           (also token-wise with the same threshold). Else mismatch / unclear.

        :param booking_text: Booking / internal ``supporting_documents`` markdown.
        :param document_text: Medical ``supporting_document`` OCR markdown.
        :return: ``match``, ``mismatch``, or ``unclear`` (no clear patient field).
        """
        booking_name = self._booking_name(booking_text)
        if (
            booking_name
            and not self._booking_has_role_note(booking_name)
            and self._identity_name_contained(booking_name, document_text)
        ):
            return "match"

        if not booking_name:
            booking_name = self._extract_person_name(booking_text, role="booking_claimant")
        document_name = self._extract_person_name(document_text, role="document_patient")
        if not document_name:
            return "unclear"
        if not booking_name:
            return "unclear"
        if self._names_within_edit_distance(
            booking_name,
            document_name,
            max_distance=self.identity_max_edit_distance,
        ):
            return "match"
        return "mismatch"

    def _extract_person_name(self, text: str, *, role: str) -> str | None:
        """Ask the LLM to extract a single person name from free text.

        :param text: Booking markdown or medical OCR.
        :param role: ``booking_claimant`` or ``document_patient`` (user framing).
        :return: Extracted name, or ``None`` when missing / unparseable.
        """
        if role == "booking_claimant":
            user_content = f"Extract the passenger / claimant name from this booking or internal record text:\n{text}"
        else:
            user_content = (
                "Extract the patient / subject / insured name from this medical "
                "supporting-document OCR. Prefer names next to patient / paciente / "
                "subject markers. Ignore doctor, facility, letterhead, signature-block, "
                "and requester / applicant / 'solicitud del' / 'a solicitud de' names "
                f"(those are not the patient):\n{text}"
            )
        response = self._chat(
            model=self.model_name,
            messages=[
                {"role": "system", "content": self.identity_prompt},
                {"role": "user", "content": user_content},
            ],
            format="json",
        )
        return self._parse_extracted_name(response_content(response))

    def _containment_result(self, claim: str, text: str) -> bool:
        normalized_claim = self._normalized_text(claim)
        if normalized_claim and normalized_claim in self._normalized_text(text):
            return True
        return self._llm_boolean_result(self.containment_prompt, claim, text, mode="containment")

    def _llm_boolean_result(self, prompt: str, claim: str, text: str, *, mode: CheckerMode) -> bool:
        response = self._chat(
            model=self.model_name,
            messages=self._check_messages(prompt, claim, text, mode=mode),
            format="json",
        )
        return self._parse_boolean_result(response_content(response), mode=mode)

    @staticmethod
    def _booking_name(booking_text: str) -> str | None:
        """Extract the passenger ``name`` field from booking markdown.

        :param booking_text: ``supporting_documents.md`` body.
        :return: Raw name string, or ``None`` when the field is absent.
        """
        match = _BOOKING_NAME_FIELD.search(booking_text)
        if match is None:
            return None
        name = match.group(1).strip()
        return name or None

    @staticmethod
    def _booking_has_role_note(booking_name: str) -> bool:
        """True when the booking name carries a relationship note (e.g. partner).

        :param booking_name: Raw ``**name**`` field value from booking markdown.
        :return: Whether containment short-circuit should be skipped.
        """
        return _BOOKING_ROLE_NOTE.search(booking_name) is not None

    @classmethod
    def _identity_name_contained(cls, booking_name: str, document_text: str) -> bool:
        """True when the booking name (or all its tokens) appears in the OCR.

        Comparison is case-insensitive after NFKC normalization. Parenthetical
        notes on the booking name (e.g. ``(partner)``) are ignored for the
        string match itself. Token containment allows reordered names when
        every token is present.

        :param booking_name: Passenger name from booking / internal markdown.
        :param document_text: Supporting-document OCR text.
        :return: Whether deterministic identity match succeeds.
        """
        name = cls._normalized_text(re.sub(r"\([^)]*\)", " ", booking_name))
        doc = cls._normalized_text(document_text)
        if not name or not doc:
            return False
        if name in doc:
            return True
        tokens = [token for token in name.split() if len(token) >= 2]
        if len(tokens) < 2:
            return bool(tokens) and len(tokens[0]) >= 3 and tokens[0] in doc
        return all(token in doc for token in tokens)

    @classmethod
    def _names_within_edit_distance(
        cls,
        booking_name: str,
        document_name: str,
        *,
        max_distance: int,
    ) -> bool:
        """True when lowercased names are within ``max_distance`` edits.

        Checks full-string Levenshtein, then token-wise matching (order-
        independent): every booking token length ≥ 2 must find a distinct
        document token within ``max_distance``.

        :param booking_name: Claimant name from booking.
        :param document_name: Patient name extracted from OCR.
        :param max_distance: Inclusive Levenshtein threshold (closer → pass).
        :return: Whether identity should pass.
        """
        left = cls._normalized_text(re.sub(r"\([^)]*\)", " ", booking_name))
        right = cls._normalized_text(re.sub(r"\([^)]*\)", " ", document_name))
        if not left or not right:
            return False
        if cls._levenshtein(left, right) <= max_distance:
            return True
        left_tokens = [t for t in left.split() if len(t) >= 2]
        right_tokens = [t for t in right.split() if len(t) >= 2]
        if not left_tokens or not right_tokens:
            return False
        used: set[int] = set()
        for token in left_tokens:
            match_idx: int | None = None
            best = max_distance + 1
            for idx, other in enumerate(right_tokens):
                if idx in used:
                    continue
                dist = cls._levenshtein(token, other)
                if dist < best:
                    best = dist
                    match_idx = idx
            if match_idx is None or best > max_distance:
                return False
            used.add(match_idx)
        return True

    @staticmethod
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
                insert = curr[j - 1] + 1
                delete = prev[j] + 1
                replace = prev[j - 1] + (ch_left != ch_right)
                curr.append(min(insert, delete, replace))
            prev = curr
        return prev[-1]

    @staticmethod
    def _check_messages(
        prompt: str, claim: str, text: str, *, mode: CheckerMode = "containment"
    ) -> list[dict[str, str]]:
        if mode in ("healthy", "not_authentic", "incomplete"):
            user_content = f"Supporting document (OCR):\n{text}"
        else:
            user_content = f"Claim:\n{claim}\n\nText:\n{text}"
        return [
            {"role": "system", "content": prompt},
            {"role": "user", "content": user_content},
        ]

    @staticmethod
    def _parse_boolean_result(content: str, *, mode: CheckerMode = "containment") -> bool:
        fail_closed = mode in _DENY_ON_TRUE_MODES
        parsed = parse_llm_json_object(content, context="checker")
        if parsed is None:
            return fail_closed
        try:
            return BooleanCheckResult.model_validate(parsed).result
        except ValidationError:
            logger.warning("LLM checker JSON missing bool result")
            return fail_closed

    @staticmethod
    def _parse_extracted_name(content: str) -> str | None:
        """Parse ``{"name": "..."}`` / ``{"name": null}`` from extraction JSON.

        :param content: Raw LLM message content.
        :return: Non-empty name string, or ``None``.
        """
        parsed = parse_llm_json_object(content, context="checker identity name")
        if parsed is None:
            return None
        try:
            name = ExtractedNameResult.model_validate(parsed).name
        except ValidationError:
            logger.warning("LLM identity name JSON invalid")
            return None
        if name is None:
            return None
        cleaned = name.strip()
        return cleaned or None

    @staticmethod
    def _normalized_text(value: str) -> str:
        collapsed = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value).casefold())
        return collapsed.strip()
