"""Check contracts shared by every composable claim check (SR-008).

Policy matrix (``CheckOutcome`` = PASS | VIOLATION | ABSTAIN | ERROR).

Boolean LLM checks. ``result`` is the validated ``{"result": bool}`` field
parsed from the LLM JSON response. Each check carries its own ``Polarity``;
there is no per-mode if/elif polarity logic.

| Mode          | result true  | result false | malformed JSON / missing or non-bool result / empty | transport error after retries |
|---------------|--------------|--------------|--------------------------------------------------------|-------------------------------|
| containment   | PASS         | ABSTAIN      | ERROR                                                   | ERROR                         |
| contradicts   | VIOLATION    | PASS         | ERROR                                                   | ERROR                         |
| healthy       | VIOLATION    | PASS         | ERROR                                                   | ERROR                         |
| incomplete    | VIOLATION    | PASS         | ERROR                                                   | ERROR                         |

A deterministic containment hit (normalized claim substring of the text) is
PASS with no LLM call.

Containment's ERROR is recorded in ``checker_outcomes`` by the pipeline, but
is intentionally excluded from the "any ERROR -> UNCERTAIN" precedence step —
a malformed containment response never drove the decision (record-only).

Identity:

| Situation                                                                      | Outcome   |
|---------------------------------------------------------------------------------|-----------|
| booking name field contained in OCR (no role note), no LLM call                 | PASS      |
| both names extracted, within identity_max_edit_distance                         | PASS      |
| both names extracted, beyond identity_max_edit_distance                          | VIOLATION |
| an extraction returned {"name": null} or a blank name, none errored             | VIOLATION |
| an extraction was unparseable / schema-invalid / transport error after retries  | ERROR     |

See ``compliance.policy.decision`` for how ``CheckOutcome`` folds into the claim
decision (VIOLATION → DENY, except incomplete VIOLATION alone under OCR/YOLO
HITL → UNCERTAIN; ERROR → UNCERTAIN, except containment; else APPROVE).
"""

from __future__ import annotations

import re
import unicodedata
from enum import Enum
from typing import Literal, NamedTuple, Protocol

CheckerMode = Literal[
    "containment",
    "contradicts",
    "identity",
    "healthy",
    "incomplete",
]


class CheckOutcome(str, Enum):
    """Typed result of a single check (SR-008).

    :cvar PASS: The check condition does not hold; no violation.
    :cvar VIOLATION: The check condition holds; drives a DENY decision.
    :cvar ABSTAIN: A parse succeeded but yielded no decidable signal (e.g. a
        deterministic containment miss answered false). Never itself an
        error, but not evidence for PASS either.
    :cvar ERROR: The LLM output was malformed/unparseable, or the chat
        transport failed after exhausting retries.
    """

    PASS = "PASS"  # noqa: S105 — outcome enum value, not a credential
    VIOLATION = "VIOLATION"
    ABSTAIN = "ABSTAIN"
    ERROR = "ERROR"


class CheckContext(NamedTuple):
    """Texts a check may read for one claim.

    :param description: Claim narrative (``description.txt``).
    :param document: Supporting-document OCR markdown.
    :param booking: Booking / internal markdown carrying the passenger ``name``.
    """

    description: str
    document: str
    booking: str


class Check(Protocol):
    """One composable claim check producing a ``CheckOutcome``."""

    name: CheckerMode

    def run(self, context: CheckContext) -> CheckOutcome:
        """Evaluate the check for one claim.

        :param context: Claim texts the check reads.
        :return: The check's outcome per the module policy matrix.
        """
        ...


def normalized_text(value: str) -> str:
    """NFKC-normalize, casefold, and collapse whitespace for substring matching.

    :param value: Raw claim / OCR / name text.
    :return: Comparable normalized text.
    """
    collapsed = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value).casefold())
    return collapsed.strip()
