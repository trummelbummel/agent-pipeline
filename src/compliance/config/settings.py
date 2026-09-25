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
    :param supporting_document: Docling-extracted document content as markdown.
    :param supporting_documents: Booking/internal markdown artifact.
    :param document_metadata: Per-document DocumentMetaData JSON artifact.
    """

    description: str = "description.txt"
    answer: str = "answer.json"
    predicted_answer: str = "predicted_answer.json"
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
    :param benford: DCT-based Benford's Law image forensics parameters.
    :param ocr_retry: Optional vision OCR retry after faulty Docling extraction.
    """

    preprocessing: PreprocessingConfig
    extraction: ExtractionConfig
    classification: ClassificationConfig
    checking: CheckingConfig
    benford: BenfordConfig = BenfordConfig()
    ocr_retry: OcrRetryConfig = Field(default_factory=OcrRetryConfig)


def load_config(path: str | Path = "config.yaml") -> AppConfig:
    """Load and validate application config from a YAML file.

    :param path: Path to the YAML config file.
    :return: Typed AppConfig covering preprocessing, extraction, classification, and checking.
    :raises FileNotFoundError: If the config file does not exist.
    :raises ValueError: If required sections or fields are missing/invalid.
    """
    config_path = Path(path)
    if not config_path.is_file():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    raw: dict[str, Any] = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    return AppConfig.model_validate(raw)
