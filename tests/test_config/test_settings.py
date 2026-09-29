from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from compliance.config import (
    AnalysisConfig,
    CheckingConfig,
    ClassificationConfig,
    CoverageClassificationConfig,
    load_config,
)
from compliance.llm import CaseClassifier, ClassificationResult, Classifier

_MINIMAL_EVALUATION_YAML = """
evaluation:
  labels: [APPROVE, DENY, UNCERTAIN]
  metrics_artifact: evaluation_metrics.json
"""

_MINIMAL_CHECKING_YAML = """
checking:
  model: test-model
  containment_prompt: |
    check containment
  contradicts_prompt: |
    check contradicts
  identity_prompt: |
    check identity
  healthy_prompt: |
    check healthy
  authenticity_prompt: |
    check authenticity
  incomplete_prompt: |
    check incomplete
"""

_MINIMAL_ANALYSIS_YAML = """
analysis:
  coverage:
    labels: ["1", "2", "3"]
    branches:
      "1": cancellation
      "2": personal_effects
      "3": missed_departure
    other_label: "False"
    model: test-model
    prompt: |
      classify coverage
  cancellation_reason:
    labels: ["1", "2"]
    other_label: "False"
    model: test-model
    prompt: |
      classify reason
  cancellation_document:
    labels: ["1"]
    other_label: "False"
    model: test-model
    prompt: |
      classify cancel doc
  personal_effects_document:
    labels: ["1"]
    other_label: "False"
    model: test-model
    prompt: |
      classify pe doc
  missed_departure_document:
    labels: ["1"]
    other_label: "False"
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
  labels: ["1", "2", "3"]
  other_label: "False"
  model: test-model
  prompt: |
    classify things
checking:
  model: test-model
  containment_prompt: |
    check containment
  contradicts_prompt: |
    check contradicts
  identity_prompt: |
    check identity
  healthy_prompt: |
    check healthy
  authenticity_prompt: |
    check authenticity
  incomplete_prompt: |
    check incomplete
"""
        + _MINIMAL_ANALYSIS_YAML
        + _MINIMAL_EVALUATION_YAML,
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
    assert "Extract the single person name" in config.checking.identity_prompt
    assert config.checking.identity_max_edit_distance == 3
    within_days = getattr(config.checking, "departure_uncertain_within_days", None)
    assert isinstance(within_days, int)
    assert within_days == 14
    assert config.checking.departure_uncertain_enabled is False


def test_load_config_reads_authenticity_and_incomplete_prompts() -> None:
    """checking.authenticity_prompt / incomplete_prompt must be non-empty (R027/R028)."""
    config = load_config("config.yaml")
    authenticity = getattr(config.checking, "authenticity_prompt", None)
    incomplete = getattr(config.checking, "incomplete_prompt", None)
    assert isinstance(authenticity, str) and authenticity.strip()
    assert isinstance(incomplete, str) and incomplete.strip()


def test_load_config_reads_suspicious_dating_max_month_delta() -> None:
    """checking.suspicious_dating_max_month_delta is a positive int (one-month default)."""
    config = load_config("config.yaml")
    delta = getattr(config.checking, "suspicious_dating_max_month_delta", None)
    assert isinstance(delta, int)
    assert delta >= 1
    assert delta == 1
    within = getattr(config.checking, "suspicious_dating_consider_within_years", None)
    assert within == 2


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
    assert "1" in config.analysis.coverage.labels
    assert "2" in config.analysis.coverage.labels
    assert "3" in config.analysis.coverage.labels
    assert "Trip cancellation or rescheduling" in config.analysis.coverage.prompt
    assert "Personal Effects" in config.analysis.coverage.prompt
    assert "Missed Departure or Missed Connection" in config.analysis.coverage.prompt
    assert "1" in config.analysis.cancellation_reason.labels
    assert "Jury duty" in config.analysis.cancellation_reason.prompt
    assert "1" in config.analysis.cancellation_document.labels
    assert "medical certificate" in config.analysis.cancellation_document.prompt
    assert "1" in config.analysis.personal_effects_document.labels
    assert "Proof of theft" in config.analysis.personal_effects_document.prompt
    assert "1" in config.analysis.missed_departure_document.labels
    assert "Incident report" in config.analysis.missed_departure_document.prompt
    assert "Proof of booking" in config.analysis.missed_departure_document.prompt


