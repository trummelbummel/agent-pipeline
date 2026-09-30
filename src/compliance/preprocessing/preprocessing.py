from __future__ import annotations

import logging
import os
import shutil
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from PIL import Image

logger = logging.getLogger(__name__)


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

    def __init__(self, source_formats: list[str]) -> None:
        """Create a converter for the given source format suffixes.

        :param source_formats: File extensions without dots from config
            (``preprocessing.document_formats``); never hardcoded in callers.
        """
        self.source_formats = [fmt.lower().lstrip(".") for fmt in source_formats]

    def to_png(self, path: Path, *, output_dir: Path | None = None) -> Path:
        """Return a PNG path for ``path``, converting when needed.

        :param path: Source document path.
        :param output_dir: When set, write ``{stem}.png`` (or copy an existing PNG
            under its original basename) into this directory instead of a temp file.
        :return: Unchanged path when already PNG and ``output_dir`` is None;
            otherwise the PNG path written or copied.
        :raises ValueError: If the suffix is not in ``source_formats`` or not convertible.
        """
        suffix = path.suffix.lower().lstrip(".")
        if suffix == "png":
            return self._png_passthrough(path, output_dir)

        self._require_convertible_suffix(suffix)

        out_path = self._converted_png(path, self._png_destination(path, output_dir))
        logger.info("Converted %s (.%s) → PNG (%s)", path.name, suffix, out_path.name)
        return out_path

    def _require_convertible_suffix(self, suffix: str) -> None:
        if suffix not in self.source_formats:
            msg = f"Unsupported format for PNG conversion: .{suffix}"
            raise ValueError(msg)
        if suffix == "pdf":
            msg = "PDF conversion is not supported by FormatConverter; pass through or convert externally"
            raise ValueError(msg)

    def _png_passthrough(self, path: Path, output_dir: Path | None) -> Path:
        """Return ``path`` or a copy under ``output_dir``.

        :param path: Existing PNG source path.
        :param output_dir: Optional destination directory for a durable copy.
        :return: Original path, or the copied path under ``output_dir``.
        """
        if output_dir is None:
            return path
        output_dir.mkdir(parents=True, exist_ok=True)
        dest = output_dir / path.name
        if path.resolve() != dest.resolve():
            shutil.copy2(path, dest)
        return dest

    def _png_destination(self, path: Path, output_dir: Path | None) -> Path:
        """Resolve where a converted PNG should be written.

        :param path: Source document path (stem reused for the PNG name).
        :param output_dir: Durable output directory, or None for a temp file.
        :return: Path to create/overwrite with PNG bytes.
        """
        if output_dir is not None:
            output_dir.mkdir(parents=True, exist_ok=True)
            return output_dir / f"{path.stem}.png"

        fd, name = tempfile.mkstemp(suffix=".png", prefix=f"{path.stem}_")
        os.close(fd)
        return Path(name)

    def _converted_png(self, path: Path, out_path: Path) -> Path:
        with Image.open(path) as image:
            self._to_rgb(image).save(out_path, format="PNG")
        return out_path

    @staticmethod
    def _to_rgb(image: Image.Image) -> Image.Image:
        if image.mode == "RGB":
            return image
        return image.convert("RGB")
