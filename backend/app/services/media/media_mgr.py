"""媒体合成总入口：分镜片段 → 正文 → 成片。"""

from __future__ import annotations

import logging
import shutil
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from app.config import get_settings
from app.utils.job_cancel import job_cancel
from app.services.media.clip.mgr import clip_mgr
from app.services.media.subtitle_style import subtitle_style_for_canvas
from app.services.media.ffmpeg_utils import build_ass_from_phrase_cues
from app.services.media.ffmpeg_utils import (
    concat_clips,
    ffmpeg_hwaccel_config_summary,
    log_ffmpeg_hwaccel_config,
    merge_audio_video,
    prepend_intro,
    probe_duration,
    probe_video_size,
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

    def _resolve_clip_provider(self, *, visual_mode: str, job: dict | None = None) -> str:
        settings = get_settings()
        if visual_mode == "kling_std" and settings.kling_upgrade_enabled:
            return "kling_std"
        from app.utils.job_info import resolve_video_provider

        return resolve_video_provider(job, visual_mode=visual_mode, settings=settings)

    def _describe_clip_provider(
        self,
        provider: str,
        *,
        motion_preset: str,
        width: int,
        height: int,
    ) -> str:
        settings = get_settings()
        if provider == "wan_i2v":
            return (
                f"provider=wan_i2v, model={settings.wan_i2v_model}, "
                f"resolution={settings.wan_i2v_resolution}, "
                f"prompt_extend={settings.wan_i2v_prompt_extend}, "
                f"size={width}x{height}"
            )
        if provider == "agnes_i2v":
            return (
                f"provider=agnes_i2v, model={settings.agnes_video_model}, "
                f"frame_rate={settings.agnes_video_frame_rate}, "
                f"size={width}x{height}"
            )
        if provider == "ffmpeg":
            return f"provider=ffmpeg, motion_preset={motion_preset}, size={width}x{height}"
        return f"provider={provider}, motion_preset={motion_preset}, size={width}x{height}"

    @staticmethod
    def _load_subtitle_cues(media_dir: Path) -> list:
        cues_path = tts_mgr.subtitle_cues_path_for(media_dir / "audio")
        return tts_mgr.load_subtitle_cues(cues_path)

    @staticmethod
    def _cues_for_segment(seg: dict, subtitle_cues: list) -> list[tuple[str, float]]:
        index = seg["segment_index"]
        seg_cues = tts_mgr.cues_for_segment(subtitle_cues, index)
        if seg_cues:
            return seg_cues
        duration = seg.get("duration_sec")
        text = (seg.get("text") or "").strip()
        if duration is not None and float(duration) > 0:
            return [(text or f"segment {index}", float(duration))]
        return []

    def build_segment_clips(
        self,
        *,
        media_dir: Path,
        segments: list[dict],
        audio_path: Path | None = None,
        only_segment_indices: set[int] | None = None,
        job: dict | None = None,
        on_clip_done: Callable[[int, Path], None] | None = None,
    ) -> SegmentClipsResult:
        settings = get_settings()
        from app.utils.job_info import resolve_segment_video_size

        clip_width, clip_height = resolve_segment_video_size(job, settings=settings)
        clips_dir = media_dir / "segments"
        clips_dir.mkdir(parents=True, exist_ok=True)

        subtitle_cues = self._load_subtitle_cues(media_dir)
        cues_path = tts_mgr.subtitle_cues_path_for(media_dir / "audio")
        if not subtitle_cues:
            logger.warning(
                "clip batch: missing %s, will fallback to segment duration_sec where available",
                cues_path,
            )
        elif audio_path is None:
            logger.info("clip batch: loaded subtitle cues from %s", cues_path)

        segment_clips: list[tuple[int, Path]] = []
        targets = (
            [seg for seg in segments if seg["segment_index"] in only_segment_indices]
            if only_segment_indices is not None
            else segments
        )
        total = len(targets)
        t_start = time.time()
        target_indices = [seg["segment_index"] for seg in targets]
        logger.info(
            "clip batch start: count=%s, segments=%s, size=%sx%s",
            total,
            target_indices,
            clip_width,
            clip_height,
        )
        for i, seg in enumerate(targets, 1):
            if job is not None and job.get("id") is not None:
                job_cancel.raise_if_cancelled(int(job["id"]))
            index = seg["segment_index"]
            clip_path = clips_dir / f"{index}.mp4"

            visual_mode = seg.get("visual_mode") or "static_motion"
            provider = self._resolve_clip_provider(visual_mode=visual_mode, job=job)
            params_desc = self._describe_clip_provider(
                provider,
                motion_preset=settings.motion_preset,
                width=clip_width,
                height=clip_height,
            )
            if provider == "kling_std":
                raise NotImplementedError(
                    f"segment {index} visual_mode=kling_std 需 VideoProvider，尚未接入"
                )

            seg_cues = self._cues_for_segment(seg, subtitle_cues)
            if not seg_cues:
                raise ValueError(
                    f"segment {index} 无句级字幕时间轴，请先执行 tts，或确保分镜有 duration_sec"
                )
            if not tts_mgr.cues_for_segment(subtitle_cues, index):
                logger.info(
                    "clip segment %s: using duration_sec fallback (%.2fs)",
                    index,
                    sum(duration for _, duration in seg_cues),
                )
            motion_prompt = seg.get("motion_prompt") or seg.get("visual_brief") or ""
            image_prompt = seg.get("image_prompt") or ""
            logger.info(
                "clip %s/%s building segment %s | %s | image_chars=%s motion_chars=%s",
                i,
                total,
                index,
                params_desc,
                len(image_prompt),
                len(motion_prompt),
            )
            clip_mgr.build_segment_clip(
                clip_provider=provider,
                image_path=Path(seg["image_path"]),
                subtitle_cues=seg_cues,
                output_path=clip_path,
                motion_preset=settings.motion_preset,
                work_dir=clips_dir,
                segment_index=index,
                motion_prompt=motion_prompt,
                image_prompt=image_prompt or None,
                width=clip_width,
                height=clip_height,
            )
            segment_clips.append((seg["id"], clip_path))
            if on_clip_done is not None:
                on_clip_done(seg["id"], clip_path)
            logger.info(
                "clip %s/%s done segment %s | %s",
                i,
                total,
                index,
                params_desc,
            )

        elapsed = time.time() - t_start
        logger.info(
            "clip batch done: %s/%s in %.1fs, segments=%s",
            len(segment_clips),
            total,
            elapsed,
            target_indices,
        )
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
        log_ffmpeg_hwaccel_config(context="merge")
        logger.info("merge: %s", ffmpeg_hwaccel_config_summary())
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

    def merge_material_final(
        self,
        *,
        media_dir: Path,
        base_video_path: Path,
        audio_path: Path,
        intro_path: Path | None,
    ) -> MergeResult:
        """素材流水线：基底视频 + 字幕烧录 + TTS + 片头。"""
        t0 = time.time()
        log_ffmpeg_hwaccel_config(context="merge_material")
        logger.info("merge_material: %s", ffmpeg_hwaccel_config_summary())
        subtitle_cues = tts_mgr.load_subtitle_cues(
            tts_mgr.subtitle_cues_path_for(audio_path.parent)
        )
        if not subtitle_cues:
            raise FileNotFoundError(
                f"缺少 {tts_mgr.subtitle_cues_path_for(audio_path.parent)}，请从 tts 阶段重跑"
            )

        audio_dur = probe_duration(audio_path)
        base_dur = probe_duration(base_video_path)
        tail_tol = 0.08
        silent_tail = base_dur > audio_dur + tail_tol
        output_dur = base_dur if silent_tail else audio_dur
        if silent_tail:
            logger.info(
                "merge_material: base %.2fs > audio %.2fs, keep full video with silent tail",
                base_dur,
                audio_dur,
            )
        else:
            logger.info(
                "merge_material: output duration %.2fs (audio-driven)",
                output_dur,
            )

        flat_cues = [
            (cue.text, cue.duration_sec)
            for cue in subtitle_cues
            if cue.duration_sec > 0 and cue.text.strip()
        ]

        work_dir = media_dir / "merge_work"
        work_dir.mkdir(parents=True, exist_ok=True)

        from app.services.media.clip.render import (
            fit_video_duration,
            fit_video_with_ass_subtitles,
        )

        body_path = media_dir / "body.mp4"
        base_w, base_h = probe_video_size(base_video_path)
        if flat_cues:
            subtitle_style = subtitle_style_for_canvas(base_w, base_h)
            logger.info(
                "merge_material: burning %s subtitle cues via ass on %sx%s "
                "font_size=%s (libx264 cpu)",
                len(flat_cues),
                base_w,
                base_h,
                subtitle_style["font_size"],
            )
            ass_path = work_dir / "subtitles.ass"
            ass_path.write_text(
                build_ass_from_phrase_cues(flat_cues, width=base_w, height=base_h),
                encoding="utf-8",
            )
            fit_video_with_ass_subtitles(
                base_video_path,
                ass_path,
                body_path,
                output_dur,
                width=base_w,
                height=base_h,
            )
        else:
            logger.warning("merge_material: no subtitle cues with duration, skipping burn")
            fit_video_duration(
                base_video_path,
                body_path,
                output_dur,
                width=base_w,
                height=base_h,
            )

        logger.info("merge_material: body.mp4 done")

        body_with_audio = media_dir / "body_with_audio.mp4"
        merge_audio_video(
            body_path,
            audio_path,
            body_with_audio,
            subtitle_path=None,
            silent_tail_when_video_longer=silent_tail,
        )
        logger.info("merge_material: audio merged")

        final_path = media_dir / "final.mp4"
        if intro_path and intro_path.exists():
            logger.info("merge_material: prepending intro")
            prepend_intro(intro_path, body_with_audio, final_path)
        else:
            shutil.copy2(body_with_audio, final_path)

        elapsed = time.time() - t0
        logger.info("merge_material: done in %.1fs -> %s", elapsed, final_path)
        return MergeResult(
            body_path=body_path,
            body_with_audio_path=body_with_audio,
            final_path=final_path,
        )


media_mgr = MediaMgr()
