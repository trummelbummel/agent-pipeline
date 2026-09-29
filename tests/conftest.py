from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Protocol
from unittest.mock import MagicMock

import pytest

from compliance.config.settings import (
    AnalysisConfig,
    AppConfig,
    CheckingConfig,
    ClassificationConfig,
    CoverageClassificationConfig,
    EvaluationConfig,
    ExtractionConfig,
    OcrRetryConfig,
    PreprocessingConfig,
)
from compliance.models.claim import BookingData, DocumentData, DocumentMetaData
from compliance.preprocessing.description import DescriptionReader
from compliance.preprocessing.extractor import InformationExtractor


class MinimalAnalysisConfigFactory(Protocol):
    def __call__(self) -> AnalysisConfig: ...


class MinimalAppConfigFactory(Protocol):
    def __call__(
        self,
        data_dir: Path,
        *,
        preprocessed_dir: Path | str = "data/preprocessed",
        results_dir: Path | str = "data/results",
        extraction_prompt: str = "extract fields",
        evaluation: EvaluationConfig | None = None,
        analysis: AnalysisConfig | None = None,
        classification: ClassificationConfig | None = None,
        ocr_retry: OcrRetryConfig | None = None,
    ) -> AppConfig: ...


def build_minimal_app_config(
    data_dir: Path,
    *,
    analysis: AnalysisConfig,
    preprocessed_dir: Path | str = "data/preprocessed",
    results_dir: Path | str = "data/results",
    extraction_prompt: str = "extract fields",
    evaluation: EvaluationConfig | None = None,
    classification: ClassificationConfig | None = None,
    ocr_retry: OcrRetryConfig | None = None,
) -> AppConfig:
    """Build a minimal AppConfig with caller-selected roots and optional overrides.

    :param data_dir: Root directory used as ``preprocessing.data_dir``.
    :param analysis: Analysis stage configuration.
    :param preprocessed_dir: Mirrored preprocessed output root.
    :param results_dir: Analysis/results output root.
    :param extraction_prompt: Prompt string for ``extraction.prompt``.
    :param evaluation: Optional evaluation config; defaults to APPROVE/DENY/UNCERTAIN.
    :param classification: Optional top-level classification config; defaults to labels ``["1"]``.
    :param ocr_retry: Optional OCR retry config; defaults to ``OcrRetryConfig()``.
    :return: Typed AppConfig suitable for unit tests without live Ollama.
    """
    evaluation_config = evaluation or EvaluationConfig(
        labels=["APPROVE", "DENY", "UNCERTAIN"],
        metrics_artifact="evaluation_metrics.json",
    )
    classification_config = classification or ClassificationConfig(
        labels=["1"],
        other_label="False",
        model="test-model",
        prompt="classify",
    )
    return AppConfig(
        preprocessing=PreprocessingConfig(
            data_dir=str(data_dir),
            document_formats=["webp", "jpg", "jpeg", "png", "pdf"],
            confidence_threshold=0.7,
            preprocessed_dir=str(preprocessed_dir),
            results_dir=str(results_dir),
        ),
        extraction=ExtractionConfig(
            model="test-model",
            prompt=extraction_prompt,
        ),
        classification=classification_config,
        checking=CheckingConfig(
            model="test-model",
            containment_prompt="containment",
            contradicts_prompt="contradicts",
            identity_prompt="identity",
            healthy_prompt="healthy",
            authenticity_prompt="authenticity",
            incomplete_prompt="incomplete",
        ),
        analysis=analysis,
        evaluation=evaluation_config,
        ocr_retry=ocr_retry if ocr_retry is not None else OcrRetryConfig(),
    )


class MockDescriptionReaderFactory(Protocol):
    def __call__(self, fields: dict[str, Any] | None = None) -> DescriptionReader: ...


class MockDocumentReaderFactory(Protocol):
    def __call__(
        self,
        docs: dict[str, DocumentData] | None = None,
        *,
        default: DocumentData | None = None,
    ) -> MagicMock: ...


class ChatReturningFactory(Protocol):
    def __call__(self, payload: dict[str, Any] | str) -> MagicMock: ...


class CancellationChatFactory(Protocol):
    def __call__(self, checker_results: Sequence[dict[str, Any]]) -> MagicMock: ...


