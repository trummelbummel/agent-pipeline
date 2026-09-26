"""Shared fixtures for Claims API tests."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from compliance.config.settings import (
    AnalysisConfig,
    AppConfig,
    CheckingConfig,
    ClassificationConfig,
    EvaluationConfig,
    ExtractionConfig,
    PreprocessingConfig,
)

ApiConfigFactory = Callable[..., AppConfig]


@pytest.fixture
def compact_analysis_config() -> AnalysisConfig:
    """Provide the compact analysis vocabulary used by basic API tests."""
    stage = ClassificationConfig(
        labels=["1", "2", "3"],
        other_label="False",
        model="test-model",
        prompt="classify",
    )
    return AnalysisConfig(
        coverage=stage,
        cancellation_reason=stage,
        cancellation_document=stage,
        personal_effects_document=stage,
        missed_departure_document=stage,
    )


@pytest.fixture
def cancellation_analysis_config() -> AnalysisConfig:
    """Provide labeled cancellation analysis stages for decision-path tests."""
    coverage = ClassificationConfig(
        labels=["1", "2", "3"],
        other_label="False",
        model="test-model",
        prompt="classify coverage",
        label_names={
            "1": "Trip cancellation or rescheduling",
            "2": "Personal Effects",
            "3": "Missed Departure or Missed Connection",
        },
    )
    cancellation_reason = ClassificationConfig(
        labels=["1", "2", "3", "4"],
        other_label="False",
        model="test-model",
        prompt="classify reason",
        label_names={
            "1": "Jury duty",
            "2": "Medical emergency",
            "3": "Theft or criminal incident",
            "4": "Other specified personal emergencies",
        },
    )
    cancellation_document = ClassificationConfig(
        labels=["1", "2", "3"],
        other_label="False",
        model="test-model",
        prompt="classify cancel doc",
        label_names={
            "1": "medical certificate",
            "2": "police report",
            "3": "jury summon letter",
        },
    )
    document_stage = ClassificationConfig(
        labels=["1"],
        other_label="False",
        model="test-model",
        prompt="classify",
        label_names={"1": "Proof of theft, loss, or damage"},
    )
    return AnalysisConfig(
        coverage=coverage,
        cancellation_reason=cancellation_reason,
        cancellation_document=cancellation_document,
        personal_effects_document=document_stage,
        missed_departure_document=document_stage,
    )


@pytest.fixture
def api_config_factory(
    compact_analysis_config: AnalysisConfig,
) -> ApiConfigFactory:
    """Build API test configuration while preserving caller-selected roots.

    :param compact_analysis_config: Default analysis stages for basic API tests.
    :return: Function-scoped factory for isolated API configurations.
    """

    def _factory(
        data_dir: Path,
        *,
        preprocessed_dir: Path | str | None = None,
        results_dir: Path | str | None = None,
        analysis: AnalysisConfig | None = None,
    ) -> AppConfig:
        return AppConfig(
            preprocessing=PreprocessingConfig(
                data_dir=str(data_dir),
                document_formats=["webp", "jpg", "jpeg", "png", "pdf"],
                confidence_threshold=0.7,
                preprocessed_dir=str(preprocessed_dir or data_dir / "preprocessed"),
                results_dir=str(results_dir or data_dir / "results"),
            ),
            extraction=ExtractionConfig(model="test-model", prompt="extract fields"),
            classification=ClassificationConfig(
                labels=["1", "2", "3"],
                other_label="False",
                model="test-model",
                prompt="classify",
            ),
            checking=CheckingConfig(
                model="test-model",
                containment_prompt="containment",
                contradicts_prompt="contradicts",
                identity_prompt="identity",
                healthy_prompt="healthy",
                authenticity_prompt="authenticity",
                incomplete_prompt="incomplete",
            ),
            analysis=analysis or compact_analysis_config,
            evaluation=EvaluationConfig(
                labels=["APPROVE", "DENY", "UNCERTAIN"],
                metrics_artifact="evaluation_metrics.json",
            ),
        )

    return _factory


def _chat_response(payload: dict[str, Any]) -> SimpleNamespace:
    return SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))


@pytest.fixture
def cancellation_chat_fn() -> MagicMock:
    """Provide a fresh seven-response cancellation-path LLM mock."""
    return MagicMock(
        side_effect=[
            _chat_response(
                {
                    "labels": ["1"],
                    "probabilities": {"1": 0.9, "False": 0.1},
                }
            ),
            _chat_response(
                {
                    "labels": ["2"],
                    "probabilities": {"2": 0.85, "False": 0.15},
                }
            ),
            _chat_response(
                {
                    "labels": ["1"],
                    "probabilities": {"1": 0.8, "False": 0.2},
                }
            ),
            _chat_response({"result": True}),
            _chat_response({"result": False}),
            _chat_response({"result": True}),
            _chat_response({"result": False}),
        ]
    )
