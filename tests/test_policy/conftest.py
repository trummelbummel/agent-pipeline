from __future__ import annotations

import pytest

from compliance.config.settings import CoverageClassificationConfig


@pytest.fixture
def coverage_config() -> CoverageClassificationConfig:
    """Coverage stage matching the claim-pipeline taxonomy used by SR-004 tests.

    :return: CoverageClassificationConfig with branches for codes 1/2/3.
    """
    return CoverageClassificationConfig(
        labels=["1", "2", "3", "False"],
        other_label="False",
        model="test-model",
        prompt="classify coverage",
        label_names={
            "1": "Trip cancellation or rescheduling",
            "2": "Personal Effects",
            "3": "Missed Departure or Missed Connection",
            "False": "False",
        },
        branches={
            "1": "cancellation",
            "2": "personal_effects",
            "3": "missed_departure",
        },
    )
