from __future__ import annotations

import logging
import math
from pathlib import Path

import numpy as np
from PIL import Image
from pydantic import BaseModel
from scipy.fft import dctn

from compliance.config.settings import BenfordConfig

logger = logging.getLogger(__name__)

_DIGITS = range(1, 10)
_BENFORD_EXPECTED = {d: math.log10(1 + 1 / d) for d in _DIGITS}


class BenfordResult(BaseModel):
    """Outcome of a Benford's Law analysis on image DCT coefficients.

    :param image_path: Path of the analysed image file.
    :param observed_frequencies: Measured first-significant-digit distribution (digits 1-9).
    :param expected_frequencies: Benford's theoretical distribution (digits 1-9).
    :param chi_squared: Chi-squared statistic comparing observed vs. expected.
    :param conformity: Whether the distribution conforms within the configured threshold.
    :param total_coefficients: Number of non-zero DCT coefficients analysed.
    """

    image_path: str
    observed_frequencies: dict[int, float]
    expected_frequencies: dict[int, float]
    chi_squared: float
    conformity: bool
    total_coefficients: int


class BenfordLawChecker:
    """Check whether an image's DCT coefficients follow Benford's Law.

    Forensics tools transform an image into the frequency domain using the
    Discrete Cosine Transform (DCT), extract quantisation coefficients, isolate
    the first significant digit (FSD) of each, and compare the digit
    distribution against Benford's theoretical curve.

    :param config: Benford analysis parameters (block size, threshold).
    """

    def __init__(self, config: BenfordConfig) -> None:
        """Bind configuration for DCT block size and chi-squared threshold.

        :param config: Externalised analysis parameters from config.yaml.
        """
        self._block_size = config.block_size
        self._chi_squared_threshold = config.chi_squared_threshold

    def check(self, image_path: Path) -> BenfordResult:
        """Run a full Benford's Law analysis on a single image.

        :param image_path: Path to a PNG image file.
        :return: Structured result with digit distribution, chi-squared, and conformity verdict.
        :raises FileNotFoundError: If the image file does not exist.
        :raises ValueError: If the image yields no usable DCT coefficients.
        """
        if not image_path.is_file():
            raise FileNotFoundError(image_path)

        pixels = self._load_grayscale(image_path)
        coefficients = self._blockwise_dct(pixels)
        digits = self._first_significant_digits(coefficients)

        if len(digits) == 0:
            raise ValueError(image_path)

        observed = self._digit_frequencies(digits)
        chi_sq = self._chi_squared(observed, len(digits))

        return BenfordResult(
            image_path=str(image_path),
            observed_frequencies=observed,
            expected_frequencies={d: round(p, 6) for d, p in _BENFORD_EXPECTED.items()},
            chi_squared=round(chi_sq, 4),
            conformity=chi_sq <= self._chi_squared_threshold,
            total_coefficients=len(digits),
        )

    @staticmethod
    def _load_grayscale(image_path: Path) -> np.ndarray:
        """Open an image and convert to a grayscale numpy array.

        :param image_path: Path to the image.
        :return: 2-D float64 array of pixel intensities.
        """
        with Image.open(image_path) as img:
            gray = img.convert("L")
            return np.asarray(gray, dtype=np.float64)

    def _blockwise_dct(self, pixels: np.ndarray) -> np.ndarray:
        """Apply block-wise 2-D DCT and collect all coefficients.

        The image is split into non-overlapping square blocks of
        ``block_size x block_size``. Edge pixels that do not fill a complete
        block are discarded (standard practice in JPEG-style analysis).

        :param pixels: 2-D grayscale pixel array.
        :return: Flat 1-D array of all DCT coefficients across blocks.
        """
        bs = self._block_size
        h, w = pixels.shape
        rows = h // bs
        cols = w // bs

        all_coeffs: list[np.ndarray] = []
        for r in range(rows):
            for c in range(cols):
                block = pixels[r * bs : (r + 1) * bs, c * bs : (c + 1) * bs]
                dct_block = dctn(block, type=2, norm="ortho")
                all_coeffs.append(dct_block.ravel())

        if not all_coeffs:
            return np.array([], dtype=np.float64)
        return np.concatenate(all_coeffs)

    @staticmethod
    def _first_significant_digits(coefficients: np.ndarray) -> np.ndarray:
        """Extract the first significant digit from each non-zero coefficient.

        Takes the absolute value, then repeatedly divides by 10 until the
        leading non-zero digit (1-9) is isolated.

        :param coefficients: Flat array of DCT coefficients.
        :return: Array of first significant digits (values 1-9).
        """
        abs_vals = np.abs(coefficients)
        nonzero = abs_vals[abs_vals > 0]

        if len(nonzero) == 0:
            return np.array([], dtype=np.int64)

        log_vals = np.log10(nonzero)
        fractional = log_vals - np.floor(log_vals)
        digits = np.floor(10 ** fractional).astype(np.int64)
        digits = np.clip(digits, 1, 9)
        return digits

    @staticmethod
    def _digit_frequencies(digits: np.ndarray) -> dict[int, float]:
        """Count digit occurrences and convert to relative frequencies.

        :param digits: Array of first significant digits (1-9).
        :return: Mapping from digit to observed frequency proportion.
        """
        total = len(digits)
        counts = dict.fromkeys(_DIGITS, 0)
        unique, unique_counts = np.unique(digits, return_counts=True)
        for digit, count in zip(unique, unique_counts, strict=True):
            if 1 <= digit <= 9:
                counts[int(digit)] = int(count)
        return {d: round(c / total, 6) for d, c in counts.items()}

    @staticmethod
    def _chi_squared(observed: dict[int, float], n: int) -> float:
        """Compute chi-squared statistic against Benford's distribution.

        :param observed: Observed digit frequency proportions.
        :param n: Total number of observations.
        :return: Chi-squared statistic (8 degrees of freedom).
        """
        chi_sq = 0.0
        for d in _DIGITS:
            expected_count = _BENFORD_EXPECTED[d] * n
            observed_count = observed[d] * n
            chi_sq += (observed_count - expected_count) ** 2 / expected_count
        return chi_sq
