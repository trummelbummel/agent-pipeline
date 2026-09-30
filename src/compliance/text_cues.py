"""Normalized multilingual cue matching for config-backed vocabularies.

Lexical cues (issue-date wording, care-window wording, DOB markers, medical
narrative keywords) live in ``config.yaml`` as plain string lists. Matching is
accent-insensitive substring / word-boundary search — not a growing mega-regex.

When a list grows unwieldy across languages, prefer an LLM role-extraction
fallback (e.g. structured ``issue_date`` / ``care_start``); that path is
non-deterministic and is not wired here.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence

# Defaults mirror config.yaml so unit tests and partial CheckingConfig fixtures
# behave without loading the full file.

DEFAULT_ISSUE_DATE_CUES: tuple[str, ...] = (
    "issue date",
    "date of issue",
    "issued on",
    "issued",
    "stamped",
    "émission",
    "emision",
    "emisión",
    "fecha de emisión",
    "fecha de emision",
    "fait à",
    "fait a",
)

DEFAULT_CARE_WINDOW_CUES: tuple[str, ...] = (
    "care",
    "admission",
    "visit",
    "discharge",
    "consulta",
    "hospitalisation",
    "hospitalization",
    "hospitalized",
    "hospitalize",
    "pris en charge",
    "tratamiento",
    "treatment",
    "attending",
    "ricovero",
    "ricoverata",
    "ricoverato",
    "ricoverati",
    "dimesso",
    "dimessa",
    "dimessi",
    "ingreso",
    "alta",
)

DEFAULT_DOB_CUES: tuple[str, ...] = (
    "nata",
    "nato",
    "nati",
    "born",
    "birth",
    "dob",
    "d.o.b",
    "nacimiento",
    "geboren",
    "geburt",
    # Phrase form — bare "né"/"née" normalize to "ne" and false-positive on French negation.
    "né le",
    "née le",
    "ne le",
    "nascida",
    "nascido",
)

DEFAULT_MEDICAL_MENTION_CUES: tuple[str, ...] = (
    "medical",
    "hospital",
    "hospitalisation",
    "hospitalization",
    "doctor",
    "physician",
    "clinic",
    "illness",
    "diagnosis",
    "diagnosed",
    "sick",
    "surgery",
    "surgical",
    "médical",
    "medicale",
    "hôpital",
    "hopital",
    "médecin",
    "clinique",
    "médico",
    "medico",
    "hospitalización",
    "hospitalizacion",
    "enfermedad",
    "medizin",
    "arzt",
    "krankenhaus",
    "erkrankung",
)

_WHITESPACE = re.compile(r"\s+")


def normalize_cue_text(text: str) -> str:
    """Casefold and strip combining accents for language-robust cue matching.

    :param text: Raw OCR or narrative text.
    :return: Normalized string with collapsed whitespace.
    """
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return _WHITESPACE.sub(" ", stripped.casefold()).strip()


def text_mentions_any(text: str, cues: Sequence[str]) -> bool:
    """True when any cue appears in ``text`` after normalization.

    Multi-word cues match as substrings. Single-token cues require a word
    boundary so short tokens like ``alta`` do not hit unrelated words.

    :param text: Haystack text (OCR or description).
    :param cues: Vocabulary phrases from config (order irrelevant).
    :return: Whether at least one cue matches.
    """
    haystack = normalize_cue_text(text)
    if not haystack:
        return False
    for cue in cues:
        needle = normalize_cue_text(cue)
        if not needle:
            continue
        if " " in needle:
            if needle in haystack:
                return True
            continue
        if re.search(rf"(?<!\w){re.escape(needle)}(?!\w)", haystack):
            return True
    return False


def text_mentions_any_near(
    text: str,
    start: int,
    end: int,
    cues: Sequence[str],
    *,
    window: int = 40,
) -> bool:
    """True when any cue appears near a character span in ``text``.

    :param text: Full haystack text.
    :param start: Span start index.
    :param end: Span end index.
    :param cues: Vocabulary phrases from config.
    :param window: Characters of left/right context to inspect.
    :return: Whether a cue matches inside the window.
    """
    left = max(0, start - window)
    right = min(len(text), end + window)
    return text_mentions_any(text[left:right], cues)
