"""媒体合成总入口：分镜片段 → 正文 → 成片。"""

from __future__ import annotations

import logging
import shutil
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from gevent.lock import Semaphore

from app.config import get_settings
from app.utils.job_cancel import JobCancelledError, job_cancel
from app.services.segment.clip.clip_mgr import clip_mgr
from app.services.render.subtitle_style import subtitle_style_for_canvas
from app.services.media.ffmpeg_utils import build_ass_from_phrase_cues
from app.services.media.ffmpeg_utils import (
    concat_clips,
    concat_video_audio_pts_fixed,
    ffmpeg_hwaccel_config_summary,
    log_ffmpeg_hwaccel_config,
    merge_audio_video,
    mix_bgm_into_video,
    prepend_intro,
    probe_duration,
    probe_video_size,
)
from app.services.tts.tts_mgr import tts_mgr

logger = logging.getLogger(__name__)

__all__ = ["MediaMgr", "MergeResult", "SegmentClipsResult", "media_mgr"]

# I2V 并发控制：单分镜占槽，限制全局同时进行的图生视频路数
_i2v_semaphore: Semaphore | None = None
_i2v_max_workers: int = 1
_i2v_semaphore_lock = Semaphore(value=1)
_I2V_PROVIDERS = frozenset({"wan_i2v", "agnes_i2v"})


def _ensure_i2v_semaphore() -> Semaphore:
    global _i2v_semaphore, _i2v_max_workers
    settings = get_settings()
    max_workers = max(1, settings.video_max_workers)
    with _i2v_semaphore_lock:
        if _i2v_semaphore is None or _i2v_max_workers != max_workers:
            _i2v_max_workers = max_workers
            _i2v_semaphore = Semaphore(max_workers)
        return _i2v_semaphore


def _reset_i2v_semaphore_for_tests() -> None:
    """测试用：清空进程内 I2V 信号量缓存。"""
    global _i2v_semaphore, _i2v_max_workers
    with _i2v_semaphore_lock:
        _i2v_semaphore = None
        _i2v_max_workers = 1


@dataclass
class SegmentClipsResult:
    segment_clip_paths: list[tuple[int, Path]]


@dataclass
class MergeResult:
    body_path: Path
    body_with_audio_path: Path
    final_path: Path


def _inject_mouth_motion(
    prompt: str,
    seg: dict,
    cues: list[tuple[str, float]],
) -> str:
    """如有对话，在 motion_prompt 前注入开口说话动作（含起止时间）。"""
    dialogue = seg.get("dialogue") or []
    if not dialogue or not cues:
        return prompt
    # dialogue 与 cues 同序；cue[1] 为 duration_sec
    speaker_actions: dict[str, list[tuple[float, float]]] = {}
    t = 0.0
    for i, (_, dur) in enumerate(cues):
        if i >= len(dialogue):
            break
        speaker = str((dialogue[i].get("speaker") or "")).strip()
        if not speaker:
            t += dur
            continue
        start, end = t, t + dur
        t = end
        speaker_actions.setdefault(speaker, []).append((start, end))
    if not speaker_actions:
        return prompt
    parts: list[str] = []
    for name, intervals in speaker_actions.items():
        segs = ",".join(
            f"{s:.1f}-{e:.1f}秒" for s, e in intervals
        )
        parts.append(f"{segs}{name}说话")
    if not parts:
        return prompt
    return "；".join(parts) + "。" + prompt