def test_analysis_coverage_other_label_is_false() -> None:
    config = load_config("config.yaml")
    assert config.analysis.coverage.other_label == "False"
    assert config.classification.other_label == "False"
    assert "False" in config.classification.labels
    assert "False" in config.analysis.coverage.labels
    assert "False" in config.analysis.cancellation_reason.labels
    assert config.analysis.coverage.abstention_labels() == {"False"}
    assert config.analysis.coverage.positive_labels() == ["1", "2", "3"]


def test_analysis_result_artifact_name_externalized() -> None:
    config = load_config("config.yaml")
    assert config.preprocessing.artifacts.analysis_result == "analysis_result.json"


def test_load_config_reads_evaluation_section() -> None:
    config = load_config("config.yaml")
    evaluation = getattr(config, "evaluation", None)
    assert evaluation is not None
    assert "APPROVE" in evaluation.labels
    assert "DENY" in evaluation.labels
    assert "UNCERTAIN" in evaluation.labels
    assert evaluation.metrics_artifact == "evaluation_metrics.json"
    assert evaluation.visualization_artifact == "evaluation_visualization.png"


def test_load_config_reads_ocr_retry_section() -> None:
    config = load_config("config.yaml")
    assert config.ocr_retry.enabled is True
    assert config.ocr_retry.model
    assert config.ocr_retry.prompt.strip()
    assert config.ocr_retry.on_faulty_extraction is True
    assert config.ocr_retry.on_low_confidence is True
    assert config.ocr_retry.on_human_in_the_loop is True
    assert config.ocr_retry.on_missing_signature is True
    assert config.ocr_retry.signature_model
    assert config.ocr_retry.signature_weights
    assert config.ocr_retry.signature_confidence > 0


def test_load_config_reads_classification_labels_and_other() -> None:
    config = load_config("config.yaml")
    labels = config.classification.labels
    assert "1" in labels
    assert "2" in labels
    assert "3" in labels
    assert "Trip cancellation or rescheduling" in config.classification.prompt
    assert "Personal Effects" in config.classification.prompt
    assert "Missed Departure or Missed Connection" in config.classification.prompt
    assert config.classification.other_label.strip()
    assert config.classification.label_names["1"] == "Trip cancellation or rescheduling"
    assert config.analysis.coverage.resolve_label_names(["1", "False"]) == [
        "Trip cancellation or rescheduling",
        "False",
    ]
    assert config.analysis.cancellation_reason.label_names["2"] == "Medical emergency"


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
        + _MINIMAL_CHECKING_YAML
        + _MINIMAL_EVALUATION_YAML,
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


def test_load_config_reads_coverage_branches() -> None:
    """analysis.coverage.branches is the authoritative label→branch map (D-01)."""
    config = load_config("config.yaml")
    assert config.analysis.coverage.branches == {
        "1": "cancellation",
        "2": "personal_effects",
        "3": "missed_departure",
    }


