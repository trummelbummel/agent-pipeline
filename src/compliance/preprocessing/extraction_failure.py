from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field

from compliance.config.settings import ExtractionFailureConfig
from compliance.models.claim import is_nan_scalar

# Docling figure captions / placeholders that are not substantive OCR body text
_FIGURE_NOISE = re.compile(
    r"(?:<!--\s*image\s*-->|"
    r"\b(?:logo|signature|stamp|icon|photograph|picture|image|qr[\s_-]?code|"
    r"bar[\s_-]?code|page[\s_-]?thumbnail)\b)",
    re.IGNORECASE,
)
_WHITESPACE = re.compile(r"\s+")
_WORD_TOKEN = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ]{3,}")


class ExtractionFailureResult(BaseModel):
    """Outcome of an ExtractionFailure check.

    :param faulty: Whether the extraction should be treated as failed.
    :param reasons: Machine-readable reason codes when faulty.
    """

    model_config = ConfigDict(strict=True)

    faulty: bool = Field(description="True when OCR text is unusable")
    reasons: list[str] = Field(
        default_factory=list,
        description="Machine-readable failure reason codes",
    )


class ExtractionFailure:
    """Detect false / unusable Docling document extractions.

    Catches empty outputs (claim 8 ``_none_``) and near-empty OCR that is mostly
    figure captions or garbage (claim 5), which must trigger human-in-the-loop.
    """

    def __init__(self, config: ExtractionFailureConfig | None = None) -> None:
        """Create a detector with substantive-content thresholds from config.

        :param config: Thresholds from ``config.yaml``; defaults when omitted (tests).
        """
        cfg = config or ExtractionFailureConfig()
        self.min_substantive_chars = cfg.min_substantive_chars
        self.min_words = cfg.min_words

    def evaluate(self, raw_text: object) -> ExtractionFailureResult:
        """Judge whether extracted document text is usable.

        :param raw_text: Docling markdown/text, or a missing NaN sentinel.
        :return: Faulty flag plus reason codes when the extraction fails.
        """
        text = self._normalized_text(raw_text)
        if text is None:
            return ExtractionFailureResult(faulty=True, reasons=["empty_text"])

        reasons = self._insufficiency_reasons(self._substantive_text(text))
        if reasons:
            return ExtractionFailureResult(faulty=True, reasons=reasons)
        return ExtractionFailureResult(faulty=False, reasons=[])

    @staticmethod
    def _normalized_text(raw_text: object) -> str | None:
        if is_nan_scalar(raw_text) or raw_text is None or not isinstance(raw_text, str):
            return None
        stripped = raw_text.strip()
        if not stripped or stripped.lower() in {"_none_", "none"}:
            return None
        return stripped

    def _insufficiency_reasons(self, substantive: str) -> list[str]:
        reasons: list[str] = []
        if len(substantive) < self.min_substantive_chars:
            reasons.append("insufficient_substantive_text")
        if len(_WORD_TOKEN.findall(substantive)) < self.min_words:
            reasons.append("insufficient_words")
        return reasons

    @staticmethod
    def _substantive_text(text: str) -> str:
        without_noise = _FIGURE_NOISE.sub(" ", text)
        return _WHITESPACE.sub(" ", without_noise).strip()
