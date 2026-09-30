from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import date

from compliance.preprocessing.markdown import MarkdownPreprocessor
from compliance.text_cues import (
    DEFAULT_CARE_WINDOW_CUES,
    DEFAULT_DOB_CUES,
    DEFAULT_ISSUE_DATE_CUES,
    text_mentions_any,
    text_mentions_any_near,
)

# Calendar-date token patterns (order: ISO first, then day-first numerics, then English).
_DATE_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_DATE_DMY = re.compile(r"\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})\b")
_DATE_DMONTH_Y = re.compile(
    r"\b(\d{1,2})\s+"
    r"(January|February|March|April|May|June|July|August|September|October|"
    r"November|December)\s+(\d{4})\b",
    re.IGNORECASE,
)
_DATE_MONTH_D_Y = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|October|"
    r"November|December)\s+(\d{1,2}),?\s+(\d{4})\b",
    re.IGNORECASE,
)
_MONTH_NUM: dict[str, int] = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _parse_calendar_date(raw: str) -> date | None:
    """Parse the first calendar date from a booking/OCR string.

    Supports ISO ``YYYY-MM-DD``, day-first ``DD/MM/YYYY`` (also ``-`` / ``.``),
    and English month names. Trailing time suffixes are ignored (ISO match first).

    :param raw: Free-text value that may contain a date.
    :return: Parsed ``date``, or None when unparseable.
    """
    if not raw or not isinstance(raw, str):
        return None
    text = raw.strip()
    match = _DATE_ISO.search(text)
    if match:
        return _safe_date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    match = _DATE_DMONTH_Y.search(text)
    if match:
        return _safe_date(
            int(match.group(3)),
            _MONTH_NUM[match.group(2).lower()],
            int(match.group(1)),
        )
    match = _DATE_MONTH_D_Y.search(text)
    if match:
        return _safe_date(
            int(match.group(3)),
            _MONTH_NUM[match.group(1).lower()],
            int(match.group(2)),
        )
    match = _DATE_DMY.search(text)
    if match:
        return _safe_date(int(match.group(3)), int(match.group(2)), int(match.group(1)))
    return None


def _unique_calendar_dates(text: str) -> set[date]:
    """Collect distinct calendar days mentioned in free text.

    :param text: OCR or narrative text that may contain multiple date tokens.
    :return: Set of successfully parsed calendar dates.
    """
    if not text:
        return set()
    found: set[date] = set()
    for match in _DATE_ISO.finditer(text):
        parsed = _safe_date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        if parsed is not None:
            found.add(parsed)
    for match in _DATE_DMONTH_Y.finditer(text):
        parsed = _safe_date(
            int(match.group(3)),
            _MONTH_NUM[match.group(2).lower()],
            int(match.group(1)),
        )
        if parsed is not None:
            found.add(parsed)
    for match in _DATE_MONTH_D_Y.finditer(text):
        parsed = _safe_date(
            int(match.group(3)),
            _MONTH_NUM[match.group(1).lower()],
            int(match.group(2)),
        )
        if parsed is not None:
            found.add(parsed)
    for match in _DATE_DMY.finditer(text):
        parsed = _safe_date(int(match.group(3)), int(match.group(2)), int(match.group(1)))
        if parsed is not None:
            found.add(parsed)
    return found


def _booking_fields(supporting_documents_text: str) -> dict[str, str]:
    """Extract canonical BookingData fields from booking markdown.

    :param supporting_documents_text: ``supporting_documents.md`` contents.
    :return: Dict of BookingData field name → string value.
    """
    if not supporting_documents_text:
        return {}
    return MarkdownPreprocessor().preprocess(supporting_documents_text)


def _reference_today(supporting_documents_text: str, *, fallback: date) -> date:
    """Resolve reference today from booking ``current_date``, else ``fallback``.

    :param supporting_documents_text: Booking markdown text.
    :param fallback: Clock date when booking has no parseable current_date.
    :return: Calendar date used as the proximity reference.
    """
    fields = _booking_fields(supporting_documents_text)
    current_raw = fields.get("current_date")
    if current_raw:
        parsed = _parse_calendar_date(str(current_raw))
        if parsed is not None:
            return parsed
    return fallback


def _departure_beyond_days(
    *,
    supporting_documents_text: str,
    description_text: str,
    today: date,
    within_days: int,
) -> bool:
    """True when an upcoming departure is farther than ``within_days`` ahead.

    Used on the medical path only: a flight still more than ``n`` days out makes
    recovery / ability-to-fly unclear → UNCERTAIN. Past departures and flights
    within the near window continue through the remaining checkers (healthy /
    identity DENY must still run on already-traveled trips).

    Departure source priority: booking markdown ``departure`` via
    ``MarkdownPreprocessor``; else first parseable date in ``description_text``.
    Unparseable departure → False.

    :param supporting_documents_text: Booking/internal markdown.
    :param description_text: Claim narrative fallback for departure date.
    :param today: Reference today (injected; pipeline resolves from booking).
    :param within_days: Inclusive near-window; UNCERTAIN only when
        ``(departure - today).days`` is strictly greater than this value.
    :return: Whether far-departure UNCERTAIN should fire.
    """
    fields = _booking_fields(supporting_documents_text)
    departure: date | None = None
    raw_dep = fields.get("departure")
    if raw_dep:
        departure = _parse_calendar_date(str(raw_dep))
    if departure is None:
        departure = _parse_calendar_date(description_text)
    if departure is None:
        return False
    return (departure - today).days > within_days