_COVERAGE_STAGE_KWARGS: dict[str, object] = {
    "labels": ["1", "2", "3"],
    "other_label": "False",
    "model": "test-model",
    "prompt": "classify coverage",
}


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        pytest.param(
            {"branches": {"1": "cancellation", "2": "personal_effects"}},
            r"unrouted|3",
            id="missing_branch",
        ),
        pytest.param(
            {
                "branches": {
                    "1": "cancellation",
                    "2": "personal_effects",
                    "3": "missed_departure",
                    "9": "cancellation",
                }
            },
            r"unknown|9",
            id="unknown_key",
        ),
        pytest.param(
            {
                "branches": {
                    "1": "cancellation",
                    "2": "cancellation",
                    "3": "missed_departure",
                }
            },
            r"duplicate|cancellation",
            id="duplicate_branch",
        ),
        pytest.param(
            {
                "branches": {
                    "1": "cancellation",
                    "2": "personal_effects",
                    "3": "not_a_branch",
                }
            },
            r"not_a_branch|Input should be",
            id="invalid_branch_value",
        ),
    ],
)
def test_invalid_coverage_branches_rejected(kwargs: dict[str, object], match: str) -> None:
    """Coverage branch map must be complete, exclusive, and use known branches."""
    with pytest.raises(ValidationError, match=match):
        CoverageClassificationConfig(**_COVERAGE_STAGE_KWARGS, **kwargs)  # type: ignore[arg-type]


def test_invalid_coverage_branches_absent_field_rejected(tmp_path: Path) -> None:
    """A coverage stage without branches fails as a missing required field."""
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
classification:
  labels: ["1", "2", "3"]
  other_label: "False"
  model: test-model
  prompt: classify
"""
        + _MINIMAL_CHECKING_YAML
        + """
analysis:
  coverage:
    labels: ["1", "2", "3"]
    other_label: "False"
    model: test-model
    prompt: |
      classify coverage
  cancellation_reason:
    labels: ["1", "2"]
    other_label: "False"
    model: test-model
    prompt: |
      classify reason
  cancellation_document:
    labels: ["1"]
    other_label: "False"
    model: test-model
    prompt: |
      classify cancel doc
  personal_effects_document:
    labels: ["1"]
    other_label: "False"
    model: test-model
    prompt: |
      classify pe doc
  missed_departure_document:
    labels: ["1"]
    other_label: "False"
    model: test-model
    prompt: |
      classify missed doc
"""
        + _MINIMAL_EVALUATION_YAML,
        encoding="utf-8",
    )
    with pytest.raises(ValidationError, match=r"branches"):
        load_config(config_path)


def _write_full_minimal_config(tmp_path: Path, *, extra_yaml: str = "") -> Path:
    """Write a loadable minimal AppConfig YAML, optionally appending extra YAML."""
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
classification:
  labels: ["1", "2", "3"]
  other_label: "False"
  model: test-model
  prompt: classify
"""
        + _MINIMAL_CHECKING_YAML
        + _MINIMAL_ANALYSIS_YAML
        + _MINIMAL_EVALUATION_YAML
        + extra_yaml,
        encoding="utf-8",
    )
    return config_path


