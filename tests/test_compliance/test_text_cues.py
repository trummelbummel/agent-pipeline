"""Unit tests for accent-insensitive cue vocabulary matching."""

from __future__ import annotations

from compliance.text_cues import (
    DEFAULT_CARE_WINDOW_CUES,
    DEFAULT_DOB_CUES,
    DEFAULT_ISSUE_DATE_CUES,
    normalize_cue_text,
    text_mentions_any,
    text_mentions_any_near,
)


def test_normalize_strips_accents_and_case() -> None:
    """NFKD + casefold collapses Fait à / FAIT A."""
    assert normalize_cue_text("Fait à PARIS") == "fait a paris"
    assert normalize_cue_text("  Hôpital\n") == "hopital"


def test_text_mentions_french_issue_and_care_cues() -> None:
    """French certificate closing and care phrases match the dating defaults."""
    assert text_mentions_any("Fait à PARIS le 17/11/2023", DEFAULT_ISSUE_DATE_CUES)
    assert text_mentions_any("Fait a PARIS le 17/11/2023", DEFAULT_ISSUE_DATE_CUES)
    assert text_mentions_any("pris en charge en hospitalisation", DEFAULT_CARE_WINDOW_CUES)
    assert not text_mentions_any("il a fait une erreur", DEFAULT_ISSUE_DATE_CUES)


def test_text_mentions_any_near_window() -> None:
    """DOB cue near a date span is detected inside the local window."""
    text = "Patient nata il 30-07-1980 then later text."
    start = text.index("30-07-1980")
    end = start + len("30-07-1980")
    assert text_mentions_any_near(text, start, end, ["nata"])
    assert not text_mentions_any_near(text, start, end, ["issued"], window=5)


def test_dob_cue_ne_le_does_not_match_french_negation() -> None:
    """Accent-stripped né must not fire on 'il ne veut pas'."""
    assert text_mentions_any("Patient né le 05.08.1999", DEFAULT_DOB_CUES)
    assert not text_mentions_any("il ne veut pas voyager", DEFAULT_DOB_CUES)