def _month_delta(left: date, right: date) -> int:
    """Absolute calendar-month distance between two dates.

    :param left: First date.
    :param right: Second date.
    :return: Absolute difference in year/month components
        (``|(y1 - y2) * 12 + (m1 - m2)|``); day-of-month is ignored.
    """
    return abs((left.year - right.year) * 12 + (left.month - right.month))


def _dates_with_match_spans(text: str) -> list[tuple[date, int, int]]:
    """Parse calendar dates with their character spans in ``text``.

    :param text: OCR or narrative text.
    :return: ``(date, start, end)`` for each successful parse (duplicates kept).
    """
    if not text:
        return []
    found: list[tuple[date, int, int]] = []
    for match in _DATE_ISO.finditer(text):
        parsed = _safe_date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        if parsed is not None:
            found.append((parsed, match.start(), match.end()))
    for match in _DATE_DMONTH_Y.finditer(text):
        parsed = _safe_date(
            int(match.group(3)),
            _MONTH_NUM[match.group(2).lower()],
            int(match.group(1)),
        )
        if parsed is not None:
            found.append((parsed, match.start(), match.end()))
    for match in _DATE_MONTH_D_Y.finditer(text):
        parsed = _safe_date(
            int(match.group(3)),
            _MONTH_NUM[match.group(1).lower()],
            int(match.group(2)),
        )
        if parsed is not None:
            found.append((parsed, match.start(), match.end()))
    for match in _DATE_DMY.finditer(text):
        parsed = _safe_date(int(match.group(3)), int(match.group(2)), int(match.group(1)))
        if parsed is not None:
            found.append((parsed, match.start(), match.end()))
    return found


def _is_dob_context(
    text: str,
    start: int,
    end: int,
    dob_cues: Sequence[str],
    *,
    window: int = 40,
) -> bool:
    """True when a birth/DOB cue appears near the date span.

    :param text: Full OCR text.
    :param start: Date token start index.
    :param end: Date token end index.
    :param dob_cues: Config vocabulary for birth/DOB markers.
    :param window: Characters of left/right context to inspect.
    :return: Whether this date should be treated as a date of birth.
    """
    return text_mentions_any_near(text, start, end, dob_cues, window=window)


def _suspicious_dating(
    supporting_document_text: str,
    *,
    today: date,
    max_month_delta: int,
    consider_within_years: int = 5,
    issue_date_cues: Sequence[str] = DEFAULT_ISSUE_DATE_CUES,
    care_window_cues: Sequence[str] = DEFAULT_CARE_WINDOW_CUES,
    dob_cues: Sequence[str] = DEFAULT_DOB_CUES,
) -> bool:
    """True when OCR dating is implausible vs reference today or care window.

    Uses existing calendar parsers only — no ad-hoc date parser. Eligible dates:
    within ``consider_within_years`` of ``today``, and not adjacent to a birth/DOB
    cue from ``dob_cues``. Farther or DOB-cued dates are ignored.

    Fires when:
    - an eligible OCR date differs from ``today`` by at least
      ``max_month_delta`` months (inclusive) and is either in the future or the
      OCR text matches an ``issue_date_cues`` phrase (not a bare image ``Stamp``
      label), or
    - issue-date wording co-occurs with a ``care_window_cues`` phrase and the
      span between the earliest and latest eligible OCR dates is at least
      ``max_month_delta`` months (same-episode admission+discharge does not fire).

    :param supporting_document_text: Medical/supporting OCR markdown.
    :param today: Reference today (booking ``current_date`` or clock).
    :param max_month_delta: Inclusive absolute month threshold from config.
    :param consider_within_years: Inclusive year window around ``today``;
        dates outside are ignored as history.
    :param issue_date_cues: Issue/stamp vocabulary from ``checking.issue_date_cues``.
    :param care_window_cues: Care/admission vocabulary from ``checking.care_window_cues``.
    :param dob_cues: Birth/DOB vocabulary from ``checking.dob_cues``.
    :return: Whether suspicious-dating UNCERTAIN should fire.
    """
    dated_spans = _dates_with_match_spans(supporting_document_text)
    dates = {
        d
        for d, start, end in dated_spans
        if abs(d.year - today.year) <= consider_within_years
        and not _is_dob_context(supporting_document_text, start, end, dob_cues)
    }
    if not dates:
        return False
    has_issue_stamp = text_mentions_any(supporting_document_text, issue_date_cues)
    for d in dates:
        if _month_delta(d, today) < max_month_delta:
            continue
        # Future dates, or issue/issued-labeled past dates with large month skew.
        if d > today or has_issue_stamp:
            return True
    if not has_issue_stamp or not text_mentions_any(supporting_document_text, care_window_cues):
        return False
    if len(dates) < 2:
        return False
    earliest, latest = min(dates), max(dates)
    return _month_delta(earliest, latest) >= max_month_delta