@pytest.mark.parametrize(
    ("extra_yaml", "match"),
    [
        pytest.param("\nanalysys: {}\n", r"analysys", id="root_extra"),
        pytest.param(
            """
preprocessing:
  data_dir: data
  document_formats: [webp]
  confidence_threshold: 0.7
  preprocessed_dir: data/preprocessed
  results_dir: data/results
  artifacts:
    description: description.txt
    answer: answer.json
    predicted_answer: predicted_answer.json
    analysis_result: analysis_result.json
    supporting_document: supporting_document.md
    supporting_documents: supporting_documents.md
    document_metadata: document_metadata.json
    answr: wrong
extraction:
  model: test-model
  prompt: extract
classification:
  labels: ["1", "2", "3"]
  other_label: "False"
  model: test-model
  prompt: classify
"""
            + _MINIMAL_CHECKING_YAML
            + _MINIMAL_ANALYSIS_YAML
            + _MINIMAL_EVALUATION_YAML,
            r"answr",
            id="nested_artifacts_extra",
        ),
        pytest.param(
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
classification:
  labels: ["1", "2", "3"]
  other_label: "False"
  model: test-model
  prompt: classify
checking:
  model: test-model
  containment_prompt: check containment
  contradicts_prompt: check contradicts
  identity_prompt: check identity
  healthy_prompt: check healthy
  authenticity_prompt: check authenticity
  incomplete_prompt: check incomplete
  transport_retry:
    max_retries: 2
    backoff_seconds: 1.0
    max_retrys: 9
"""
            + _MINIMAL_ANALYSIS_YAML
            + _MINIMAL_EVALUATION_YAML,
            r"max_retrys",
            id="nested_transport_retry_extra",
        ),
    ],
)
def test_unknown_config_key_rejected(tmp_path: Path, extra_yaml: str, match: str) -> None:
    """Unknown keys at root or nested models fail load (D-02)."""
    if match == "analysys":
        config_path = _write_full_minimal_config(tmp_path, extra_yaml=extra_yaml)
    else:
        config_path = tmp_path / "config.yaml"
        config_path.write_text(extra_yaml, encoding="utf-8")
    with pytest.raises(ValidationError, match=match):
        load_config(config_path)


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        pytest.param(
            {"labels": ["1", "2", "1"], "other_label": "False", "model": "m", "prompt": "p"},
            r"Duplicate|1",
            id="duplicate_labels",
        ),
        pytest.param(
            {
                "labels": ["1"],
                "other_label": "False",
                "model": "m",
                "prompt": "p",
                "label_names": {"9": "unknown"},
            },
            r"Unknown label_names|9",
            id="unknown_label_names_key",
        ),
        pytest.param(
            {"labels": [], "other_label": "False", "model": "m", "prompt": "p"},
            r"non-empty|empty",
            id="empty_labels",
        ),
    ],
)
def test_invalid_label_vocabulary_rejected(kwargs: dict[str, object], match: str) -> None:
    """Duplicate, unknown label_names, and empty labels fail validation."""
    with pytest.raises(ValidationError, match=match):
        ClassificationConfig(**kwargs)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("factory", "kwargs"),
    [
        pytest.param(
            "preprocessing",
            {
                "data_dir": "d",
                "document_formats": ["webp"],
                "confidence_threshold": 1.5,
                "preprocessed_dir": "p",
                "results_dir": "r",
            },
            id="confidence_above_one",
        ),
        pytest.param(
            "preprocessing",
            {
                "data_dir": "d",
                "document_formats": ["webp"],
                "confidence_threshold": -0.1,
                "preprocessed_dir": "p",
                "results_dir": "r",
            },
            id="confidence_negative",
        ),
        pytest.param("ocr_retry", {"signature_confidence": 2.0}, id="signature_confidence_high"),
        pytest.param("benford", {"block_size": 0}, id="block_size_zero"),
        pytest.param("benford", {"chi_squared_threshold": 0}, id="chi_squared_zero"),
        pytest.param("checking", {"identity_max_edit_distance": -1}, id="identity_distance_negative"),
        pytest.param("extraction_failure", {"min_words": -1}, id="min_words_negative"),
    ],
)
def test_out_of_range_config_values_rejected(factory: str, kwargs: dict[str, object]) -> None:
    """Out-of-range numeric settings fail at model construction."""
    from compliance.config.settings import (
        BenfordConfig,
        CheckingConfig,
        ExtractionFailureConfig,
        OcrRetryConfig,
        PreprocessingConfig,
    )

    builders = {
        "preprocessing": PreprocessingConfig,
        "ocr_retry": OcrRetryConfig,
        "benford": BenfordConfig,
        "checking": lambda **kw: CheckingConfig(
            model="m",
            containment_prompt="c",
            contradicts_prompt="x",
            identity_prompt="i",
            healthy_prompt="h",
            authenticity_prompt="a",
            incomplete_prompt="n",
            **kw,
        ),
        "extraction_failure": ExtractionFailureConfig,
    }
    with pytest.raises(ValidationError):
        builders[factory](**kwargs)  # type: ignore[operator]
