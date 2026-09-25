from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class PreprocessedArtifactNames(BaseModel):
    """Filenames written under each mirrored claim output directory.

    :param description: Claim letter text artifact.
    :param answer: Ground-truth answer JSON artifact.
    :param predicted_answer: Pipeline-predicted decision JSON (when available).
    :param analysis_result: Claim-analysis JSON artifact under results_dir.
    :param supporting_document: Docling-extracted document content as markdown.
    :param supporting_documents: Booking/internal markdown artifact.
    :param document_metadata: Per-document DocumentMetaData JSON artifact.
    """

    description: str = "description.txt"
    answer: str = "answer.json"
    predicted_answer: str = "predicted_answer.json"
    analysis_result: str = "analysis_result.json"
    supporting_document: str = "supporting_document.md"
    supporting_documents: str = "supporting_documents.md"
    document_metadata: str = "document_metadata.json"


class PreprocessingConfig(BaseModel):
    """Preprocessing pipeline settings loaded from config.yaml.

    :param data_dir: Root directory containing claim folders.
    :param document_formats: File extensions routed through FormatConverter/Docling.
    :param confidence_threshold: Below this OCR confidence, flag human_in_the_loop.
    :param preprocessed_dir: Output root for the mirrored preprocessed claim tree.
    :param results_dir: Output root for pipeline predictions (predicted_answer).
    :param artifacts: Filenames for mirrored preprocessed outputs and predictions.
    """

    data_dir: str
    document_formats: list[str]
    confidence_threshold: float
    preprocessed_dir: str
    results_dir: str
    artifacts: PreprocessedArtifactNames = Field(default_factory=PreprocessedArtifactNames)


class ExtractionConfig(BaseModel):
    """LLM extraction settings for InformationExtractor.

    :param model: LLM model name used for structured field extraction.
    :param prompt: System/instruction prompt for extraction.
    """

    model: str
    prompt: str


class ClassificationConfig(BaseModel):
    """LLM case-classification settings for CaseClassifier.

    :param labels: Coverage class names the classifier may return.
    :param other_label: Fallback label when no coverage class fits.
    :param model: LLM model name used for classification.
    :param prompt: System/instruction prompt for classification.
    """

    labels: list[str]
    other_label: str
    model: str
    prompt: str


class CheckingConfig(BaseModel):
    """LLM claim-checking settings for Checker containment and contradiction modes.

    :param model: LLM model name used when deterministic containment misses.
    :param containment_prompt: System prompt for containment / entailment checks.
    :param contradicts_prompt: System prompt for contradiction checks.
    """

    model: str
    containment_prompt: str
    contradicts_prompt: str


class AnalysisConfig(BaseModel):
    """Multi-stage claim-analysis classifier settings for ClaimPipeline.

    Each stage reuses ClassificationConfig (labels, other_label, model, prompt).

    :param coverage: Coverage-type classifier on description text.
    :param cancellation_reason: Cancellation-reason classifier (trip-cancellation path).
    :param cancellation_document: Supporting-document type on the cancellation path.
    :param personal_effects_document: Document type for personal-effects coverage.
    :param missed_departure_document: Document type for missed-departure coverage.
    """

    coverage: ClassificationConfig
    cancellation_reason: ClassificationConfig
    cancellation_document: ClassificationConfig
    personal_effects_document: ClassificationConfig
    missed_departure_document: ClassificationConfig


class BenfordConfig(BaseModel):
    """Benford's Law analysis settings for image forensic checks.

    :param enabled: When False, DocumentReader skips Benford entirely (default for
        this project's synthetic claim images). Set True for real-world scans.
    :param block_size: Side length of the square DCT block (pixels).
    :param chi_squared_threshold: Maximum chi-squared statistic for conformity (8 dof).
    """

    enabled: bool = False
    block_size: int = 8
    chi_squared_threshold: float = 15.51


class ExtractionFailureConfig(BaseModel):
    """Thresholds for detecting unusable Docling OCR text.

    :param min_substantive_chars: Minimum non-noise characters required for usable OCR.
    :param min_words: Minimum alphabetic word tokens (length ≥ 3) required.
    """

    min_substantive_chars: int = 40
    min_words: int = 5


class LoggingConfig(BaseModel):
    """Application logging defaults for the CLI entrypoint.

    :param level: Logging level name (e.g. ``INFO``, ``DEBUG``).
    :param format: ``logging.basicConfig`` format string.
    """

    level: str = "INFO"
    format: str = "%(asctime)s %(levelname)s [%(name)s] %(message)s"


class EvaluationConfig(BaseModel):
    """Prediction-evaluation settings for scoring predicted vs ground-truth answers.

    :param labels: Decision vocabulary for confusion-matrix axes and macro F1.
    :param metrics_artifact: Filename for the batch metrics JSON under results_dir.
    """

    labels: list[str]
    metrics_artifact: str


class OcrRetryConfig(BaseModel):
    """Vision-model OCR retry after ExtractionFailure flags Docling text as unusable.

    :param enabled: When False, DocumentReader skips the vision retry path.
    :param model: Ollama vision model name (config only — never hardcode in source).
    :param prompt: Instruction to transcribe the document image into clean text.
    """

    enabled: bool = False
    model: str = ""
    prompt: str = ""


class AppConfig(BaseModel):
    """Top-level application configuration.

    :param preprocessing: Document discovery and Docling-related settings.
    :param extraction: LLM model and prompt for description extraction.
    :param classification: LLM model, labels, and prompt for case classification.
    :param checking: LLM model and prompts for claim containment/contradiction checks.
    :param analysis: Multi-stage claim-analysis classifier taxonomies and prompts.
    :param benford: DCT-based Benford's Law image forensics parameters.
    :param extraction_failure: Thresholds for unusable Docling OCR detection.
    :param ocr_retry: Optional vision OCR retry after faulty Docling extraction.
    :param logging: CLI logging level and format.
    :param evaluation: Labels and metrics artifact for prediction evaluation.
    """

    preprocessing: PreprocessingConfig
    extraction: ExtractionConfig
    classification: ClassificationConfig
    checking: CheckingConfig
    analysis: AnalysisConfig
    evaluation: EvaluationConfig
    benford: BenfordConfig = BenfordConfig()
    extraction_failure: ExtractionFailureConfig = Field(
        default_factory=ExtractionFailureConfig
    )
    ocr_retry: OcrRetryConfig = Field(default_factory=OcrRetryConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)


def load_config(path: str | Path = "config.yaml") -> AppConfig:
    """Load and validate application config from a YAML file.

    :param path: Path to the YAML config file.
    :return: Typed AppConfig covering preprocessing, extraction, classification,
        checking, and analysis.
    :raises FileNotFoundError: If the config file does not exist.
    :raises ValueError: If required sections or fields are missing/invalid.
    """
    config_path = Path(path)
    if not config_path.is_file():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    raw: dict[str, Any] = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    return AppConfig.model_validate(raw)
