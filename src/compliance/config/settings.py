from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, model_validator

# Shared vocabulary between the config contract and pipeline routing branches so the two cannot drift.
CoverageRoute = Literal["cancellation", "personal_effects", "missed_departure"]


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


class CoverageClassificationConfig(ClassificationConfig):
    """Coverage-stage classifier with an authoritative label→branch map (D-01).

    ``branches`` maps each positive coverage label CODE to its routing branch.
    The mapping is authoritative: the order of ``labels`` carries no routing meaning.

    :param branches: Map from coverage label code to routing branch
        (``cancellation`` / ``personal_effects`` / ``missed_departure``).
    """

    branches: dict[str, CoverageRoute]

    @model_validator(mode="after")
    def _validated_branch_map(self) -> CoverageClassificationConfig:
        """Reject unrouted positives, unknown keys, and duplicate branch values.

        :return: Self after the branch map passes all checks.
        """
        positives = set(self.positive_labels())
        branch_keys = set(self.branches)
        unrouted = sorted(positives - branch_keys)
        unknown = sorted(branch_keys - positives)
        if unrouted or unknown:
            raise CoverageBranchMappingError(unrouted=unrouted, unknown=unknown, allowed=sorted(positives))
        seen: dict[str, list[str]] = {}
        for code, route in self.branches.items():
            seen.setdefault(route, []).append(code)
        for duplicate_route, codes in seen.items():
            if len(codes) > 1:
                raise DuplicateCoverageBranchError(branch=duplicate_route, codes=sorted(codes))
        return self


class TransportRetryConfig(BaseModel):
    """Bounded retry for checker chat transport failures (SR-008).

    :param max_retries: Extra attempts after the first try (total attempts =
        ``max_retries + 1``). Exhaustion records the check as ERROR.
    :param backoff_seconds: Base delay for exponential backoff between attempts
        (``backoff_seconds * 2**attempt``); no sleep after the final failure.
    """

    max_retries: int = Field(default=2, ge=0)
    backoff_seconds: float = Field(default=1.0, ge=0.0)


