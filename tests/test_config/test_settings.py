from __future__ import annotations

from pathlib import Path

import pytest

from compliance.config import load_config


def test_load_config_reads_document_formats(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
preprocessing:
  data_dir: data
  output_filename: processed.json
  document_formats: [webp, jpg, png]
  confidence_threshold: 0.7
extraction:
  model: test-model
  prompt: |
    extract things
""",
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


def test_load_config_missing_file_raises(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist.yaml"
    with pytest.raises(FileNotFoundError, match="Config file not found"):
        load_config(missing)
