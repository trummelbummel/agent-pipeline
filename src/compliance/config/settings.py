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

    :param labels: Numeric (or other) class codes the classifier may return.
    :param other_label: Fallback label when no coverage class fits.
    :param model: LLM model name used for classification.
    :param prompt: System/instruction prompt for classification.
    :param label_names: Map from code → semantic display name for analysis artifacts.
    """

    labels: list[str]
    other_label: str
    model: str
    prompt: str
    label_names: dict[str, str] = Field(default_factory=dict)

    def resolve_label_names(self, codes: list[str]) -> list[str]:
        """Map classifier codes to semantic names; unknown codes pass through.

        :param codes: Raw label codes from the classifier (may include other_label).
        :return: Semantic names in the same order as ``codes``.
        """
        names = dict(self.label_names)
        names.setdefault(self.other_label, self.other_label)
        names.setdefault("False", "False")
        return [names.get(code, code) for code in codes]

    def abstention_labels(self) -> set[str]:
        """Labels that mean no positive class was chosen (``False`` abstention).

        :return: Set containing ``other_label`` and ``False`` when either is used.
        """
        return {self.other_label, "False"}

    def positive_labels(self) -> list[str]:
        """Class codes excluding confident-negative ``False``.

        :return: Labels used as real coverage/reason/document types.
        """
        return [label for label in self.labels if label != "False"]


class CheckingConfig(BaseModel):
    """LLM claim-checking settings for Checker modes.

    :param model: LLM model name used when deterministic containment misses.
    :param containment_prompt: System prompt for containment / entailment checks.
    :param contradicts_prompt: System prompt for contradiction checks.
    :param identity_prompt: System prompt for claimant-name vs document-name checks.
    :param healthy_prompt: System prompt for healthy / fit certificate detection.
    :param authenticity_prompt: System prompt for document authenticity / format
        checks (True = not authentic / wrong format → violation).
    :param incomplete_prompt: System prompt for incomplete medical-document field
        checks (True = required fields missing → violation); wired in a later plan.
    :param departure_uncertain_within_days: Inclusive absolute day window; when
        departure is within this many days of reference today, analysis yields
        UNCERTAIN (``departure_within_days``) without running LLM checkers.
    """

    model: str
    containment_prompt: str
    contradicts_prompt: str
    identity_prompt: str
    healthy_prompt: str
    authenticity_prompt: str
    incomplete_prompt: str
    departure_uncertain_within_days: int = 14


class RequiredDocumentsConfig(BaseModel):
    """Acceptable supporting-document codes per coverage / cancellation reason.

    Codes match ``analysis.*.labels`` (numeric strings). Missing documentation
    means the classified document type is outside the acceptable set for the claim.

    :param cancellation_by_reason: Map cancellation-reason code → acceptable
        cancellation-document codes (e.g. medical emergency ``"2"`` → ``["1"]``).
    :param personal_effects: Acceptable personal-effects document codes.
    :param missed_departure: Acceptable missed-departure document codes.
    :param signature_required_codes: Document codes that must have
        ``has_signature: true`` in ``document_metadata.json`` (e.g. medical
        certificate, hospital admission).
    :param identity_required_codes: Document codes that trigger booking-vs-OCR
        identity checks (typically medical certificate / hospital admission).
    """

    cancellation_by_reason: dict[str, list[str]] = Field(default_factory=dict)
    personal_effects: list[str] = Field(default_factory=list)
    missed_departure: list[str] = Field(default_factory=list)
    signature_required_codes: list[str] = Field(default_factory=list)
    identity_required_codes: list[str] = Field(default_factory=list)


class AnalysisConfig(BaseModel):
    """Multi-stage claim-analysis classifier settings for ClaimPipeline.

    Each stage reuses ClassificationConfig (labels, other_label, model, prompt).

    :param coverage: Coverage-type classifier on description text.
    :param cancellation_reason: Cancellation-reason classifier (trip-cancellation path).
    :param cancellation_document: Supporting-document type on the cancellation path.
    :param personal_effects_document: Document type for personal-effects coverage.
    :param missed_departure_document: Document type for missed-departure coverage.
    :param required_documents: Acceptable document codes per coverage/reason path.
    """

    coverage: ClassificationConfig
    cancellation_reason: ClassificationConfig
    cancellation_document: ClassificationConfig
    personal_effects_document: ClassificationConfig
    missed_departure_document: ClassificationConfig
    required_documents: RequiredDocumentsConfig = Field(
        default_factory=RequiredDocumentsConfig
    )

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
    :param confusion_matrix_artifact: Filename for the labeled matrix JSON under results_dir.
    :param visualization_artifact: Filename for the confusion-matrix PNG under results_dir.
    :param analysis_stats_artifact: Filename for aggregated analysis_result stats JSON.
    :param analysis_visualization_artifact: Filename for analysis stats bar-chart PNG.
    """

    labels: list[str] = Field(
        default_factory=lambda: ["APPROVE", "DENY", "UNCERTAIN"]
    )
    metrics_artifact: str = "evaluation_metrics.json"
    confusion_matrix_artifact: str = "confusion_matrix.json"
    visualization_artifact: str = "evaluation_visualization.png"
    analysis_stats_artifact: str = "analysis_stats.json"
    analysis_visualization_artifact: str = "analysis_stats_visualization.png"


class OcrRetryConfig(BaseModel):
    """Vision-model OCR retry and YOLO signature verify (preprocess only).

    Retry triggers are independent flags. ``DocumentReader`` retries text once when
    any enabled trigger matches the Docling ``DocumentMetaData``. When Docling
    reports ``has_signature=false``, an optional Ultralytics YOLO pass may set
    ``has_signature=true``. Analysis never re-runs OCR — it reads preprocessed
    artifacts only.

    :param enabled: When False, DocumentReader skips vision retry and signature verify.
    :param model: Ollama vision model name for text OCR retry (config only).
    :param prompt: Instruction to transcribe the document image into clean text.
    :param on_faulty_extraction: Retry when ``ExtractionFailure`` flags unusable OCR.
    :param on_low_confidence: Retry when ``extraction_probability`` is below
        ``preprocessing.confidence_threshold``.
    :param on_human_in_the_loop: Retry when ``human_in_the_loop`` is true.
    :param on_identity_unclear: During analysis, retry when identity returns
        ``unclear`` and preprocess did not already run a vision retry.
    :param on_missing_signature: When Docling leaves ``has_signature`` false, run
        YOLO signature detection on the document image.
    :param signature_model: HuggingFace repo id or local ``.pt`` path for YOLO weights.
    :param signature_weights: Filename inside the HF repo (ignored for local ``.pt``).
    :param signature_confidence: Minimum box confidence to treat as a signature.
    """

    enabled: bool = False
    model: str = ""
    prompt: str = ""
    on_faulty_extraction: bool = True
    on_low_confidence: bool = True
    on_human_in_the_loop: bool = True
    on_identity_unclear: bool = True
    on_missing_signature: bool = True
    signature_model: str = "tech4humans/yolov8s-signature-detector"
    signature_weights: str = "yolov8s.pt"
    signature_confidence: float = 0.25


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
    evaluation: EvaluationConfig = Field(default_factory=EvaluationConfig)
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
