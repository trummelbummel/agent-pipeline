"""Checker policy matrix (``CheckOutcome`` = PASS | VIOLATION | ABSTAIN | ERROR).

Boolean LLM modes. ``result`` is the validated ``{"result": bool}`` field
parsed from the LLM JSON response. The outcome comes from one per-mode
polarity table lookup — there is no per-mode if/elif polarity logic.

| Mode          | result true  | result false | malformed JSON / missing or non-bool result / empty | transport error after retries |
|---------------|--------------|--------------|--------------------------------------------------------|-------------------------------|
| containment   | PASS         | ABSTAIN      | ERROR                                                   | ERROR                         |
| contradicts   | VIOLATION    | PASS         | ERROR                                                   | ERROR                         |
| healthy       | VIOLATION    | PASS         | ERROR                                                   | ERROR                         |
| not_authentic | VIOLATION    | PASS         | ERROR                                                   | ERROR                         |
| incomplete    | VIOLATION    | PASS         | ERROR                                                   | ERROR                         |

A deterministic containment hit (normalized claim substring of the text) is
PASS with no LLM call.

Containment's ERROR is recorded in ``checker_outcomes`` by the pipeline, but
is intentionally excluded from the "any ERROR -> UNCERTAIN" precedence step —
a malformed containment response never drove the decision before, and it
still does not (record-only).

Identity:

| Situation                                                                      | Outcome   |
|---------------------------------------------------------------------------------|-----------|
| booking name field contained in OCR (no role note), no LLM call                 | PASS      |
| both names extracted, within identity_max_edit_distance                         | PASS      |
| both names extracted, beyond identity_max_edit_distance                          | VIOLATION |
| an extraction returned {"name": null} or a blank name, none errored             | ABSTAIN   |
| an extraction was unparseable / schema-invalid / transport error after retries  | ERROR     |

See ``compliance.workflows.claim_pipeline`` for how ``CheckOutcome`` folds
into the claim decision (VIOLATION -> DENY; ERROR -> UNCERTAIN, except
containment; identity ABSTAIN -> UNCERTAIN; else APPROVE).
"""

from __future__ import annotations

import logging
import re
import unicodedata
from enum import Enum
from typing import Literal, NamedTuple

import ollama
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from compliance.config.settings import TransportRetryConfig
from compliance.llm.chat import ChatFn, chat_content_with_retry, parse_llm_json_object

logger = logging.getLogger(__name__)

CheckerMode = Literal[
    "containment",
    "contradicts",
    "identity",
    "healthy",
    "not_authentic",
    "incomplete",
]

_BOOKING_NAME_FIELD = re.compile(r"(?im)^\s*(?:\*\*)?name(?:\*\*)?\s*:\s*(.+?)\s*$")
# Booking name notes like ``(partner)`` mean the passenger is not the patient —
# containment against requester text in OCR would false-pass identity.
_BOOKING_ROLE_NOTE = re.compile(
    r"(?i)\(\s*(partner|spouse|wife|husband|child|son|daughter|"
    r"mother|father|parent|friend|relative)\s*\)"
)


class CheckOutcome(str, Enum):
    """Typed result of a single ``Checker`` mode (SR-008).

    :cvar PASS: The mode condition does not hold; no violation.
    :cvar VIOLATION: The mode condition holds; drives a DENY decision.
    :cvar ABSTAIN: A parse succeeded but yielded no decidable signal (e.g. a
        null/blank extracted name, or a deterministic containment miss).
        Never itself an error, but not evidence for PASS either.
    :cvar ERROR: The LLM output was malformed/unparseable, or (with retry
        configured) the chat transport failed after exhausting retries.
    """

    PASS = "PASS"  # noqa: S105 — outcome enum value, not a credential
    VIOLATION = "VIOLATION"
    ABSTAIN = "ABSTAIN"
    ERROR = "ERROR"


class _ModePolarity(NamedTuple):
    """Resolved CheckOutcome for a boolean mode's true/false result.

    :param when_true: Outcome when the LLM boolean result is True.
    :param when_false: Outcome when the LLM boolean result is False.
    """

    when_true: CheckOutcome
    when_false: CheckOutcome


# Per-mode polarity, exactly as the module-docstring matrix states. Looked up
# once in `_boolean_outcome`; no per-mode if/elif branches anywhere else.
_MODE_POLARITY: dict[CheckerMode, _ModePolarity] = {
    "containment": _ModePolarity(CheckOutcome.PASS, CheckOutcome.ABSTAIN),
    "contradicts": _ModePolarity(CheckOutcome.VIOLATION, CheckOutcome.PASS),
    "healthy": _ModePolarity(CheckOutcome.VIOLATION, CheckOutcome.PASS),
    "not_authentic": _ModePolarity(CheckOutcome.VIOLATION, CheckOutcome.PASS),
    "incomplete": _ModePolarity(CheckOutcome.VIOLATION, CheckOutcome.PASS),
}


