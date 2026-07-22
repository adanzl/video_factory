"""片头标题：统一字号黄色大字。"""

from __future__ import annotations

from PIL import Image

from app.services.render.text_render import load_cjk_font, wrap_text
from app.services.render.title_render import (
    STROKE_WIDTH,
    compose_vstack,
    fit_font_and_lines,
    render_text_rgba,
)


def render_feed_title(
    title: str,
    theme,
    max_width: int,
    *,
    max_size: int = 118,
    min_size: int = 58,
    max_lines: int = 3,
    max_height: int | None = None,
) -> Image.Image:
    """渲染标题文字块（不含背景圆），最多 max_lines 行。"""
    normalized = title.strip()

    def _load(size: int):
        return load_cjk_font(size)

    font, lines, font_size = fit_font_and_lines(
        normalized,
        max_width,
        _load,
        max_size=max_size,
        min_size=min_size,
        wrap_fn=wrap_text,
        max_lines=max_lines,
        max_height=max_height,
    )
    line_gap = max(8, font_size // 14)
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
