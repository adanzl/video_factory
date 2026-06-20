"""字幕烧录：PIL 透明层 + 连续 Ken Burns 单次 FFmpeg 合成。

按 TTS 句级时间轴绘制 overlay PNG，在同一分镜内按 t 切换字幕（方案 A）。
"""

from __future__ import annotations

import os
from pathlib import Path

from PIL import Image

from app.config import get_settings
from app.services.media.clip.render import image_to_clip_with_overlay
from app.services.visual.text_render import load_cjk_font, wrap_text
from app.services.visual.title_render import (
    SHADOW_OFFSET_X,
    SHADOW_OFFSET_Y,
    fit_font_and_lines,
    render_title_block,
)

# 布局
_SIDE_MARGIN = 48
_SUBTITLE_Y_RATIO = 0.75
_MAX_LINES = 2

# 样式（与片头黄条同色）
_SUBTITLE_FONT_SIZE = 68
_SUBTITLE_FONT_MIN = 54
_SUBTITLE_RENDER_SCALE = 2
_SUBTITLE_COLOR = (255, 214, 64, 255)
_SUBTITLE_STROKE_WIDTH = 1
_SUBTITLE_SHADOW_BLUR = 2

__all__ = ["build_segment_clip", "burn_subtitled_clip", "render_subtitle_overlay"]


def _keep_overlay_png() -> bool:
    """SUBTITLE_KEEP_OVERLAY=1 时保留 .sub.png 便于排查。"""
    return os.getenv("SUBTITLE_KEEP_OVERLAY", "").lower() in {"1", "true", "yes"}


def _layout_for_canvas(width: int, height: int) -> dict:
    """按画布尺寸缩放边距与字号（以竖屏 1080×1920 为基准）。"""
    settings = get_settings()
    ref_w, ref_h = settings.video_width, settings.video_height
    if ref_w > ref_h:
        ref_w, ref_h = ref_h, ref_w
    h_scale = height / ref_h
    w_scale = width / ref_w
    font_max = max(_SUBTITLE_FONT_MIN, int(_SUBTITLE_FONT_SIZE * h_scale))
    font_min = max(28, int(_SUBTITLE_FONT_MIN * h_scale))
    if font_min > font_max:
        font_min = font_max
    return {
        "width": width,
        "height": height,
        "side_margin": max(24, int(_SIDE_MARGIN * w_scale)),
        "font_max": font_max,
        "font_min": font_min,
    }


def _fit_subtitle(
    text: str,
    max_width: int,
    *,
    font_max: int = _SUBTITLE_FONT_SIZE,
    font_min: int = _SUBTITLE_FONT_MIN,
) -> tuple[list[str], int]:
    _, lines, font_size = fit_font_and_lines(
        text,
        max_width,
        load_cjk_font,
        max_size=font_max,
        min_size=font_min,
        wrap_fn=wrap_text,
        max_lines=_MAX_LINES,
        balance_overflow=False,
    )
    return lines, font_size


def _render_subtitle_block(lines: list[str], font_size: int, line_gap: int) -> Image.Image:
    """2x 超采样绘制后 LANCZOS 缩小。"""
    scale = _SUBTITLE_RENDER_SCALE
    scaled_font = load_cjk_font(font_size * scale)
    block = render_title_block(
        lines,
        scaled_font,
        fill=_SUBTITLE_COLOR,
        line_gap=line_gap * scale,
        stroke_width=_SUBTITLE_STROKE_WIDTH * scale,
        with_shadow=True,
        shadow_blur=_SUBTITLE_SHADOW_BLUR * scale,
        shadow_offset_x=SHADOW_OFFSET_X * scale,
        shadow_offset_y=SHADOW_OFFSET_Y * scale,
        with_glow=False,
    )
    return block.resize(
        (max(1, block.size[0] // scale), max(1, block.size[1] // scale)),
        Image.Resampling.LANCZOS,
    )


def render_subtitle_overlay(
    text: str,
    output_path: Path,
    *,
    width: int | None = None,
    height: int | None = None,
) -> Path:
    """生成整帧字幕透明 PNG（默认 1080×1920 RGBA，可传入基底视频尺寸）。"""
    settings = get_settings()
    if width is None or height is None:
        width, height = settings.video_width, settings.video_height
    layout = _layout_for_canvas(width, height)
    width = layout["width"]
    height = layout["height"]
    output_path.parent.mkdir(parents=True, exist_ok=True)

    lines, font_size = _fit_subtitle(
        text,
        width - layout["side_margin"] * 2,
        font_max=layout["font_max"],
        font_min=layout["font_min"],
    )
    line_gap = max(4, font_size // 24)
    text_block = _render_subtitle_block(lines, font_size, line_gap)

    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    text_x = (width - text_block.size[0]) // 2
    text_y = int(height * _SUBTITLE_Y_RATIO - text_block.size[1] / 2)
    text_y = max(0, min(text_y, height - text_block.size[1]))
    canvas.alpha_composite(text_block, (text_x, text_y))
    canvas.save(output_path, compress_level=0)
    return output_path


def burn_subtitled_clip(
    *,
    image_path: Path,
    text: str,
    output_path: Path,
    duration_sec: float,
    motion_preset: str,
    segment_index: int = 0,
) -> Path:
    """PIL 绘制 overlay + Ken Burns，单次编码输出带字幕 clip。"""
    overlay_path = output_path.with_suffix(".sub.png")
    render_subtitle_overlay(text, overlay_path)
    try:
        return image_to_clip_with_overlay(
            image_path,
            overlay_path,
            output_path,
            duration_sec,
            preset=motion_preset,
            segment_index=segment_index,
        )
    finally:
        if not _keep_overlay_png():
            overlay_path.unlink(missing_ok=True)


def build_segment_clip(
    *,
    image_path: Path,
    subtitle_cues: list[tuple[str, float]],
    output_path: Path,
    motion_preset: str,
    work_dir: Path,
    segment_index: int,
    clip_provider: str | None = None,
    motion_prompt: str | None = None,
) -> Path:
    """分镜内连续动效 + 句级字幕按时间轴切换。"""
    from app.services.media.clip.mgr import clip_mgr

    provider = clip_provider or get_settings().clip_provider
    return clip_mgr.build_segment_clip(
        clip_provider=provider,
        image_path=image_path,
        subtitle_cues=subtitle_cues,
        output_path=output_path,
        motion_preset=motion_preset,
        work_dir=work_dir,
        segment_index=segment_index,
        motion_prompt=motion_prompt,
    )