class _NameExtraction(NamedTuple):
    """Structured result of extracting a person name from free text.

    :param name: Non-empty extracted name, or None when null/blank/absent.
    :param failed: True when the LLM content was unparseable or failed
        ``ExtractedNameResult`` schema validation (an ERROR, not an ABSTAIN).
    """

    name: str | None
    failed: bool


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
        transport_retry: TransportRetryConfig | None = None,
    ) -> None:
        """Bind model, prompts, and optional chat seam.

        :param model_name: LLM model name from config.
        :param containment_prompt: System prompt for containment mode.
        :param contradicts_prompt: System prompt for contradiction mode.
        :param identity_prompt: System prompt that extracts a person name as JSON
            ``{"name": "..."}`` or ``{"name": null}``.
        :param healthy_prompt: System prompt for healthy-certificate detection.
        :param authenticity_prompt: System prompt for document authenticity / format
            (True = not authentic -> violation).
        :param incomplete_prompt: System prompt for incomplete medical fields
            (True = required fields missing -> violation).
        :param chat_fn: Optional chat callable for tests; defaults to ollama.chat.
        :param identity_max_edit_distance: Max Levenshtein distance (lowercased
            names) for identity PASS after name extraction.
        :param transport_retry: Bounded retry for chat transport failures; defaults
            to ``TransportRetryConfig()`` when omitted.
        """
        self.model_name = model_name
        self.containment_prompt = containment_prompt
        self.contradicts_prompt = contradicts_prompt
        self.identity_prompt = identity_prompt
        self.healthy_prompt = healthy_prompt
        self.authenticity_prompt = authenticity_prompt
        self.incomplete_prompt = incomplete_prompt
        self.identity_max_edit_distance = identity_max_edit_distance
        self._transport_retry = transport_retry if transport_retry is not None else TransportRetryConfig()
        self._chat: ChatFn = chat_fn or ollama.chat

    def check(
        self,
        claim: str,
        text: str,
        mode: CheckerMode,
    ) -> CheckOutcome:
        """Check claim against text for the selected mode.

        :param claim: Claim / booking text (unused for OCR-focused modes).
        :param text: Supporting document OCR text (primary input for healthy /
            not_authentic / incomplete).
        :param mode: ``containment``, ``contradicts``, ``identity``, ``healthy``,
            ``not_authentic``, or ``incomplete``.
        :return: The mode's ``CheckOutcome`` per the module policy matrix.
            ``identity`` delegates to ``check_identity``.
        :raises UnsupportedCheckerModeError: When ``mode`` is not a supported checker mode
            (a ``ValueError`` subclass).
        """
        if mode == "containment":
            return self._containment_outcome(claim, text)
        if mode == "identity":
            return self.check_identity(claim, text)
        if mode not in _MODE_POLARITY:
            raise UnsupportedCheckerModeError(mode)
        return self._boolean_check(self._prompt_for_mode(mode), claim, text, mode=mode)

    def check_identity(self, booking_text: str, document_text: str) -> CheckOutcome:
        """Compare booking name to patient/subject name on the medical OCR.

        Order:
        1. Deterministic containment of the booking ``**name**`` field in OCR
           (skipped when the booking name has a role note such as ``(partner)``,
           so a requester name in the letter cannot false-pass) -> PASS, no LLM call.
        2. Booking name: the markdown ``name`` field when present, else an LLM
           extraction. Document name: always an LLM extraction. Both extractions
           are always attempted before folding (today's call order is unchanged).
        3. Either extraction unparseable/schema-invalid -> ERROR. Either name
           missing (null/blank) -> ABSTAIN. Lowercased Levenshtein distance
           (also token-wise) <= ``identity_max_edit_distance`` -> PASS, else VIOLATION.

        :param booking_text: Booking / internal ``supporting_documents`` markdown.
        :param document_text: Medical ``supporting_document`` OCR markdown.
        :return: ``CheckOutcome`` per the module policy matrix identity table.
        """
        booking_name = self._booking_name(booking_text)
        if (
            booking_name
            and not self._booking_has_role_note(booking_name)
            and self._identity_name_contained(booking_name, document_text)
        ):
            return CheckOutcome.PASS

        booking = (
            _NameExtraction(name=booking_name, failed=False)
            if booking_name
            else self._extract_person_name(booking_text, role="booking_claimant")
        )
        document = self._extract_person_name(document_text, role="document_patient")
        return self._identity_outcome(booking, document)

    def _identity_outcome(self, booking: _NameExtraction, document: _NameExtraction) -> CheckOutcome:
        """Fold two name extractions into an identity ``CheckOutcome`` (D-02).

        :param booking: Booking/claimant name extraction result.
        :param document: Document/patient name extraction result.
        :return: ERROR when either extraction failed; ABSTAIN when either name
            is missing; PASS within the edit-distance threshold; else VIOLATION.
        """
        if booking.failed or document.failed:
            return CheckOutcome.ERROR
        if not booking.name or not document.name:
            return CheckOutcome.ABSTAIN
        if self._names_within_edit_distance(
            booking.name,
            document.name,
            max_distance=self.identity_max_edit_distance,
        ):
            return CheckOutcome.PASS
        return CheckOutcome.VIOLATION

    def _extract_person_name(self, text: str, *, role: str) -> _NameExtraction:
        """Ask the LLM to extract a single person name from free text.

        :param text: Booking markdown or medical OCR.
        :param role: ``booking_claimant`` or ``document_patient`` (user framing).
        :return: Structured extraction result (name and/or failed flag).
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
        content = chat_content_with_retry(
            self._chat,
            self._transport_retry,
            context=f"checker identity {role}",
            model=self.model_name,
            messages=[
                {"role": "system", "content": self.identity_prompt},
                {"role": "user", "content": user_content},
            ],
            format="json",
        )
        if content is None:
            return _NameExtraction(name=None, failed=True)
        return self._parsed_name_extraction(content)

    def _containment_outcome(self, claim: str, text: str) -> CheckOutcome:
        normalized_claim = self._normalized_text(claim)
        if normalized_claim and normalized_claim in self._normalized_text(text):
            return CheckOutcome.PASS
        return self._boolean_check(self.containment_prompt, claim, text, mode="containment")

    def _prompt_for_mode(self, mode: CheckerMode) -> str:
        """Look up the configured system prompt for a boolean checker mode.

        :param mode: One of the ``_MODE_POLARITY`` boolean modes.
        :return: The mode's system prompt string.
        """
        prompts: dict[CheckerMode, str] = {
            "contradicts": self.contradicts_prompt,
            "healthy": self.healthy_prompt,
            "not_authentic": self.authenticity_prompt,
            "incomplete": self.incomplete_prompt,
        }
        return prompts[mode]

    def _boolean_check(self, prompt: str, claim: str, text: str, *, mode: CheckerMode) -> CheckOutcome:
        content = chat_content_with_retry(
            self._chat,
            self._transport_retry,
            context=f"checker {mode}",
            model=self.model_name,
            messages=self._check_messages(prompt, claim, text, mode=mode),
            format="json",
        )
        if content is None:
            return CheckOutcome.ERROR
        return self._boolean_outcome(content, mode=mode)

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
        independent): every booking token length >= 2 must find a distinct
        document token within ``max_distance``.

        :param booking_name: Claimant name from booking.
        :param document_name: Patient name extracted from OCR.
        :param max_distance: Inclusive Levenshtein threshold (closer -> pass).
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
    def _boolean_outcome(content: str, *, mode: CheckerMode) -> CheckOutcome:
        """Parse a boolean-mode LLM response into its polarity-resolved outcome.

        :param content: Raw LLM message content.
        :param mode: The boolean mode being parsed (looks up ``_MODE_POLARITY``).
        :return: ERROR on empty/malformed/schema-invalid content; else the
            mode's polarity-resolved outcome for the parsed boolean.
        """
        parsed = parse_llm_json_object(content, context="checker")
        if parsed is None:
            return CheckOutcome.ERROR
        try:
            result = BooleanCheckResult.model_validate(parsed).result
        except ValidationError:
            logger.warning("LLM checker JSON missing bool result")
            return CheckOutcome.ERROR
        polarity = _MODE_POLARITY[mode]
        return polarity.when_true if result else polarity.when_false

    @staticmethod
    def _parsed_name_extraction(content: str) -> _NameExtraction:
        """Parse ``{"name": "..."}`` / ``{"name": null}`` from extraction JSON.

        :param content: Raw LLM message content.
        :return: ``failed=True`` on empty/malformed/schema-invalid content;
            otherwise a name (stripped, non-empty) or None (null/blank).
        """
        parsed = parse_llm_json_object(content, context="checker identity name")
        if parsed is None:
            return _NameExtraction(name=None, failed=True)
        try:
            name = ExtractedNameResult.model_validate(parsed).name
        except ValidationError:
            logger.warning("LLM identity name JSON invalid")
            return _NameExtraction(name=None, failed=True)
        if name is None:
            return _NameExtraction(name=None, failed=False)
        cleaned = name.strip()
        return _NameExtraction(name=cleaned or None, failed=False)

    @staticmethod
    def _normalized_text(value: str) -> str:
        collapsed = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value).casefold())
        return collapsed.strip()