class MediaMgr:
    """媒体合成管理器。"""

    def _resolve_clip_provider(
        self,
        *,
        visual_mode: str,
        job: dict | None = None,
        segment: dict | None = None,
    ) -> str:
        settings = get_settings()
        if visual_mode == "kling_std" and settings.kling_upgrade_enabled:
            return "kling_std"
        from app.utils.job_info import resolve_video_provider

        return resolve_video_provider(
            job, visual_mode=visual_mode, settings=settings, segment=segment
        )

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
                f"frame_rate={settings.clip_fps}, "
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
        on_clip_done: Callable[[int, Path, float], None] | None = None,
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

        targets = (
            [seg for seg in segments if seg["segment_index"] in only_segment_indices]
            if only_segment_indices is not None
            else segments
        )
        total = len(targets)
        t_start = time.time()
        target_indices = [seg["segment_index"] for seg in targets]

        uses_i2v = any(
            self._resolve_clip_provider(
                visual_mode=seg.get("visual_mode") or "static_motion",
                job=job,
                segment=seg,
            )
            in _I2V_PROVIDERS
            for seg in targets
        )
        max_workers = (
            1
            if settings.mock_mode or not uses_i2v
            else max(1, settings.video_max_workers)
        )

        logger.info(
            "clip batch start: count=%s, workers=%s, segments=%s, size=%sx%s%s",
            total,
            max_workers,
            target_indices,
            clip_width,
            clip_height,
            " (i2v)" if uses_i2v else "",
        )

        def build_one(seg: dict, ordinal: int) -> tuple[int, Path, float]:
            t0 = time.time()
            job_id = int(job["id"]) if job is not None and job.get("id") is not None else None
            if job_id is not None:
                job_cancel.raise_if_cancelled(job_id)
            index = seg["segment_index"]
            clip_path = clips_dir / f"{index}.mp4"

            visual_mode = seg.get("visual_mode") or "static_motion"
            provider = self._resolve_clip_provider(
                visual_mode=visual_mode, job=job, segment=seg
            )
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
            # 代码注入开口动作（从 dialogue 取 speaker + 从 cues 取时长）
            motion_prompt = _inject_mouth_motion(motion_prompt, seg, seg_cues)
            image_prompt = seg.get("image_prompt") or ""
            logger.info(
                "clip %s/%s building segment %s | %s | image_chars=%s motion_chars=%s",
                ordinal,
                total,
                index,
                params_desc,
                len(image_prompt),
                len(motion_prompt),
            )

            i2v_sem: Semaphore | None = None
            if provider in _I2V_PROVIDERS:
                i2v_sem = _ensure_i2v_semaphore()
                logger.info(
                    "clip segment %s: waiting i2v slot (max_workers=%s)...",
                    index,
                    _i2v_max_workers,
                )
                i2v_sem.acquire()
                logger.info("clip segment %s: acquired i2v slot", index)
            try:
                if job_id is not None:
                    job_cancel.raise_if_cancelled(job_id)
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
                    job_id=job_id,
                )
            finally:
                if i2v_sem is not None:
                    i2v_sem.release()
                    logger.info("clip segment %s: released i2v slot", index)

            elapsed = time.time() - t0
            logger.info(
                "clip %s/%s done segment %s in %.1fs | %s",
                ordinal,
                total,
                index,
                elapsed,
                params_desc,
            )
            return seg["id"], clip_path, elapsed

        segment_clips: list[tuple[int, Path]] = []
        if max_workers <= 1:
            for i, seg in enumerate(targets, 1):
                seg_id, clip_path, gen_sec = build_one(seg, i)
                segment_clips.append((seg_id, clip_path))
                if on_clip_done is not None:
                    on_clip_done(seg_id, clip_path, gen_sec)
        else:
            import gevent
            from gevent.pool import Pool

            pool = Pool(size=max_workers)
            green_lets = [
                pool.spawn(build_one, seg, i) for i, seg in enumerate(targets, 1)
            ]
            pending = set(green_lets)
            job_id = int(job["id"]) if job is not None and job.get("id") is not None else None
            try:
                while pending:
                    if job_id is not None and job_cancel.is_cancelled(job_id):
                        exc = JobCancelledError(f"job {job_id} aborted")
                        for g in list(pending):
                            g.kill(exc, block=False)
                        pool.kill(exc, block=False)
                        raise exc
                    ready = [g for g in pending if g.ready()]
                    if not ready:
                        gevent.wait(pending, count=1, timeout=1.0)
                        continue
                    for g in ready:
                        pending.discard(g)
                        seg_id, clip_path, gen_sec = g.get()
                        segment_clips.append((seg_id, clip_path))
                        if on_clip_done is not None:
                            on_clip_done(seg_id, clip_path, gen_sec)
            except JobCancelledError:
                for g in list(pending):
                    g.kill(block=False)
                pool.kill(block=False)
                raise

        elapsed = time.time() - t_start
        logger.info(
            "clip batch done: %s/%s in %.1fs, workers=%s, segments=%s",
            len(segment_clips),
            total,
            elapsed,
            max_workers,
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
        end_path: Path | None = None,
        bgm_path: Path | None = None,
        bgm_volume_db: float = -14.0,
        burn_subtitles: bool = True,
        xfade_duration_sec: float | None = None,
        xfade_transition: str | None = None,
    ) -> MergeResult:
        t0 = time.time()
        log_ffmpeg_hwaccel_config(context="merge")
        logger.info("merge: %s", ffmpeg_hwaccel_config_summary())
        clips_dir = media_dir / "segments"
        sorted_seg_lst = sorted(segments, key=lambda s: s["segment_index"])
        clip_paths: list[Path] = []
        clip_durations: list[float] = []
        for seg in sorted_seg_lst:
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
            if seg["duration_sec"] is None:
                raise ValueError(
                    f"segment {index} 缺少 duration_sec，请从 tts 阶段重跑"
                )
            clip_durations.append(seg["duration_sec"])

        logger.info("merge: concatenating %s clips with pts fix", len(clip_paths))
        body_path = media_dir / "body.mp4"
        body_with_audio = media_dir / "body_with_audio.mp4"
        concat_video_audio_pts_fixed(
            clip_paths,
            audio_path,
            body_with_audio,
            clip_durations=clip_durations,
            xfade_duration_sec=xfade_duration_sec,
            xfade_transition=xfade_transition,
        )
        logger.info("merge: audio merged (pts corrected)")

        # 成片统一 ASS 烧字幕（分镜 clip 不再叠字幕）
        if burn_subtitles:
            subtitle_cues = tts_mgr.load_subtitle_cues(
                tts_mgr.subtitle_cues_path_for(audio_path.parent)
            )
            flat_cues: list[tuple[str, float]] = []
            for seg in sorted_seg_lst:
                index = seg["segment_index"]
                for cue in subtitle_cues:
                    if cue.segment_index != index or cue.duration_sec <= 0:
                        continue
                    flat_cues.append((cue.text, cue.duration_sec))
            if not flat_cues and subtitle_path and subtitle_path.exists():
                logger.warning(
                    "merge: no subtitle_cues.json phrases; subtitle_path=%s unused for burn",
                    subtitle_path.name,
                )
            if flat_cues:
                from app.services.segment.clip.clip_render import burn_ass_subtitles

                base_w, base_h = probe_video_size(body_with_audio)
                work_dir = media_dir / "merge_work"
                work_dir.mkdir(parents=True, exist_ok=True)
                subtitle_style = subtitle_style_for_canvas(base_w, base_h)
                logger.info(
                    "merge: burning %s subtitle cues via ass on %sx%s font_size=%s",
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
                burned = work_dir / "body_with_subs.mp4"
                burn_ass_subtitles(body_with_audio, ass_path, burned)
                shutil.move(burned, body_with_audio)
            else:
                logger.warning("merge: no subtitle cues with duration, skipping burn")
        else:
            logger.info("merge: subtitle burn disabled")

        if bgm_path is not None and bgm_path.exists():
            logger.info(
                "merge: mixing bgm path=%s volume_db=%.1f",
                bgm_path.name,
                bgm_volume_db,
            )
            mixed = media_dir / "body_with_bgm.mp4"
            mix_bgm_into_video(
                body_with_audio,
                bgm_path,
                mixed,
                volume_db=bgm_volume_db,
            )
            shutil.move(mixed, body_with_audio)

        final_path = media_dir / "final.mp4"
        if intro_path and intro_path.exists():
            logger.info("merge: prepending intro")
            prepend_intro(intro_path, body_with_audio, final_path)
        else:
            shutil.copy2(body_with_audio, final_path)

        if end_path and end_path.exists():
            logger.info("merge: appending end card")
            tmp_final = final_path.with_suffix(".tmp.mp4")
            shutil.move(final_path, tmp_final)
            concat_clips([tmp_final, end_path], final_path)
            tmp_final.unlink(missing_ok=True)

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
        burn_subtitles: bool = True,
    ) -> MergeResult:
        """素材流水线：基底视频 + 字幕烧录 + TTS + 片头。"""
        t0 = time.time()
        log_ffmpeg_hwaccel_config(context="merge_material")
        logger.info("merge_material: %s", ffmpeg_hwaccel_config_summary())
        subtitle_cues = tts_mgr.load_subtitle_cues(
            tts_mgr.subtitle_cues_path_for(audio_path.parent)
        )
        if burn_subtitles and not subtitle_cues:
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
        ] if burn_subtitles else []

        work_dir = media_dir / "merge_work"
        work_dir.mkdir(parents=True, exist_ok=True)

        from app.services.segment.clip.clip_render import (
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
            if burn_subtitles:
                logger.warning(
                    "merge_material: no subtitle cues with duration, skipping burn"
                )
            else:
                logger.info("merge_material: subtitle burn disabled")
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
