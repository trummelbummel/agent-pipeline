from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from evaluation.analysis_stats import AnalysisStats
from evaluation.evaluator import EvaluationResult

_CELL = 88
_MARGIN_LEFT = 110
_MARGIN_TOP = 56
_PAD = 8

_TOP_N = 12
_PANEL_WIDTH = 720
_PANEL_PAD = 16
_BAR_HEIGHT = 18
_BAR_GAP = 6
_LABEL_WIDTH = 220
_BAR_MAX_WIDTH = 420
_PANEL_HEADER = 36


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


def write_analysis_stats_png(stats: AnalysisStats, path: Path) -> Path:
    """Render a multi-panel bar chart PNG from AnalysisStats.

    Panels: decision counts, checker true-rates (0-1), top-N label frequencies
    (coverage/reason/document prefixed), and top-N decision explanations.
    Empty stats still yield a titled PNG with empty bars.

    :param stats: Aggregated analysis_result statistics.
    :param path: Destination path under ``results_dir`` for the PNG artifact.
    :return: The written ``path``.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    image = _render_analysis_stats(stats)
    image.save(path, format="PNG")
    return path


def _render_analysis_stats(stats: AnalysisStats) -> Image.Image:
    """Compose four horizontal-bar panels into one RGB image.

    :param stats: Aggregated analysis statistics to visualize.
    :return: RGB image ready to save as PNG.
    """
    decision_items = _top_items(stats.decision_counts)
    rate_items = _top_items(stats.checker_true_rates)
    label_items = _top_items(_prefixed_label_counts(stats))
    explanation_items = _top_items(stats.decision_explanation_counts)
    panels = [
        ("Decisions", decision_items, False),
        ("Checker true rates", rate_items, True),
        ("Label frequencies", label_items, False),
        ("Decision explanations", explanation_items, False),
    ]
    panel_images = [_bar_panel(title, items, rate_scale=rate_scale) for title, items, rate_scale in panels]
    width = _PANEL_WIDTH
    heights = [img.height for img in panel_images]
    title_band = 40
    height = title_band + sum(heights) + _PANEL_PAD
    image = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    font_title = _load_font(16)
    draw.text(
        (_PANEL_PAD, 10),
        f"Analysis stats  n_claims={stats.n_claims}",
        fill=(30, 30, 30),
        font=font_title,
    )
    y = title_band
    for panel in panel_images:
        image.paste(panel, (0, y))
        y += panel.height
    return image


def _prefixed_label_counts(stats: AnalysisStats) -> dict[str, float]:
    """Merge coverage/reason/document label counts with series prefixes.

    :param stats: Aggregated analysis statistics.
    :return: Prefixed label → count mapping for a single panel.
    """
    merged: dict[str, float] = {}
    for prefix, counts in (
        ("coverage", stats.coverage_label_counts),
        ("reason", stats.reason_label_counts),
        ("document", stats.document_label_counts),
    ):
        for label, count in counts.items():
            merged[f"{prefix}:{label}"] = float(count)
    return merged


def _top_items(counts: dict[str, float] | dict[str, int]) -> list[tuple[str, float]]:
    """Sort mapping by value descending and cap at ``_TOP_N``.

    :param counts: Category → value mapping.
    :return: Top-N ``(label, value)`` pairs.
    """
    items = [(key, float(value)) for key, value in counts.items()]
    items.sort(key=lambda pair: (-pair[1], pair[0]))
    return items[:_TOP_N]


def _bar_panel(
    title: str,
    items: list[tuple[str, float]],
    *,
    rate_scale: bool,
) -> Image.Image:
    """Render one titled horizontal-bar panel.

    :param title: Panel heading text.
    :param items: Category/value pairs to draw (may be empty).
    :param rate_scale: When True, axis max is 1.0; otherwise max of values.
    :return: RGB image for this panel.
    """
    n_rows = max(len(items), 1)
    height = _PANEL_HEADER + n_rows * (_BAR_HEIGHT + _BAR_GAP) + _PANEL_PAD
    image = Image.new("RGB", (_PANEL_WIDTH, height), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    font = _load_font(13)
    font_title = _load_font(15)
    draw.text((_PANEL_PAD, 8), title, fill=(30, 30, 30), font=font_title)
    if not items:
        draw.text(
            (_PANEL_PAD, _PANEL_HEADER),
            "(none)",
            fill=(140, 140, 140),
            font=font,
        )
        return image
    peak = 1.0 if rate_scale else max((value for _, value in items), default=1.0) or 1.0
    _draw_bars(draw, items, peak=peak, rate_scale=rate_scale, font=font)
    return image


def _draw_bars(
    draw: ImageDraw.ImageDraw,
    items: list[tuple[str, float]],
    *,
    peak: float,
    rate_scale: bool,
    font: ImageFont.ImageFont | ImageFont.FreeTypeFont,
) -> None:
    """Draw labeled horizontal bars into an existing panel draw context.

    :param draw: PIL draw handle for the panel image.
    :param items: Category/value pairs already capped/sorted.
    :param peak: Scale denominator for bar widths.
    :param rate_scale: Format values as ratios when True.
    :param font: Font for labels and value text.
    """
    for index, (label, value) in enumerate(items):
        y = _PANEL_HEADER + index * (_BAR_HEIGHT + _BAR_GAP)
        draw.text((_PANEL_PAD, y), _truncate(label, 34), fill=(40, 40, 40), font=font)
        bar_x = _PANEL_PAD + _LABEL_WIDTH
        width = int(_BAR_MAX_WIDTH * (value / peak)) if peak > 0 else 0
        bar_width = max(width, 1) if value > 0 else 0
        if bar_width > 0:
            draw.rectangle(
                [bar_x, y, bar_x + bar_width, y + _BAR_HEIGHT],
                fill=(70, 130, 180),
                outline=(90, 90, 90),
            )
        text = f"{value:.2f}" if rate_scale else str(int(value))
        draw.text(
            (bar_x + bar_width + 6, y),
            text,
            fill=(50, 50, 50),
            font=font,
        )


def _truncate(text: str, max_len: int) -> str:
    """Shorten long category labels for the bar axis.

    :param text: Original label.
    :param max_len: Maximum characters including ellipsis.
    :return: Possibly truncated label.
    """
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


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
        f"acc={result.accuracy:.0%}  F1={result.f1_macro:.2f}  n={result.n_evaluated}  "
        f"HITL T/F={result.human_in_the_loop_true}/{result.human_in_the_loop_false}"
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
