"""Deterministic date gates that short-circuit LLM checks to UNCERTAIN.

A gate that fires records its flag and skips every LLM check for the claim.
Gates run only when their name is in the claim's ``CheckerRuleSet.applicable``.
"""

from __future__ import annotations

from datetime import date
from typing import Protocol

from compliance.claim_dates import _departure_beyond_days, _suspicious_dating
from compliance.config.settings import CheckingConfig
from compliance.llm.checks import CheckContext
from compliance.policy.rules import GatedCheck

__all__ = [
    "DepartureGate",
    "Gate",
    "SuspiciousDatingGate",
    "gates_from_config",
]


class Gate(Protocol):
    """Deterministic early-UNCERTAIN gate evaluated before LLM checks."""

    name: GatedCheck

    def fires(self, context: CheckContext, *, today: date) -> bool:
        """Decide whether the gate short-circuits this claim to UNCERTAIN.

        :param context: Claim texts.
        :param today: Reference today resolved from the booking.
        :return: True when the gate fires.
        """
        ...


class DepartureGate:
    """Upcoming departure farther than ``within_days`` ahead → UNCERTAIN."""

    name: GatedCheck = "departure"

    def __init__(self, within_days: int) -> None:
        """Bind the near-departure window.

        :param within_days: Inclusive window; only departures strictly beyond
            it fire. Past departures never fire.
        """
        self._within_days = within_days

    def fires(self, context: CheckContext, *, today: date) -> bool:
        """True when the booking/description departure is beyond the window.

        :param context: Claim texts (booking first, description as fallback).
        :param today: Reference today resolved from the booking.
        :return: Whether the far-departure gate fires.
        """
        return _departure_beyond_days(
            supporting_documents_text=context.booking,
            description_text=context.description,
            today=today,
            within_days=self._within_days,
        )


class SuspiciousDatingGate:
    """Implausible OCR document dating vs reference today → UNCERTAIN."""

    name: GatedCheck = "suspicious_dating"

    def __init__(
        self,
        max_month_delta: int,
        consider_within_years: int,
        *,
        issue_date_cues: list[str],
        care_window_cues: list[str],
        dob_cues: list[str],
    ) -> None:
        """Bind the dating thresholds and cue vocabularies.

        :param max_month_delta: Inclusive month skew that counts as suspicious.
        :param consider_within_years: Only OCR dates within this many years of
            today are eligible.
        :param issue_date_cues: Issue/stamp phrases from checking config.
        :param care_window_cues: Care/admission phrases from checking config.
        :param dob_cues: Birth/DOB phrases from checking config.
        """
        self._max_month_delta = max_month_delta
        self._consider_within_years = consider_within_years
        self._issue_date_cues = issue_date_cues
        self._care_window_cues = care_window_cues
        self._dob_cues = dob_cues

    def fires(self, context: CheckContext, *, today: date) -> bool:
        """True when the supporting-document OCR dating is implausible.

        :param context: Claim texts (``document`` is read).
        :param today: Reference today resolved from the booking.
        :return: Whether the suspicious-dating gate fires.
        """
        return _suspicious_dating(
            context.document,
            today=today,
            max_month_delta=self._max_month_delta,
            consider_within_years=self._consider_within_years,
            issue_date_cues=self._issue_date_cues,
            care_window_cues=self._care_window_cues,
            dob_cues=self._dob_cues,
        )


def gates_from_config(checking: CheckingConfig) -> tuple[Gate, ...]:
    """Build the configured date gates once.

    :param checking: Checking config holding the date-gate thresholds.
    :return: Departure gate (only when ``departure_uncertain_enabled``) and
        suspicious-dating gate.
    """
    dating = SuspiciousDatingGate(
        checking.suspicious_dating_max_month_delta,
        checking.suspicious_dating_consider_within_years,
        issue_date_cues=checking.issue_date_cues,
        care_window_cues=checking.care_window_cues,
        dob_cues=checking.dob_cues,
    )
    if not checking.departure_uncertain_enabled:
        return (dating,)
    return (DepartureGate(checking.departure_uncertain_within_days), dating)
