from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from compliance.config.settings import (
    AnalysisConfig,
    AppConfig,
    CheckingConfig,
    ClassificationConfig,
    ExtractionConfig,
    PreprocessingConfig,
)

_XFAIL_WAVE0 = pytest.mark.xfail(
    strict=False,
    reason="Wave 0 stub — implemented in 04-02/04-03",
)


def _analysis_config() -> AnalysisConfig:
    coverage = ClassificationConfig(
        labels=[
            "Trip cancellation or rescheduling",
            "Personal Effects",
            "Missed Departure or Missed Connection",
        ],
        other_label="None",
        model="test-model",
        prompt="classify coverage",
    )
    cancellation_reason = ClassificationConfig(
        labels=[
            "Jury duty",
            "Medical emergency",
            "Theft or criminal incident",
            "Other specified personal emergencies",
        ],
        other_label="None",
        model="test-model",
        prompt="classify reason",
    )
    cancellation_document = ClassificationConfig(
        labels=["medical certificate", "police report", "jury summon letter"],
        other_label="None",
        model="test-model",
        prompt="classify cancel doc",
    )
    personal_effects_document = ClassificationConfig(
        labels=["Proof of theft, loss, or damage"],
        other_label="None",
        model="test-model",
        prompt="classify pe doc",
    )
    missed_departure_document = ClassificationConfig(
        labels=[
            "Incident report or documentation explaining the cause of delay",
            "Proof of booking",
        ],
        other_label="None",
        model="test-model",
        prompt="classify missed doc",
    )
    return AnalysisConfig(
        coverage=coverage,
        cancellation_reason=cancellation_reason,
        cancellation_document=cancellation_document,
        personal_effects_document=personal_effects_document,
        missed_departure_document=missed_departure_document,
    )


def _config(
    data_dir: Path,
    *,
    preprocessed_dir: Path | str | None = None,
    results_dir: Path | str | None = None,
) -> AppConfig:
    """Build AppConfig with checking + analysis for ClaimPipeline stubs.

    :param data_dir: Temporary claim data root used as preprocessing.data_dir.
    :param preprocessed_dir: Optional preprocessed mirror root.
    :param results_dir: Optional analysis/results root.
    :return: Typed AppConfig suitable for unit tests without live Ollama.
    """
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
            labels=[
                "Trip cancellation or rescheduling",
                "Personal Effects",
                "Missed Departure or Missed Connection",
            ],
            other_label="Other",
            model="test-model",
            prompt="classify",
        ),
        checking=CheckingConfig(
            model="test-model",
            containment_prompt="containment",
            contradicts_prompt="contradicts",
        ),
        analysis=_analysis_config(),
    )


@_XFAIL_WAVE0
def test_coverage_node(tmp_path: Path) -> None:
    """R011: coverage classifier runs on description.txt via injectable chat_fn."""
    config = _config(tmp_path)
    chat_fn = MagicMock()  # R016: inject MagicMock chat_fn — no live Ollama
    raise AssertionError(
        f"ClaimPipeline coverage node not implemented (config={config.analysis.coverage.labels}, chat={chat_fn})"
    )


@_XFAIL_WAVE0
def test_routes_cancellation_to_reason(tmp_path: Path) -> None:
    """R012: trip-cancellation coverage routes to cancellation_reason classifier."""
    config = _config(tmp_path)
    chat_fn = MagicMock()
    raise AssertionError(
        f"cancellation→reason routing not implemented (chat_fn={chat_fn}, "
        f"labels={config.analysis.cancellation_reason.labels})"
    )


@_XFAIL_WAVE0
def test_routes_personal_effects(tmp_path: Path) -> None:
    """R013: Personal Effects coverage routes to personal_effects_document."""
    config = _config(tmp_path)
    chat_fn = MagicMock()
    raise AssertionError(
        f"personal-effects routing not implemented (chat_fn={chat_fn}, "
        f"labels={config.analysis.personal_effects_document.labels})"
    )


@_XFAIL_WAVE0
def test_routes_missed_departure(tmp_path: Path) -> None:
    """R013: Missed Departure coverage routes to missed_departure_document."""
    config = _config(tmp_path)
    chat_fn = MagicMock()
    raise AssertionError(
        f"missed-departure routing not implemented (chat_fn={chat_fn}, "
        f"labels={config.analysis.missed_departure_document.labels})"
    )


@_XFAIL_WAVE0
def test_checker_node(tmp_path: Path) -> None:
    """R014: Checker containment/contradicts run after document classification."""
    config = _config(tmp_path)
    chat_fn = MagicMock()
    raise AssertionError(
        f"checker node not implemented (checking.model={config.checking.model}, chat_fn={chat_fn})"
    )


@_XFAIL_WAVE0
def test_refuses_unsafe_claim_dir_name(tmp_path: Path) -> None:
    """R010/T-04-01: claim_dir.name with path separators or .. raises before I/O."""
    config = _config(tmp_path)
    raise AssertionError(
        f"path-safety refusal not implemented (results_dir={config.preprocessing.results_dir})"
    )


@_XFAIL_WAVE0
def test_unit_path_uses_injected_chat_fn(tmp_path: Path) -> None:
    """R016: unit path injects MagicMock chat_fn; never calls live Ollama."""
    config = _config(tmp_path)
    chat_fn = MagicMock(name="injected_chat_fn")
    raise AssertionError(
        f"ClaimPipeline injectable chat_fn seam not implemented (chat_fn={chat_fn}, "
        f"analysis_result={config.preprocessing.artifacts.analysis_result})"
    )
