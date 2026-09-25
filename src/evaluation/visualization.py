from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from evaluation.evaluator import EvaluationResult

_CELL = 88
_MARGIN_LEFT = 110
_MARGIN_TOP = 56
_PAD = 8


def write_confusion_matrix_png(result: EvaluationResult, path: Path) -> Path:
    """Render a labeled confusion-matrix heatmap PNG from an EvaluationResult.

    :param result: Aggregate evaluation with ``labels`` and ``confusion_matrix``.
    :param path: Destination path under ``results_dir`` for the PNG artifact.
    :return: The written ``path``.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    image = _render_heatmap(result)
    image.save(path, format="PNG")
    return path


def _render_heatmap(result: EvaluationResult) -> Image.Image:
    labels = result.labels
    matrix = result.confusion_matrix
    n = len(labels)
    width = _MARGIN_LEFT + n * _CELL + _PAD
    height = _MARGIN_TOP + n * _CELL + 36
    image = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    font = _load_font(14)
    font_title = _load_font(16)
    font_cell = _load_font(18)
    title = (
        f"Confusion matrix  "
        f"acc={result.accuracy:.0%}  F1={result.f1_macro:.2f}  n={result.n_evaluated}"
    )
    draw.text((_MARGIN_LEFT, 12), title, fill=(30, 30, 30), font=font_title)
    draw.text((_MARGIN_LEFT, 34), "Predicted →", fill=(90, 90, 90), font=font)
    draw.text((8, _MARGIN_TOP - 18), "GT ↓", fill=(90, 90, 90), font=font)
    peak = max((max(row) for row in matrix), default=0) or 1
    for i, true_label in enumerate(labels):
        y = _MARGIN_TOP + i * _CELL
        draw.text((8, y + _CELL // 3), true_label, fill=(20, 20, 20), font=font)
        for j, pred_label in enumerate(labels):
            x = _MARGIN_LEFT + j * _CELL
            if i == 0:
                draw.text((x + 8, _MARGIN_TOP - 18), pred_label, fill=(20, 20, 20), font=font)
            count = matrix[i][j]
            fill = _cell_color(count, peak)
            draw.rectangle(
                [x, y, x + _CELL - 4, y + _CELL - 4],
                fill=fill,
                outline=(120, 120, 120),
            )
            text_fill = (255, 255, 255) if count / peak > 0.55 else (20, 20, 20)
            draw.text(
                (x + _CELL // 2 - 6, y + _CELL // 2 - 10),
                str(count),
                fill=text_fill,
                font=font_cell,
            )
    return image


def _cell_color(count: int, peak: int) -> tuple[int, int, int]:
    t = count / peak
    return (
        int(235 - 170 * t),
        int(245 - 140 * t),
        int(255 - 50 * t),
    )


def _load_font(size: int) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    for name in (
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()
