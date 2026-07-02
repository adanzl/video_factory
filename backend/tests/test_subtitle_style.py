from __future__ import annotations

from app.services.render.subtitle_style import (
    SUBTITLE_FONT_SIZE,
    layout_for_canvas,
    subtitle_style_for_canvas,
)


def test_landscape_font_matches_portrait_at_1080p() -> None:
    """横屏 1920×1080 与竖屏 1080×1920 应得到相同目标字号。"""
    portrait = subtitle_style_for_canvas(1080, 1920)
    landscape = subtitle_style_for_canvas(1920, 1080)
    assert portrait["font_size"] == SUBTITLE_FONT_SIZE
    assert landscape["font_size"] == SUBTITLE_FONT_SIZE


def test_font_max_not_clamped_by_font_min() -> None:
    """font_max 由 SUBTITLE_FONT_SIZE 决定，不被 SUBTITLE_FONT_MIN 顶死。"""
    layout = layout_for_canvas(1920, 1080)
    assert layout["font_max"] == SUBTITLE_FONT_SIZE
    assert layout["font_min"] <= layout["font_max"]
