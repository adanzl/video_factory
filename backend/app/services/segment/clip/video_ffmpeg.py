"""FFmpeg Ken Burns 动效 ClipProvider。"""

from __future__ import annotations

from pathlib import Path

from app.services.segment.clip.clip_mgr import ClipProvider, clip_mgr
from app.services.segment.clip.clip_render import image_to_clip, image_to_clip_timed_overlays


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
        total_duration, overlay_windows, overlay_paths = clip_mgr.prepare_subtitle_overlays(
            subtitle_cues=subtitle_cues,
            work_dir=work_dir,
            segment_index=segment_index,
            width=width,
            height=height,
        )
        if total_duration <= 0:
            raise ValueError(f"segment {segment_index} has zero duration")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            if overlay_windows:
                image_to_clip_timed_overlays(
                    image_path,
                    overlay_windows,
                    output_path,
                    total_duration,
                    preset=motion_preset,
                    segment_index=segment_index,
                    width=width,
                    height=height,
                )
            else:
                image_to_clip(
                    image_path,
                    output_path,
                    total_duration,
                    preset=motion_preset,
                    segment_index=segment_index,
                    width=width,
                    height=height,
                )
        finally:
            clip_mgr.cleanup_overlay_paths(overlay_paths)
        return output_path
