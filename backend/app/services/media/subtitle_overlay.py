"""字幕烧录：PIL 透明层 + Ken Burns 单次 FFmpeg 合成。

按 TTS 句级时间轴逐句绘制 overlay PNG，与分镜图一次性编码为 clip。
样式与片头共用 title_render（黄字、描边、斜投影、2x 超采样）。
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from PIL import Image

from app.config import get_settings
from app.services.media.ffmpeg_utils import (
    concat_clips,
    image_to_clip,
    image_to_clip_with_overlay,
)
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


def _fit_subtitle(text: str, max_width: int) -> tuple[list[str], int]:
    _, lines, font_size = fit_font_and_lines(
        text,
        max_width,
        load_cjk_font,
        max_size=_SUBTITLE_FONT_SIZE,
        min_size=_SUBTITLE_FONT_MIN,
        wrap_fn=wrap_text,
        max_lines=_MAX_LINES,
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


def render_subtitle_overlay(text: str, output_path: Path) -> Path:
    """生成整帧字幕透明 PNG（1080×1920 RGBA）。"""
    settings = get_settings()
    width, height = settings.video_width, settings.video_height
    output_path.parent.mkdir(parents=True, exist_ok=True)

    lines, font_size = _fit_subtitle(text, width - _SIDE_MARGIN * 2)
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
) -> Path:
    """分镜内按句级时间轴逐句烧字幕后 concat。"""
    if not subtitle_cues:
        raise ValueError(f"segment {segment_index} has no subtitle cues")

    sub_clips: list[Path] = []
    for idx, (sentence, duration) in enumerate(subtitle_cues):
        if duration <= 0:
            continue
        sub_clip = work_dir / f"{segment_index}_{idx}.mp4"
        if sentence.strip():
            burn_subtitled_clip(
                image_path=image_path,
                text=sentence,
                output_path=sub_clip,
                duration_sec=duration,
                motion_preset=motion_preset,
            )
        else:
            image_to_clip(image_path, sub_clip, duration, preset=motion_preset)
        sub_clips.append(sub_clip)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if len(sub_clips) == 1:
        shutil.move(str(sub_clips[0]), str(output_path))
        return output_path

    concat_clips(sub_clips, output_path)
    for path in sub_clips:
        path.unlink(missing_ok=True)
    return output_path
