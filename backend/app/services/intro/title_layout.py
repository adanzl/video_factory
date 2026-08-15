"""片头 / 封面标题：分字折行 + 按封面基准字号缩放。"""

from __future__ import annotations

from PIL import Image, ImageFont

from app.services.render.text_render import balance_title_lines, load_cjk_font
from app.services.render.title_render import (
    STROKE_WIDTH,
    compose_vstack,
    render_text_rgba,
    text_bbox,
)

# 与 MAX_TITLE_LENGTH / 封面一致；超长截断
TITLE_MAX_CHARS = 18
# 无空格时单行上限；超过则均分两行（不要为了挤进单行而缩小字号）
TITLE_SINGLE_LINE_MAX = 8

# 封面设计画布上的字号；片头按画布高度放大
_LANDSCAPE_REF_H = 720
_PORTRAIT_REF_H = 1280
_LANDSCAPE_FONT_MAX = 135
_LANDSCAPE_FONT_MIN = 100
_PORTRAIT_FONT_MAX = 120
_PORTRAIT_FONT_MIN = 96


def split_title_lines(title: str, *, max_lines: int = 2) -> list[str]:
    """标题折行：冒号变空格后优先按空格分两行，否则超过 8 字均分两行。"""
    display = title.replace("：", " ").replace(":", " ").strip()
    if not display:
        return [""]
    compact = display.replace(" ", "")
    if len(compact) > TITLE_MAX_CHARS:
        compact = compact[:TITLE_MAX_CHARS]
    if " " in display:
        parts = display.split(" ", 1)
        line1 = parts[0].strip()[:TITLE_MAX_CHARS]
        line2 = (
            parts[1].strip()[: TITLE_MAX_CHARS - len(line1)]
            if len(parts) > 1
            else ""
        )
        if line2:
            return [line1, line2]
        return [line1] if line1 else [compact]
    if len(compact) <= TITLE_SINGLE_LINE_MAX:
        return [compact]
    return balance_title_lines(compact, max_lines)


def title_font_range(*, width: int, height: int) -> tuple[int, int]:
    """按封面 720p/1280p 基准字号，随画布高度放大。

    1280×720 → 135–100；1920×1080 → 约 203–150，避免 1080p 片头显得比封面小。
    """
    if width > height:
        scale = height / _LANDSCAPE_REF_H
        return (
            max(1, round(_LANDSCAPE_FONT_MAX * scale)),
            max(1, round(_LANDSCAPE_FONT_MIN * scale)),
        )
    scale = height / _PORTRAIT_REF_H
    return (
        max(1, round(_PORTRAIT_FONT_MAX * scale)),
        max(1, round(_PORTRAIT_FONT_MIN * scale)),
    )


def fit_title_font(
    lines: list[str],
    *,
    max_width: int,
    max_size: int,
    min_size: int,
    max_height: int | None = None,
    line_gap_ratio: float = 1 / 12,
) -> tuple[ImageFont.FreeTypeFont, int]:
    """已折行标题：取能放下的最大字号，不重新折行。"""
    font = load_cjk_font(min_size)
    font_size = min_size
    for size in range(max_size, min_size - 1, -2):
        candidate = load_cjk_font(size)
        if not all(text_bbox(line, candidate)[0] <= max_width for line in lines):
            continue
        gap = max(8, int(size * line_gap_ratio))
        total_h = sum(text_bbox(line, candidate)[1] for line in lines)
        total_h += gap * max(len(lines) - 1, 0)
        if max_height is not None and total_h > max_height:
            continue
        font = candidate
        font_size = size
        break
    return font, font_size


def layout_title(
    title: str,
    max_width: int,
    *,
    max_size: int,
    min_size: int,
    max_lines: int = 2,
    max_height: int | None = None,
) -> tuple[ImageFont.FreeTypeFont, list[str], int]:
    """分字折行后再适配字号，返回 (font, lines, font_size)。"""
    normalized = title.strip()
    lines = [ln for ln in split_title_lines(normalized, max_lines=max_lines) if ln]
    if not lines:
        lines = [""]
    font, font_size = fit_title_font(
        lines,
        max_width=max_width,
        max_size=max_size,
        min_size=min_size,
        max_height=max_height,
    )
    return font, lines, font_size


def render_feed_title(
    title: str,
    theme,
    max_width: int,
    *,
    max_size: int = 118,
    min_size: int = 58,
    max_lines: int = 2,
    max_height: int | None = None,
) -> Image.Image:
    """渲染标题文字块（不含背景圆），折行规则与封面相同。"""
    font, lines, font_size = layout_title(
        title,
        max_width,
        max_size=max_size,
        min_size=min_size,
        max_lines=max_lines,
        max_height=max_height,
    )
    line_gap = max(8, font_size // 12)
    stroke = STROKE_WIDTH + 4

    rendered = [
        render_text_rgba(
            line,
            font,
            fill=theme.title_fill,
            stroke_width=stroke,
            stroke_fill=theme.title_stroke,
            with_shadow=True,
            shadow_blur=14,
            shadow_offset_x=3,
            shadow_offset_y=4,
        )
        for line in lines
    ]
    return compose_vstack(rendered, gap=line_gap, align="center")
