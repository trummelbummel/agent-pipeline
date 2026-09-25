from __future__ import annotations

import logging
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from PIL import Image

logger = logging.getLogger(__name__)

_DEFAULT_SOURCE_FORMATS = ["webp", "jpg", "jpeg", "png"]
_RASTER_MODES_NEEDING_RGB = {"RGBA", "LA", "P", "PA"}


class Preprocessor(ABC):
    """Transform raw reader input into a shape ready for model construction."""

    @abstractmethod
    def preprocess(self, raw: Any) -> Any:
        """Transform raw loaded content into processed data.

        :param raw: Unprocessed content from a Reader._load call.
        :return: Processed content suitable for Reader._to_model.
        """


class FormatConverter:
    """Convert configured raster document formats to PNG via Pillow.

    Applied before Docling in DocumentReader (S03); PNG inputs pass through.
    """

    def __init__(self, source_formats: list[str] | None = None) -> None:
        """Create a converter for the given source format suffixes.

        :param source_formats: File extensions without dots (e.g. webp, jpg).
            Defaults to common raster formats when not provided.
        """
        formats = source_formats if source_formats is not None else _DEFAULT_SOURCE_FORMATS
        self.source_formats = [fmt.lower().lstrip(".") for fmt in formats]

    def to_png(self, path: Path) -> Path:
        """Return a PNG path for ``path``, converting when needed.

        :param path: Source document path.
        :return: Unchanged path when already PNG; otherwise a new PNG path.
        :raises ValueError: If the suffix is not in ``source_formats`` or not convertible.
        """
        suffix = path.suffix.lower().lstrip(".")
        if suffix == "png":
            return path

        if suffix not in self.source_formats:
            msg = f"Unsupported format for PNG conversion: .{suffix}"
            raise ValueError(msg)

        if suffix == "pdf":
            msg = "PDF conversion is not supported by FormatConverter; pass through or convert externally"
            raise ValueError(msg)

        with Image.open(path) as image:
            rgb = self._to_rgb(image)
            out_path = Path(tempfile.mkstemp(suffix=".png", prefix=f"{path.stem}_")[1])
            rgb.save(out_path, format="PNG")

        logger.info("Converted %s (.%s) → PNG (%s)", path.name, suffix, out_path.name)
        return out_path

    @staticmethod
    def _to_rgb(image: Image.Image) -> Image.Image:
        """Convert an image to RGB for PNG output.

        :param image: Opened Pillow image.
        :return: RGB image suitable for PNG save.
        """
        if image.mode in _RASTER_MODES_NEEDING_RGB:
            return image.convert("RGB")
        if image.mode != "RGB":
            return image.convert("RGB")
        return image
