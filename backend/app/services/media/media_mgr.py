"""媒体合成总入口：分镜片段 → 正文 → 成片。"""

from __future__ import annotations

import logging
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

from app.config import get_settings
from app.services.media.clip.mgr import clip_mgr
from app.services.media.ffmpeg_utils import (
    concat_clips,
    merge_audio_video,
    prepend_intro,
)
from app.services.tts.tts_mgr import tts_mgr

logger = logging.getLogger(__name__)

__all__ = ["MediaMgr", "MergeResult", "SegmentClipsResult", "media_mgr"]


@dataclass
class SegmentClipsResult:
    segment_clip_paths: list[tuple[int, Path]]


@dataclass
class MergeResult:
    body_path: Path
    body_with_audio_path: Path
    final_path: Path


class MediaMgr:
    """媒体合成管理器。"""

    def _resolve_clip_provider(self, *, visual_mode: str) -> str:
        settings = get_settings()
        if visual_mode == "kling_std" and settings.kling_upgrade_enabled:
            return "kling_std"
        if visual_mode == "wan_i2v":
            return "wan_i2v"
        if visual_mode == "static_motion":
            return settings.clip_provider
        return settings.clip_provider

    def build_segment_clips(
        self,
        *,
        media_dir: Path,
        segments: list[dict],
        audio_path: Path,
        only_segment_indices: set[int] | None = None,
    ) -> SegmentClipsResult:
        settings = get_settings()
        clips_dir = media_dir / "segments"
        clips_dir.mkdir(parents=True, exist_ok=True)

        subtitle_cues = tts_mgr.load_subtitle_cues(
            tts_mgr.subtitle_cues_path_for(audio_path.parent)
        )
        if not subtitle_cues:
            raise FileNotFoundError(
                f"缺少 {tts_mgr.subtitle_cues_path_for(audio_path.parent)}，请从 tts 阶段重跑"
            )

        segment_clips: list[tuple[int, Path]] = []
        targets = (
            [seg for seg in segments if seg["segment_index"] in only_segment_indices]
            if only_segment_indices is not None
            else segments
        )
        total = len(targets)
        t_start = time.time()
        for i, seg in enumerate(targets, 1):
            index = seg["segment_index"]
            clip_path = clips_dir / f"{index}.mp4"

            visual_mode = seg.get("visual_mode") or "static_motion"
            provider = self._resolve_clip_provider(visual_mode=visual_mode)
            if provider == "kling_std":
                raise NotImplementedError(
                    f"segment {index} visual_mode=kling_std 需 VideoProvider，尚未接入"
                )

            seg_cues = tts_mgr.cues_for_segment(subtitle_cues, index)
            if not seg_cues:
                raise ValueError(f"segment {index} 无句级字幕时间轴")
            motion_prompt = seg.get("motion_prompt") or seg.get("visual_brief") or ""
            logger.info("clip %s/%s building (provider=%s)...", i, total, provider)
            clip_mgr.build_segment_clip(
                clip_provider=provider,
                image_path=Path(seg["image_path"]),
                subtitle_cues=seg_cues,
                output_path=clip_path,
                motion_preset=settings.motion_preset,
                work_dir=clips_dir,
                segment_index=index,
                motion_prompt=motion_prompt,
            )
            segment_clips.append((seg["id"], clip_path))
            logger.info("clip %s/%s done (segment %s)", i, total, index)

        elapsed = time.time() - t_start
        logger.info("clip total: %s/%s built in %.1fs", len(segment_clips), total, elapsed)
        return SegmentClipsResult(segment_clip_paths=segment_clips)

    def merge_final(
        self,
        *,
        media_dir: Path,
        segments: list[dict],
        audio_path: Path,
        subtitle_path: Path | None,
        intro_path: Path | None,
    ) -> MergeResult:
        t0 = time.time()
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

        logger.info("merge: concatenating %s clips", len(clip_paths))
        body_path = media_dir / "body.mp4"
        concat_clips(clip_paths, body_path)
        logger.info("merge: body.mp4 done")

        body_with_audio = media_dir / "body_with_audio.mp4"
        merge_audio_video(body_path, audio_path, body_with_audio, subtitle_path=subtitle_path)
        logger.info("merge: audio+subtitles merged")

        final_path = media_dir / "final.mp4"
        if intro_path and intro_path.exists():
            logger.info("merge: prepending intro")
            prepend_intro(intro_path, body_with_audio, final_path)
        else:
            shutil.copy2(body_with_audio, final_path)

        elapsed = time.time() - t0
        logger.info("merge: done in %.1fs -> %s", elapsed, final_path)
        return MergeResult(
            body_path=body_path,
            body_with_audio_path=body_with_audio,
            final_path=final_path,
        )


media_mgr = MediaMgr()