@pytest.fixture
def cancellation_analysis_config() -> AnalysisConfig:
    """Provide labeled cancellation analysis stages for decision-path tests."""
    coverage = CoverageClassificationConfig(
        labels=["1", "2", "3"],
        other_label="False",
        model="test-model",
        prompt="classify coverage",
        label_names={
            "1": "Trip cancellation or rescheduling",
            "2": "Personal Effects",
            "3": "Missed Departure or Missed Connection",
        },
        branches={
            "1": "cancellation",
            "2": "personal_effects",
            "3": "missed_departure",
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
def minimal_analysis_config_factory() -> MinimalAnalysisConfigFactory:
    """Build the shared minimal analysis configuration."""

    def _build() -> AnalysisConfig:
        stage = ClassificationConfig(
            labels=["1"],
            other_label="False",
            model="test-model",
            prompt="classify",
        )
        coverage = CoverageClassificationConfig(
            labels=["1"],
            other_label="False",
            model="test-model",
            prompt="classify",
            branches={"1": "cancellation"},
        )
        return AnalysisConfig(
            coverage=coverage,
            cancellation_reason=stage,
            cancellation_document=stage,
            personal_effects_document=stage,
            missed_departure_document=stage,
        )

    return _build


@pytest.fixture
def minimal_app_config_factory(
    minimal_analysis_config_factory: MinimalAnalysisConfigFactory,
) -> MinimalAppConfigFactory:
    """Build minimal application configurations with caller-selected roots.

    :param minimal_analysis_config_factory: Factory for the shared analysis stages.
    """

    def _build(
        data_dir: Path,
        *,
        preprocessed_dir: Path | str = "data/preprocessed",
        results_dir: Path | str = "data/results",
        extraction_prompt: str = "extract fields",
        evaluation: EvaluationConfig | None = None,
        analysis: AnalysisConfig | None = None,
        classification: ClassificationConfig | None = None,
        ocr_retry: OcrRetryConfig | None = None,
    ) -> AppConfig:
        return build_minimal_app_config(
            data_dir,
            preprocessed_dir=preprocessed_dir,
            results_dir=results_dir,
            extraction_prompt=extraction_prompt,
            evaluation=evaluation,
            analysis=analysis or minimal_analysis_config_factory(),
            classification=classification,
            ocr_retry=ocr_retry,
        )

    return _build


@pytest.fixture
def mock_description_reader_factory() -> MockDescriptionReaderFactory:
    """Build description readers backed by fresh chat mocks."""

    def _build(fields: dict[str, Any] | None = None) -> DescriptionReader:
        payload = fields or {}
        chat = MagicMock(return_value=SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload))))
        extractor = InformationExtractor(
            target_model=BookingData,
            model_name="test-model",
            prompt="p",
            chat_fn=chat,
        )
        return DescriptionReader(extractor=extractor)

    return _build


@pytest.fixture
def mock_document_reader_factory() -> MockDocumentReaderFactory:
    """Build document readers with mapping and default document behavior."""

    def _build(
        docs: dict[str, DocumentData] | None = None,
        *,
        default: DocumentData | None = None,
    ) -> MagicMock:
        mapping = docs or {}
        default_document = (
            default
            if default is not None
            else DocumentData(
                raw_text="x",
                metadata=DocumentMetaData(extraction_probability=0.9),
            )
        )
        reader = MagicMock()

        def _read(path: Path) -> DocumentData:
            if path.name in mapping:
                return mapping[path.name]
            return default_document

        reader.read.side_effect = _read
        return reader

    return _build


@pytest.fixture
def chat_returning_factory() -> ChatReturningFactory:
    """Build fresh chat mocks returning JSON or raw string content."""

    def _build(payload: dict[str, Any] | str) -> MagicMock:
        content = payload if isinstance(payload, str) else json.dumps(payload)
        response = SimpleNamespace(message=SimpleNamespace(content=content))
        return MagicMock(return_value=response)

    return _build


@pytest.fixture
def cancellation_chat_factory() -> CancellationChatFactory:
    """Build cancellation-path chat mocks with caller-selected checker results."""

    def _response(payload: dict[str, Any]) -> SimpleNamespace:
        return SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))

    def _build(checker_results: Sequence[dict[str, Any]]) -> MagicMock:
        classification_payloads = [
            {
                "labels": ["1"],
                "probabilities": {"1": 0.9, "False": 0.1},
            },
            {
                "labels": ["2"],
                "probabilities": {"2": 0.85, "False": 0.15},
            },
            {
                "labels": ["1"],
                "probabilities": {"1": 0.8, "False": 0.2},
            },
        ]
        return MagicMock(
            side_effect=[
                *(_response(payload) for payload in classification_payloads),
                *(_response(payload) for payload in checker_results),
            ]
        )

    return _build
