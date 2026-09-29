"""Shared fixtures for Claims API tests."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest
from conftest import MinimalAppConfigFactory

from compliance.config.settings import AnalysisConfig, AppConfig, ClassificationConfig, CoverageClassificationConfig

if TYPE_CHECKING:
    from conftest import CancellationChatFactory

ApiConfigFactory = Callable[..., AppConfig]

_API_CLASSIFICATION = ClassificationConfig(
    labels=["1", "2", "3"],
    other_label="False",
    model="test-model",
    prompt="classify",
)


@pytest.fixture
def compact_analysis_config() -> AnalysisConfig:
    """Provide the compact analysis vocabulary used by basic API tests."""
    stage = ClassificationConfig(
        labels=["1", "2", "3"],
        other_label="False",
        model="test-model",
        prompt="classify",
    )
    coverage = CoverageClassificationConfig(
        labels=["1", "2", "3"],
        other_label="False",
        model="test-model",
        prompt="classify",
        branches={
            "1": "cancellation",
            "2": "personal_effects",
            "3": "missed_departure",
        },
    )
    return AnalysisConfig(
        coverage=coverage,
        cancellation_reason=stage,
        cancellation_document=stage,
        personal_effects_document=stage,
        missed_departure_document=stage,
    )


@pytest.fixture
def api_config_factory(
    compact_analysis_config: AnalysisConfig,
    minimal_app_config_factory: MinimalAppConfigFactory,
) -> ApiConfigFactory:
    """Build API test configuration while preserving caller-selected roots.

    :param compact_analysis_config: Default analysis stages for basic API tests.
    :param minimal_app_config_factory: Shared AppConfig builder from root conftest.
    :return: Function-scoped factory for isolated API configurations.
    """

    def _factory(
        data_dir: Path,
        *,
        preprocessed_dir: Path | str | None = None,
        results_dir: Path | str | None = None,
        analysis: AnalysisConfig | None = None,
    ) -> AppConfig:
        return minimal_app_config_factory(
            data_dir,
            preprocessed_dir=preprocessed_dir or data_dir / "preprocessed",
            results_dir=results_dir or data_dir / "results",
            analysis=analysis or compact_analysis_config,
            classification=_API_CLASSIFICATION,
        )

    return _factory


@pytest.fixture
def cancellation_chat_fn(
    cancellation_chat_factory: CancellationChatFactory,
) -> MagicMock:
    """Provide a fresh seven-response cancellation-path LLM mock."""
    return cancellation_chat_factory([
        {"result": False},
        {"name": "Ada Lovelace"},
        {"name": "Ada Lovelace"},
        {"result": False},
        {"result": False},
        {"result": False},
    ])