class CheckingConfig(BaseModel):
    """LLM claim-checking settings for Checker modes.

    :param model: LLM model name used when deterministic containment misses.
    :param containment_prompt: System prompt for containment / entailment checks.
    :param contradicts_prompt: System prompt for contradiction checks.
    :param identity_prompt: System prompt that extracts a person name as JSON
        ``{"name": "..."}`` / ``{"name": null}`` for identity edit-distance matching.
    :param healthy_prompt: System prompt for healthy / fit certificate detection.
    :param authenticity_prompt: System prompt for document authenticity / format
        checks (True = not authentic / wrong format → violation).
    :param incomplete_prompt: System prompt for incomplete medical-document field
        checks (True = required fields missing → violation).
    :param identity_max_edit_distance: Inclusive Levenshtein threshold on
        lowercased extracted names; distance ≤ this value → identity match.
    :param departure_uncertain_enabled: When False, skip the medical far-departure
        UNCERTAIN gate entirely.
    :param departure_uncertain_within_days: Inclusive near-window in days; on the
        medical path, when |departure - reference today| is strictly greater than
        this value, analysis yields UNCERTAIN (``departure_within_days``) without
        running LLM checkers. Departures within the window continue through
        the remaining checkers. Ignored when ``departure_uncertain_enabled`` is False.
    :param suspicious_dating_max_month_delta: Inclusive absolute month threshold;
        when any OCR calendar date differs from reference today by at least this
        many months, analysis yields UNCERTAIN (``checker_suspicious_dating``).
        Default 1 month.
    :param suspicious_dating_consider_within_years: Only OCR dates within this
        many years of reference today are eligible for suspicious dating;
        farther dates are ignored as date-of-birth / history.
    :param transport_retry: Retry/backoff for checker chat transport failures
        (connection / timeout / server error); exhaustion → CheckOutcome.ERROR.
    """

    model: str
    containment_prompt: str
    contradicts_prompt: str
    identity_prompt: str
    healthy_prompt: str
    authenticity_prompt: str
    incomplete_prompt: str
    identity_max_edit_distance: int = 3
    departure_uncertain_enabled: bool = False
    departure_uncertain_within_days: int = 14
    suspicious_dating_max_month_delta: int = 1
    suspicious_dating_consider_within_years: int = 2
    transport_retry: TransportRetryConfig = Field(default_factory=TransportRetryConfig)


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
    Coverage additionally carries a named ``branches`` map (D-01).

    :param coverage: Coverage-type classifier on description text, with named
        label→branch routing map.
    :param cancellation_reason: Cancellation-reason classifier (trip-cancellation path).
    :param cancellation_document: Supporting-document type on the cancellation path.
    :param personal_effects_document: Document type for personal-effects coverage.
    :param missed_departure_document: Document type for missed-departure coverage.
    :param required_documents: Acceptable document codes per coverage/reason path.
    """

    coverage: CoverageClassificationConfig
    cancellation_reason: ClassificationConfig
    cancellation_document: ClassificationConfig
    personal_effects_document: ClassificationConfig
    missed_departure_document: ClassificationConfig
    required_documents: RequiredDocumentsConfig = Field(default_factory=RequiredDocumentsConfig)


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

    labels: list[str] = Field(default_factory=lambda: ["APPROVE", "DENY", "UNCERTAIN"])
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
    :param signature_confidence: Accept threshold for YOLO max box confidence;
        below this (or no boxes) sets ``human_in_the_loop`` after verify.
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
    extraction_failure: ExtractionFailureConfig = Field(default_factory=ExtractionFailureConfig)
    ocr_retry: OcrRetryConfig = Field(default_factory=OcrRetryConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)


class ConfigFileNotFoundError(FileNotFoundError):
    """The configured application config file path does not exist."""

    def __init__(self, path: Path) -> None:
        """Build the not-found message from the resolved config path.

        :param path: Config file path that was checked and not found.
        """
        super().__init__(f"Config file not found: {path}")


class CoverageBranchMappingError(ValueError):
    """Coverage ``branches`` keys do not match the positive label vocabulary."""

    def __init__(self, unrouted: list[str], unknown: list[str], allowed: list[str]) -> None:
        """Name unrouted positives and/or unknown branch keys.

        :param unrouted: Positive labels missing from ``branches``.
        :param unknown: ``branches`` keys outside the positive vocabulary.
        :param allowed: The positive label set that keys must equal.
        """
        parts: list[str] = []
        if unrouted:
            parts.append(f"unrouted coverage codes {unrouted}")
        if unknown:
            parts.append(f"unknown branch keys {unknown} (allowed {allowed})")
        super().__init__(f"Invalid coverage.branches: {'; '.join(parts)}")


class DuplicateCoverageBranchError(ValueError):
    """Two coverage codes map to the same routing branch."""

    def __init__(self, branch: str, codes: list[str]) -> None:
        """Name the duplicated branch and the codes that share it.

        :param branch: Branch value claimed by more than one code.
        :param codes: Coverage codes that all map to ``branch``.
        """
        super().__init__(f"Duplicate coverage branch {branch!r} shared by codes {codes}")


def load_config(path: str | Path = "config.yaml") -> AppConfig:
    """Load and validate application config from a YAML file.

    :param path: Path to the YAML config file.
    :return: Typed AppConfig covering preprocessing, extraction, classification,
        checking, and analysis.
    :raises ConfigFileNotFoundError: If the config file does not exist (a
        ``FileNotFoundError`` subclass).
    :raises ValueError: If required sections or fields are missing/invalid.
    """
    config_path = Path(path)
    if not config_path.is_file():
        raise ConfigFileNotFoundError(config_path)

    raw: dict[str, Any] = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    return AppConfig.model_validate(raw)
