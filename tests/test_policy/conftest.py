from __future__ import annotations

import pytest

from compliance.config.settings import (
    AnalysisConfig,
    CheckingConfig,
    ClassificationConfig,
    CoverageClassificationConfig,
    RequiredDocumentsConfig,
)


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


@pytest.fixture
def analysis_config(coverage_config: CoverageClassificationConfig) -> AnalysisConfig:
    """Full analysis config matching the claim-pipeline taxonomy.

    :param coverage_config: Shared coverage stage fixture.
    :return: AnalysisConfig with reason/document stages and required-documents.
    """
    cancellation_reason = ClassificationConfig(
        labels=["1", "2", "3", "4", "False"],
        other_label="False",
        model="test-model",
        prompt="classify reason",
        label_names={
            "1": "Jury duty",
            "2": "Medical emergency",
            "3": "Theft or criminal incident",
            "4": "Other specified personal emergencies",
            "False": "False",
        },
    )
    cancellation_document = ClassificationConfig(
        labels=["1", "2", "3", "4", "False"],
        other_label="False",
        model="test-model",
        prompt="classify cancel doc",
        label_names={
            "1": "medical certificate",
            "2": "police report",
            "3": "jury summon letter",
            "4": "hospital admission",
            "False": "False",
        },
    )
    personal_effects_document = ClassificationConfig(
        labels=["1", "False"],
        other_label="False",
        model="test-model",
        prompt="classify pe doc",
        label_names={"1": "Proof of theft, loss, or damage", "False": "False"},
    )
    missed_departure_document = ClassificationConfig(
        labels=["1", "2", "False"],
        other_label="False",
        model="test-model",
        prompt="classify missed doc",
        label_names={
            "1": "Incident report or documentation explaining the cause of delay",
            "2": "Proof of booking",
            "False": "False",
        },
    )
    return AnalysisConfig(
        coverage=coverage_config,
        cancellation_reason=cancellation_reason,
        cancellation_document=cancellation_document,
        personal_effects_document=personal_effects_document,
        missed_departure_document=missed_departure_document,
        required_documents=RequiredDocumentsConfig(
            cancellation_by_reason={
                "1": ["3"],
                "2": ["1", "4"],
                "3": ["2"],
                "4": ["1", "2", "3", "4"],
            },
            personal_effects=["1"],
            missed_departure=["1", "2"],
            signature_required_codes=["1", "4"],
            identity_required_codes=["1", "4"],
        ),
    )


@pytest.fixture
def checking_config() -> CheckingConfig:
    """Minimal checking config for policy unit tests.

    :return: CheckingConfig with test prompts and default date windows.
    """
    return CheckingConfig(
        model="test-model",
        containment_prompt="containment",
        contradicts_prompt="contradicts",
        identity_prompt="identity",
        healthy_prompt="healthy",
        authenticity_prompt="authenticity",
        incomplete_prompt="incomplete",
    )
