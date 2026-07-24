"""字幕烧录：PIL 透明层绘制（调试/预览）；成片改在 merge 用 ASS 烧录。

按 TTS 句级时间轴绘制 overlay PNG；日常流水线分镜不再叠字幕。
"""

from __future__ import annotations

import os
from pathlib import Path

from PIL import Image

from app.config import get_settings
from app.services.segment.clip.clip_render import image_to_clip_with_overlay
from app.services.render.subtitle_style import (
    MAX_LINES,
    SUBTITLE_ASS_PRIMARY_COLOUR,
    SUBTITLE_COLOR_RGB,
    SUBTITLE_FONT_MIN,
    SUBTITLE_FONT_SIZE,
    SUBTITLE_SHADOW_BLUR,
    SUBTITLE_STROKE_WIDTH,
    SUBTITLE_Y_RATIO,
    layout_for_canvas,
    subtitle_style_for_canvas,
)
from app.services.render.text_render import load_cjk_font, wrap_text
from app.repositories import repo_segment
from app.services.render.title_render import (
    SHADOW_OFFSET_X,
    SHADOW_OFFSET_Y,
    fit_font_and_lines,
    render_title_block,
)
from app.services.tts.tts_mgr import tts_mgr

# 布局 / 样式常量见 subtitle_style.py
_SUBTITLE_RENDER_SCALE = 2
_SUBTITLE_COLOR = (*SUBTITLE_COLOR_RGB, 255)

__all__ = [
    "SUBTITLE_ASS_PRIMARY_COLOUR",
    "build_segment_clip",
    "burn_subtitled_clip",
    "rebuild_segment_subtitles",
    "render_subtitle_overlay",
    "subtitle_style_for_canvas",
]


def _keep_overlay_png() -> bool:
    """SUBTITLE_KEEP_OVERLAY=1 时保留 .sub.png 便于排查。"""
    return os.getenv("SUBTITLE_KEEP_OVERLAY", "").lower() in {"1", "true", "yes"}


def _layout_for_canvas(width: int, height: int) -> dict:
    return layout_for_canvas(width, height)


def _fit_subtitle(
    text: str,
    max_width: int,
    *,
    font_max: int = SUBTITLE_FONT_SIZE,
    font_min: int = SUBTITLE_FONT_MIN,
) -> tuple[list[str], int]:
    _, lines, font_size = fit_font_and_lines(
        text,
        max_width,
        load_cjk_font,
        max_size=font_max,
        min_size=font_min,
        wrap_fn=wrap_text,
        max_lines=MAX_LINES,
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
        stroke_width=SUBTITLE_STROKE_WIDTH * scale,
        with_shadow=True,
        shadow_blur=SUBTITLE_SHADOW_BLUR * scale,
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
    text_y = int(height * SUBTITLE_Y_RATIO - text_block.size[1] / 2)
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
    from app.services.segment.clip.clip_mgr import clip_mgr

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


def rebuild_segment_subtitles(
    job_id: int,
    segment_index: int,
    *,
    sentence: int | None = None,
) -> Path:
    """单分镜字幕预览：重建 segments/{N}.mp4 或句级 {N}_test.mp4。"""
    settings = get_settings()
    media_dir = settings.video_data_dir / str(job_id)
    clips_dir = media_dir / "segments"
    clips_dir.mkdir(parents=True, exist_ok=True)

    segments = repo_segment.list_segments(job_id)
    seg = next((s for s in segments if s["segment_index"] == segment_index), None)
    if seg is None:
        raise ValueError(f"job {job_id} 无 segment {segment_index}")

    image_path = seg.get("image_path")
    if not image_path:
        raise FileNotFoundError(f"segment {segment_index} 无 image_path")

    cues_path = tts_mgr.subtitle_cues_path_for(media_dir / "audio")
    seg_cues = tts_mgr.cues_for_segment(tts_mgr.load_subtitle_cues(cues_path), segment_index)
    if not seg_cues:
        raise ValueError(f"segment {segment_index} 无字幕时间轴")

    if sentence is not None:
        if sentence < 0 or sentence >= len(seg_cues):
            raise ValueError(f"sentence 需在 0..{len(seg_cues) - 1}")
        text, duration = seg_cues[sentence]
        out_path = clips_dir / f"{segment_index}_test.mp4"
        burn_subtitled_clip(
            image_path=Path(image_path),
            text=text,
            output_path=out_path,
            duration_sec=duration,
            motion_preset=settings.motion_preset,
            segment_index=segment_index,
        )
        return out_path

    out_path = clips_dir / f"{segment_index}.mp4"
    build_segment_clip(
        image_path=Path(image_path),
        subtitle_cues=seg_cues,
        output_path=out_path,
        motion_preset=settings.motion_preset,
        work_dir=clips_dir,
        segment_index=segment_index,
    )
    return out_path
