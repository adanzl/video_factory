"""媒体合成总入口：分镜片段 → 正文 → 成片。"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from app.config import get_settings
from app.services.media.ffmpeg_utils import (
    concat_clips,
    merge_audio_video,
    prepend_intro,
)
from app.services.media.subtitle_overlay import build_segment_clip
from app.services.tts.tts_mgr import cues_for_segment, load_subtitle_cues, subtitle_cues_path_for

__all__ = [
    "MergeResult",
    "SegmentClipsResult",
    "build_segment_clips",
    "merge_final",
]


@dataclass
class SegmentClipsResult:
    segment_clip_paths: list[tuple[int, Path]]


@dataclass
class MergeResult:
    body_path: Path
    body_with_audio_path: Path
    final_path: Path


def _resolve_clip_provider(*, visual_mode: str) -> str:
    settings = get_settings()
    if visual_mode == "kling_std" and settings.kling_upgrade_enabled:
        return "kling_std"
    return "static_motion"


def build_segment_clips(
    *,
    media_dir: Path,
    segments: list[dict],
    audio_path: Path,
    only_segment_indices: set[int] | None = None,
) -> SegmentClipsResult:
    settings = get_settings()
    clips_dir = media_dir / "segments"
    clips_dir.mkdir(parents=True, exist_ok=True)

    subtitle_cues = load_subtitle_cues(subtitle_cues_path_for(audio_path.parent))
    if not subtitle_cues:
        raise FileNotFoundError(
            f"缺少 {subtitle_cues_path_for(audio_path.parent)}，请从 tts 阶段重跑"
        )

    segment_clips: list[tuple[int, Path]] = []
    for seg in segments:
        index = seg["segment_index"]
        clip_path = clips_dir / f"{index}.mp4"
        if only_segment_indices and index not in only_segment_indices:
            existing = Path(seg["clip_path"]) if seg.get("clip_path") else clip_path
            if not existing.exists():
                raise FileNotFoundError(
                    f"segment {index} 缺少 clip，请全量重跑 segment 或指定该段"
                )
            segment_clips.append((seg["id"], existing))
            continue

        visual_mode = seg.get("visual_mode") or "static_motion"
        provider = _resolve_clip_provider(visual_mode=visual_mode)
        if provider == "kling_std":
            raise NotImplementedError(
                f"segment {index} visual_mode=kling_std 需 VideoProvider，尚未接入"
            )

        seg_cues = cues_for_segment(subtitle_cues, index)
        if not seg_cues:
            raise ValueError(f"segment {index} 无句级字幕时间轴")
        build_segment_clip(
            image_path=Path(seg["image_path"]),
            subtitle_cues=seg_cues,
            output_path=clip_path,
            motion_preset=settings.motion_preset,
            work_dir=clips_dir,
            segment_index=index,
        )
        segment_clips.append((seg["id"], clip_path))

    return SegmentClipsResult(segment_clip_paths=segment_clips)


def merge_final(
    *,
    media_dir: Path,
    segments: list[dict],
    audio_path: Path,
    subtitle_path: Path | None,
    intro_path: Path | None,
) -> MergeResult:
    clips_dir = media_dir / "segments"
    clip_paths: list[Path] = []
    for seg in sorted(segments, key=lambda s: s["segment_index"]):
        index = seg["segment_index"]
        if seg.get("clip_path"):
            clip_paths.append(Path(seg["clip_path"]))
        else:
            fallback = clips_dir / f"{index}.mp4"
            if not fallback.exists():
                raise FileNotFoundError(
                    f"segment {index} 缺少 clip，请从 segment 阶段重跑"
                )
            clip_paths.append(fallback)

    body_path = media_dir / "body.mp4"
    concat_clips(clip_paths, body_path)

    body_with_audio = media_dir / "body_with_audio.mp4"
    merge_audio_video(body_path, audio_path, body_with_audio, subtitle_path=subtitle_path)

    final_path = media_dir / "final.mp4"
    if intro_path and intro_path.exists():
        prepend_intro(intro_path, body_with_audio, final_path)
    else:
        shutil.copy2(body_with_audio, final_path)

    return MergeResult(
        body_path=body_path,
        body_with_audio_path=body_with_audio,
        final_path=final_path,
    )
