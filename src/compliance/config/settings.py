from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel


class PreprocessingConfig(BaseModel):
    """Preprocessing pipeline settings loaded from config.yaml.

    :param data_dir: Root directory containing claim folders.
    :param output_filename: Filename written per claim after processing.
    :param document_formats: File extensions routed through FormatConverter/Docling.
    :param confidence_threshold: Below this OCR confidence, flag human_in_the_loop.
    """

    data_dir: str
    output_filename: str
    document_formats: list[str]
    confidence_threshold: float


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


class AppConfig(BaseModel):
    """Top-level application configuration.

    :param preprocessing: Document discovery and Docling-related settings.
    :param extraction: LLM model and prompt for description extraction.
    :param classification: LLM model, labels, and prompt for case classification.
    """

    preprocessing: PreprocessingConfig
    extraction: ExtractionConfig
    classification: ClassificationConfig


def load_config(path: str | Path = "config.yaml") -> AppConfig:
    """Load and validate application config from a YAML file.

    :param path: Path to the YAML config file.
    :return: Typed AppConfig covering preprocessing, extraction, and classification.
    :raises FileNotFoundError: If the config file does not exist.
    :raises ValueError: If required sections or fields are missing/invalid.
    """
    config_path = Path(path)
    if not config_path.is_file():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    raw: dict[str, Any] = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    return AppConfig.model_validate(raw)
