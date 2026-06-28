"""分镜 clip 合成：ClipProvider 抽象 + 编排入口。"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from pathlib import Path

from app.config import get_settings

__all__ = ["ClipMgr", "ClipProvider", "clip_mgr"]


def _keep_overlay_png() -> bool:
    return os.getenv("SUBTITLE_KEEP_OVERLAY", "").lower() in {"1", "true", "yes"}


class ClipProvider(ABC):
    @abstractmethod
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
        width: int | None = None,
        height: int | None = None,
    ) -> Path:
        ...


class ClipMgr:
    """分镜 clip 管理器。"""

    def prepare_subtitle_overlays(
        self,
        *,
        subtitle_cues: list[tuple[str, float]],
        work_dir: Path,
        segment_index: int,
        width: int | None = None,
        height: int | None = None,
    ) -> tuple[float, list[tuple[Path, float, float]], list[Path]]:
        from app.services.media.subtitle_overlay import render_subtitle_overlay

        total_duration = sum(duration for _, duration in subtitle_cues if duration > 0)
        overlay_windows: list[tuple[Path, float, float]] = []
        overlay_paths: list[Path] = []
        cursor = 0.0
        for idx, (sentence, duration) in enumerate(subtitle_cues):
            if duration <= 0:
                continue
            start = cursor
            end = cursor + duration
            cursor = end
            if not sentence.strip():
                continue
            overlay_path = work_dir / f"{segment_index}_{idx}.sub.png"
            render_subtitle_overlay(
                sentence,
                overlay_path,
                width=width,
                height=height,
            )
            overlay_paths.append(overlay_path)
            overlay_windows.append((overlay_path, start, end))
        return total_duration, overlay_windows, overlay_paths

    def cleanup_overlay_paths(self, overlay_paths: list[Path]) -> None:
        if _keep_overlay_png():
            return
        for path in overlay_paths:
            path.unlink(missing_ok=True)

    def get_clip_provider(self, name: str) -> ClipProvider:
        from app.services.media.clip.video_ffmpeg import FfmpegClipProvider
        from app.services.media.clip.video_wan import WanClipProvider
        from app.services.media.clip.video_agnes import AgnesClipProvider

        if name == "wan_i2v":
            if get_settings().mock_mode:
                return FfmpegClipProvider()
            return WanClipProvider()
        if name == "agnes_i2v":
            if get_settings().mock_mode:
                return FfmpegClipProvider()
            return AgnesClipProvider()
        if name == "ffmpeg":
            return FfmpegClipProvider()
        raise ValueError(f"unknown clip provider: {name}")

    def build_segment_clip(
        self,
        *,
        clip_provider: str,
        image_path: Path,
        subtitle_cues: list[tuple[str, float]],
        output_path: Path,
        motion_preset: str,
        work_dir: Path,
        segment_index: int,
        motion_prompt: str | None = None,
        width: int | None = None,
        height: int | None = None,
    ) -> Path:
        if not subtitle_cues:
            raise ValueError(f"segment {segment_index} has no subtitle cues")
        provider = self.get_clip_provider(clip_provider)
        return provider.build_segment_clip(
            image_path=image_path,
            subtitle_cues=subtitle_cues,
            output_path=output_path,
            motion_preset=motion_preset,
            work_dir=work_dir,
            segment_index=segment_index,
            motion_prompt=motion_prompt,
            width=width,
            height=height,
        )


clip_mgr = ClipMgr()
