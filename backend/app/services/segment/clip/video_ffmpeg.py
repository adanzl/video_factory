"""FFmpeg Ken Burns 动效 ClipProvider。"""

from __future__ import annotations

from pathlib import Path

from app.services.segment.clip.clip_mgr import ClipProvider, clip_mgr
from app.services.segment.clip.clip_render import image_to_clip


class FfmpegClipProvider(ClipProvider):
    def build_segment_clip(
        self,
        *,
        image_path: Path,
        subtitle_cues: list[tuple[str, float]],
        output_path: Path,
        motion_preset: str,
        work_dir: Path,
        segment_index: int,
        motion_prompt: str | None = None,
        image_prompt: str | None = None,
        width: int | None = None,
        height: int | None = None,
    ) -> Path:
        _ = motion_prompt
        _ = image_prompt
        _ = work_dir
        total_duration = clip_mgr.cue_total_duration(subtitle_cues)
        if total_duration <= 0:
            raise ValueError(f"segment {segment_index} has zero duration")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        # 字幕改在 merge 阶段 ASS 烧录，分镜只出干净动效片
        image_to_clip(
            image_path,
            output_path,
            total_duration,
            preset=motion_preset,
            segment_index=segment_index,
            width=width,
            height=height,
        )
        return output_path
