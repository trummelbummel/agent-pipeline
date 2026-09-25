from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from compliance.config.settings import BenfordConfig
from compliance.tools.benford import BenfordLawChecker, BenfordResult


def _create_png(path: Path, size: tuple[int, int] = (64, 64), seed: int = 42) -> Path:
    """Write a synthetic grayscale PNG for testing."""
    rng = np.random.default_rng(seed)
    pixels = rng.integers(0, 256, size=size, dtype=np.uint8)
    img = Image.fromarray(pixels, mode="L")
    img.save(path, format="PNG")
    return path


@pytest.fixture
def config() -> BenfordConfig:
    return BenfordConfig(block_size=8, chi_squared_threshold=15.51)


@pytest.fixture
def checker(config: BenfordConfig) -> BenfordLawChecker:
    return BenfordLawChecker(config)


class TestBenfordResult:
    def test_result_fields(self) -> None:
        result = BenfordResult(
            image_path="test.png",
            observed_frequencies=dict.fromkeys(range(1, 10), 1 / 9),
            expected_frequencies=dict.fromkeys(range(1, 10), 0.1),
            chi_squared=5.0,
            conformity=True,
            total_coefficients=1000,
        )
        assert result.conformity is True
        assert result.chi_squared == 5.0
        assert len(result.observed_frequencies) == 9


class TestLoadGrayscale:
    def test_returns_2d_float_array(self, tmp_path: Path, checker: BenfordLawChecker) -> None:
        png = _create_png(tmp_path / "test.png", size=(32, 32))
        arr = checker._load_grayscale(png)
        assert arr.ndim == 2
        assert arr.shape == (32, 32)
        assert arr.dtype == np.float64

    def test_rgb_image_converted_to_grayscale(self, tmp_path: Path, checker: BenfordLawChecker) -> None:
        rgb = Image.new("RGB", (16, 16), color=(100, 150, 200))
        path = tmp_path / "rgb.png"
        rgb.save(path, format="PNG")
        arr = checker._load_grayscale(path)
        assert arr.ndim == 2
        assert arr.shape == (16, 16)


class TestBlockwiseDCT:
    def test_coefficient_count(self, tmp_path: Path, checker: BenfordLawChecker) -> None:
        png = _create_png(tmp_path / "test.png", size=(64, 64))
        pixels = checker._load_grayscale(png)
        coeffs = checker._blockwise_dct(pixels)
        blocks = (64 // 8) * (64 // 8)
        assert len(coeffs) == blocks * 8 * 8

    def test_small_image_no_blocks(self, checker: BenfordLawChecker) -> None:
        tiny = np.zeros((4, 4), dtype=np.float64)
        coeffs = checker._blockwise_dct(tiny)
        assert len(coeffs) == 0

    def test_non_divisible_dimensions(self, checker: BenfordLawChecker) -> None:
        pixels = np.random.default_rng(0).random((19, 27)) * 255
        coeffs = checker._blockwise_dct(pixels)
        expected_blocks = (19 // 8) * (27 // 8)
        assert len(coeffs) == expected_blocks * 64


class TestFirstSignificantDigits:
    def test_known_values(self) -> None:
        coeffs = np.array([123.0, -45.6, 7.89, 0.012, -0.34])
        digits = BenfordLawChecker._first_significant_digits(coeffs)
        assert list(digits) == [1, 4, 7, 1, 3]

    def test_zeros_excluded(self) -> None:
        coeffs = np.array([0.0, 0.0, 5.0])
        digits = BenfordLawChecker._first_significant_digits(coeffs)
        assert len(digits) == 1
        assert digits[0] == 5

    def test_all_zeros_empty(self) -> None:
        coeffs = np.array([0.0, 0.0, 0.0])
        digits = BenfordLawChecker._first_significant_digits(coeffs)
        assert len(digits) == 0


class TestDigitFrequencies:
    def test_uniform_digits(self) -> None:
        digits = np.array([1, 2, 3, 4, 5, 6, 7, 8, 9])
        freqs = BenfordLawChecker._digit_frequencies(digits)
        for d in range(1, 10):
            assert abs(freqs[d] - 1 / 9) < 1e-5

    def test_single_digit(self) -> None:
        digits = np.array([3, 3, 3])
        freqs = BenfordLawChecker._digit_frequencies(digits)
        assert freqs[3] == 1.0
        assert freqs[1] == 0.0


class TestChiSquared:
    def test_perfect_match_is_zero(self) -> None:
        from compliance.tools.benford import _BENFORD_EXPECTED

        observed = {d: round(p, 6) for d, p in _BENFORD_EXPECTED.items()}
        chi_sq = BenfordLawChecker._chi_squared(observed, 10000)
        assert chi_sq < 0.01

    def test_uniform_distribution_high_chi_squared(self) -> None:
        observed = dict.fromkeys(range(1, 10), 1 / 9)
        chi_sq = BenfordLawChecker._chi_squared(observed, 10000)
        assert chi_sq > 15.51


class TestCheck:
    def test_returns_benford_result(self, tmp_path: Path, checker: BenfordLawChecker) -> None:
        png = _create_png(tmp_path / "test.png", size=(64, 64))
        result = checker.check(png)
        assert isinstance(result, BenfordResult)
        assert result.image_path == str(png)
        assert len(result.observed_frequencies) == 9
        assert len(result.expected_frequencies) == 9
        assert result.total_coefficients > 0

    def test_file_not_found_raises(self, tmp_path: Path, checker: BenfordLawChecker) -> None:
        with pytest.raises(FileNotFoundError, match="nonexistent"):
            checker.check(tmp_path / "nonexistent.png")

    def test_image_too_small_raises(self, tmp_path: Path, checker: BenfordLawChecker) -> None:
        tiny = tmp_path / "tiny.png"
        img = Image.fromarray(np.zeros((4, 4), dtype=np.uint8), mode="L")
        img.save(tiny, format="PNG")
        with pytest.raises(ValueError, match="tiny"):
            checker.check(tiny)

    def test_conformity_with_loose_threshold(self, tmp_path: Path) -> None:
        loose = BenfordConfig(block_size=8, chi_squared_threshold=10000.0)
        checker = BenfordLawChecker(loose)
        png = _create_png(tmp_path / "test.png", size=(64, 64))
        result = checker.check(png)
        assert result.conformity is True

    def test_conformity_with_strict_threshold(self, tmp_path: Path) -> None:
        strict = BenfordConfig(block_size=8, chi_squared_threshold=0.001)
        checker = BenfordLawChecker(strict)
        png = _create_png(tmp_path / "test.png", size=(64, 64))
        result = checker.check(png)
        assert result.conformity is False

    def test_different_block_sizes(self, tmp_path: Path) -> None:
        config_16 = BenfordConfig(block_size=16, chi_squared_threshold=15.51)
        checker_16 = BenfordLawChecker(config_16)
        png = _create_png(tmp_path / "test.png", size=(64, 64))
        result = checker_16.check(png)
        assert result.total_coefficients > 0
        expected_blocks = (64 // 16) * (64 // 16)
        assert result.total_coefficients <= expected_blocks * 16 * 16
