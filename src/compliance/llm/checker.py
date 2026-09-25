from __future__ import annotations

import logging
import re
import unicodedata
from typing import Literal

import ollama
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from compliance.llm.chat import ChatFn, parse_llm_json_object, response_content

logger = logging.getLogger(__name__)

CheckerMode = Literal["containment", "contradicts", "identity", "healthy"]
IdentityStatus = Literal["match", "mismatch", "unclear"]

_BOOKING_NAME_FIELD = re.compile(
    r"(?im)^\s*(?:\*\*)?name(?:\*\*)?\s*:\s*(.+?)\s*$"
)


class BooleanCheckResult(BaseModel):
    """LLM JSON contract for Checker boolean modes."""

    model_config = ConfigDict(strict=True)

    result: bool = Field(description="True when the mode condition holds")


class Checker:
    """Claim-vs-text checker: containment, contradicts, identity, healthy."""

    def __init__(
        self,
        model_name: str,
        containment_prompt: str,
        contradicts_prompt: str,
        identity_prompt: str,
        healthy_prompt: str,
        chat_fn: ChatFn | None = None,
    ) -> None:
        """Bind model, prompts, and optional chat seam.

        :param model_name: LLM model name from config.
        :param containment_prompt: System prompt for containment mode.
        :param contradicts_prompt: System prompt for contradicts mode.
        :param identity_prompt: System prompt for booking vs document name checks.
        :param healthy_prompt: System prompt for healthy-certificate detection.
        :param chat_fn: Optional chat callable for tests; defaults to ollama.chat.
        """
        self.model_name = model_name
        self.containment_prompt = containment_prompt
        self.contradicts_prompt = contradicts_prompt
        self.identity_prompt = identity_prompt
        self.healthy_prompt = healthy_prompt
        self._chat: ChatFn = chat_fn or ollama.chat

    def check(
        self,
        claim: str,
        text: str,
        mode: CheckerMode,
    ) -> bool:
        """Check claim against text for the selected mode.

        :param claim: Claim / booking text (unused for ``healthy`` mode).
        :param text: Supporting document OCR text (primary input for ``healthy``).
        :param mode: ``containment``, ``contradicts``, ``identity``, or ``healthy``.
        :return: True when the mode condition holds; for ``identity``, True only on
            ``match`` (``mismatch`` / ``unclear`` → False). Prefer ``check_identity``
            when the three-way outcome matters.
        :raises ValueError: When ``mode`` is not a supported checker mode.
        """
        if mode == "containment":
            return self._containment_result(claim, text)
        if mode == "contradicts":
            return self._llm_boolean_result(
                self.contradicts_prompt, claim, text, mode=mode
            )
        if mode == "identity":
            return self.check_identity(claim, text) == "match"
        if mode == "healthy":
            return self._llm_boolean_result(
                self.healthy_prompt, claim, text, mode=mode
            )
        raise ValueError(f"Unsupported checker mode: {mode!r}")

    def check_identity(self, booking_text: str, document_text: str) -> IdentityStatus:
        """Compare booking name to patient/subject name on the medical OCR.

        First tries a deterministic lowercase containment check (full booking name
        or all name tokens present in the OCR). On success the LLM is skipped.
        Otherwise falls back to the identity prompt for match/mismatch/unclear.

        :param booking_text: Booking / internal ``supporting_documents`` markdown.
        :param document_text: Medical ``supporting_document`` OCR markdown.
        :return: ``match``, ``mismatch``, or ``unclear`` (no clear patient field).
        """
        booking_name = self._booking_name(booking_text)
        if booking_name and self._identity_name_contained(booking_name, document_text):
            return "match"
        response = self._chat(
            model=self.model_name,
            messages=self._check_messages(
                self.identity_prompt,
                booking_text,
                document_text,
                mode="identity",
            ),
            format="json",
        )
        return self._parse_identity_result(response_content(response))

    def _containment_result(self, claim: str, text: str) -> bool:
        normalized_claim = self._normalized_text(claim)
        if normalized_claim and normalized_claim in self._normalized_text(text):
            return True
        return self._llm_boolean_result(
            self.containment_prompt, claim, text, mode="containment"
        )

    def _llm_boolean_result(
        self, prompt: str, claim: str, text: str, *, mode: CheckerMode
    ) -> bool:
        response = self._chat(
            model=self.model_name,
            messages=self._check_messages(prompt, claim, text, mode=mode),
            format="json",
        )
        return self._parse_boolean_result(response_content(response))

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

    @classmethod
    def _identity_name_contained(cls, booking_name: str, document_text: str) -> bool:
        """True when the booking name (or all its tokens) appears in the OCR.

        Comparison is case-insensitive after NFKC normalization. Parenthetical
        notes on the booking name (e.g. ``(partner)``) are ignored. Token
        containment allows reordered names when every token is present.

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

    @staticmethod
    def _check_messages(
        prompt: str, claim: str, text: str, *, mode: CheckerMode = "containment"
    ) -> list[dict[str, str]]:
        if mode == "identity":
            user_content = (
                f"Booking / internal supporting documents:\n{claim}\n\n"
                f"Supporting document (OCR):\n{text}"
            )
        elif mode == "healthy":
            user_content = f"Supporting document (OCR):\n{text}"
        else:
            user_content = f"Claim:\n{claim}\n\nText:\n{text}"
        return [
            {"role": "system", "content": prompt},
            {"role": "user", "content": user_content},
        ]

    @staticmethod
    def _parse_boolean_result(content: str) -> bool:
        parsed = parse_llm_json_object(content, context="checker")
        if parsed is None:
            return False
        try:
            return BooleanCheckResult.model_validate(parsed).result
        except ValidationError:
            logger.warning("LLM checker JSON missing bool result")
            return False

    @staticmethod
    def _parse_identity_result(content: str) -> IdentityStatus:
        parsed = parse_llm_json_object(content, context="checker identity")
        if parsed is None:
            return "mismatch"
        raw = parsed.get("result")
        if raw is True or raw == "match":
            return "match"
        if raw == "unclear":
            return "unclear"
        if raw is False or raw == "mismatch":
            return "mismatch"
        logger.warning("LLM identity JSON has unrecognized result=%r", raw)
        return "mismatch"

    @staticmethod
    def _normalized_text(value: str) -> str:
        collapsed = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value).casefold())
        return collapsed.strip()
