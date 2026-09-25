from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from compliance.config import AnalysisConfig, CheckingConfig, ClassificationConfig, load_config
from compliance.llm import CaseClassifier, ClassificationResult, Classifier

_MINIMAL_CHECKING_YAML = """
checking:
  model: test-model
  containment_prompt: |
    check containment
  contradicts_prompt: |
    check contradicts
"""

_MINIMAL_ANALYSIS_YAML = """
analysis:
  coverage:
    labels: [Trip cancellation or rescheduling, Personal Effects, Missed Departure or Missed Connection]
    other_label: "None"
    model: test-model
    prompt: |
      classify coverage
  cancellation_reason:
    labels: [Jury duty, Medical emergency]
    other_label: "None"
    model: test-model
    prompt: |
      classify reason
  cancellation_document:
    labels: [medical certificate]
    other_label: "None"
    model: test-model
    prompt: |
      classify cancel doc
  personal_effects_document:
    labels: [Proof of theft, loss, or damage]
    other_label: "None"
    model: test-model
    prompt: |
      classify pe doc
  missed_departure_document:
    labels: [Proof of booking]
    other_label: "None"
    model: test-model
    prompt: |
      classify missed doc
"""


def test_load_config_reads_document_formats(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
preprocessing:
  data_dir: data
  document_formats: [webp, jpg, png]
  confidence_threshold: 0.7
  preprocessed_dir: data/preprocessed
  results_dir: data/results
extraction:
  model: test-model
  prompt: |
    extract things
classification:
  labels: [Trip cancellation or rescheduling, Personal Effects, Missed Departure or Missed Connection]
  other_label: Other
  model: test-model
  prompt: |
    classify things
checking:
  model: test-model
  containment_prompt: |
    check containment
  contradicts_prompt: |
    check contradicts
"""
        + _MINIMAL_ANALYSIS_YAML,
        encoding="utf-8",
    )
    config = load_config(config_path)
    assert config.preprocessing.document_formats == ["webp", "jpg", "png"]
    assert config.preprocessing.confidence_threshold == 0.7
    assert config.preprocessing.data_dir == "data"


def test_load_config_reads_extraction_model_and_prompt() -> None:
    config = load_config("config.yaml")
    assert config.extraction.model
    assert "Extract booking/travel fields" in config.extraction.prompt
    assert "omit unknowns" in config.extraction.prompt


def test_load_config_reads_preprocessed_dir() -> None:
    config = load_config("config.yaml")
    assert config.preprocessing.data_dir == "data/raw"
    assert config.preprocessing.preprocessed_dir == "data/preprocessed"
    assert config.preprocessing.results_dir == "data/results"


def test_load_config_reads_artifact_names() -> None:
    config = load_config("config.yaml")
    artifacts = config.preprocessing.artifacts
    assert artifacts.description == "description.txt"
    assert artifacts.answer == "answer.json"
    assert artifacts.predicted_answer == "predicted_answer.json"
    assert artifacts.document_metadata == "document_metadata.json"
    assert artifacts.supporting_document == "supporting_document.md"
    assert artifacts.supporting_documents == "supporting_documents.md"


def test_load_config_benford_disabled_by_default() -> None:
    config = load_config("config.yaml")
    assert config.benford.enabled is False
    assert config.benford.block_size == 8
    assert config.benford.chi_squared_threshold == 15.51


def test_load_config_reads_classification_section() -> None:
    config = load_config("config.yaml")
    assert len(config.classification.labels) >= 3
    assert config.classification.other_label
    assert config.classification.model
    assert config.classification.prompt.strip()


def test_load_config_reads_checking_section() -> None:
    config = load_config("config.yaml")
    assert config.checking.model
    assert config.checking.containment_prompt.strip()
    assert config.checking.contradicts_prompt.strip()


def test_load_config_reads_analysis_section() -> None:
    config = load_config("config.yaml")
    stages = (
        config.analysis.coverage,
        config.analysis.cancellation_reason,
        config.analysis.cancellation_document,
        config.analysis.personal_effects_document,
        config.analysis.missed_departure_document,
    )
    for stage in stages:
        assert len(stage.labels) >= 1
        assert stage.other_label
        assert stage.model
        assert stage.prompt.strip()
    assert "Trip cancellation or rescheduling" in config.analysis.coverage.labels


def test_analysis_coverage_other_label_is_none() -> None:
    config = load_config("config.yaml")
    assert config.analysis.coverage.other_label == "None"
    assert config.classification.other_label == "Other"


def test_analysis_result_artifact_name_externalized() -> None:
    config = load_config("config.yaml")
    assert config.preprocessing.artifacts.analysis_result == "analysis_result.json"


def test_load_config_reads_ocr_retry_section() -> None:
    config = load_config("config.yaml")
    assert config.ocr_retry.enabled is True
    assert config.ocr_retry.model
    assert config.ocr_retry.prompt.strip()


def test_load_config_reads_classification_labels_and_other() -> None:
    config = load_config("config.yaml")
    labels = config.classification.labels
    assert "Trip cancellation or rescheduling" in labels
    assert "Personal Effects" in labels
    assert "Missed Departure or Missed Connection" in labels
    assert config.classification.other_label.strip()


def test_load_config_missing_classification_section_raises(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
preprocessing:
  data_dir: data
  document_formats: [webp]
  confidence_threshold: 0.7
  preprocessed_dir: data/preprocessed
  results_dir: data/results
extraction:
  model: test-model
  prompt: extract
"""
        + _MINIMAL_CHECKING_YAML,
        encoding="utf-8",
    )
    with pytest.raises(ValidationError):
        load_config(config_path)


def test_public_exports_include_classifier_and_classification_config() -> None:
    assert issubclass(Classifier, object)
    assert issubclass(CaseClassifier, Classifier)
    assert ClassificationResult is not None
    assert ClassificationConfig is not None
    assert CheckingConfig is not None
    assert AnalysisConfig is not None


def test_load_config_missing_file_raises(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist.yaml"
    with pytest.raises(FileNotFoundError, match="Config file not found"):
        load_config(missing)
