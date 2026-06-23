"""字幕样式与布局（PNG overlay 与 ASS 烧录共用）。"""

from __future__ import annotations

from app.config import get_settings

# 布局（与 subtitle_overlay 一致）
SIDE_MARGIN = 48
SUBTITLE_Y_RATIO = 0.75
MAX_LINES = 2

# 样式（与片头黄条同色）；基准竖屏 1080×1920
SUBTITLE_FONT_SIZE = 68
SUBTITLE_FONT_MIN = 64
SUBTITLE_COLOR_RGB = (255, 214, 64)
# ASS PrimaryColour：BGR 
SUBTITLE_ASS_PRIMARY_COLOUR = "&H0040D6FF"
SUBTITLE_STROKE_WIDTH = 1
SUBTITLE_SHADOW_BLUR = 2


def layout_for_canvas(width: int, height: int) -> dict[str, int]:
    """按画布尺寸缩放边距与字号（以竖屏 1080×1920 为基准）。"""
    settings = get_settings()
    ref_w, ref_h = settings.video_width, settings.video_height
    if ref_w > ref_h:
        ref_w, ref_h = ref_h, ref_w
    h_scale = height / ref_h
    w_scale = width / ref_w
    font_max = max(SUBTITLE_FONT_MIN, int(SUBTITLE_FONT_SIZE * h_scale))
    font_min = max(28, int(SUBTITLE_FONT_MIN * h_scale))
    if font_min > font_max:
        font_min = font_max
    return {
        "width": width,
        "height": height,
        "side_margin": max(24, int(SIDE_MARGIN * w_scale)),
        "font_max": font_max,
        "font_min": font_min,
    }


def subtitle_style_for_canvas(width: int, height: int) -> dict[str, int | str]:
    """PNG overlay 与 ASS 烧录共用的布局/样式。"""
    layout = layout_for_canvas(width, height)
    font_size = int(layout["font_max"])
    line_gap = max(4, font_size // 24)
    block_h = font_size * MAX_LINES + line_gap
    margin_v = max(24, int(height * (1 - SUBTITLE_Y_RATIO) - block_h / 2))
    side = int(layout["side_margin"])
    return {
        "font_size": font_size,
        "margin_l": side,
        "margin_r": side,
        "margin_v": margin_v,
        "outline": SUBTITLE_STROKE_WIDTH,
        "shadow": max(1, SUBTITLE_SHADOW_BLUR),
        "primary_colour": SUBTITLE_ASS_PRIMARY_COLOUR,
        "outline_colour": "&H00000000",
        "back_colour": "&H30000000",
    }
