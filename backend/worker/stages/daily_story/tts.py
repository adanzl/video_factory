"""日常故事（对话）多角色 TTS 阶段。"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

from app.config import get_settings
from app.quality.quality_mgr import apply_quality_checks, check_tts_audio
from app.repositories import repo_job_log, repo_job, repo_segment
from app.repositories.connection import connection
from app.services.tts.audio_analysis import analyze_loudness, analyze_silence, normalize_loudness
from app.services.tts.tts_mgr import tts_mgr, SubtitleCue
from app.services.media.ffmpeg_utils import concat_clips, generate_silent_mp3, probe_duration
from app.utils.job_info import parse_job_info
from worker.context import JobContext
from worker.stages.base import StageExecutor

logger = logging.getLogger(__name__)

# 默认角色配置（昭昭/灿灿）
_DEFAULT_SPEAKER_CONFIGS: dict[str, dict] = {
    "昭昭": {"voice_id": "cosyvoice-v3.5-flash-leo-f9d115bfdf2346edbeb9d21ecd4f9ce9", "speech_rate": 1.0},
    "灿灿": {"voice_id": "cosyvoice-v3.5-flash-leo-60621bdce780434ab0734555e5196d7d", "speech_rate": 1.0},
}
_DEFAULT_PHRASE_GAP_SEC = 0.3
_TTS_MAX_RETRIES = 3
_TTS_RETRY_BASE_DELAY = 2.0  # seconds


@dataclass(frozen=True)
class _SegResult:
    """单个分镜的合成结果。"""
    seg_index: int
    clip_path: Path
    cues: list[SubtitleCue]
    duration: float
    chars: int


def _tts_with_retry(text: str, *, word_timestamps: bool, rate: float, voice: str):
    """带重试的 TTS 调用，指数退避。"""
    from app.services.tts.tts_ali import _run_tts_task

    last_err: Exception | None = None
    for attempt in range(1, _TTS_MAX_RETRIES + 1):
        try:
            return _run_tts_task(text, word_timestamps=word_timestamps, rate=rate, voice=voice)
        except Exception as exc:
            last_err = exc
            if attempt < _TTS_MAX_RETRIES:
                delay = _TTS_RETRY_BASE_DELAY * (2 ** (attempt - 1))
                logger.warning(
                    "tts attempt %d/%d failed (voice=%s): %s — retrying in %.1fs",
                    attempt, _TTS_MAX_RETRIES, voice, exc, delay,
                )
                time.sleep(delay)
            else:
                logger.error(
                    "tts all %d attempts failed (voice=%s): %s",
                    _TTS_MAX_RETRIES, voice, exc,
                )
    raise last_err  # type: ignore[misc]


def _synthesize_segment_dialogue(
    seg: dict,
    clips_dir: Path,
    ext: str,
    speaker_configs: dict[str, dict],
    phrase_gap_sec: float,
    *,
    job_id: int | None = None,
) -> _SegResult:
    """合成单个分镜的多角色对话，返回结果。可在线程池中并发执行。"""
    from app.services.tts.tts_ali import _run_tts_task
    from app.services.tts.phrase_timing import normalize_word_timestamps
    from app.services.tts.segment_trim import apply_tts_segment_trim
    from app.services.tts.tts_leadin import prepare_lead_in, strip_tts_lead_in

    seg_index = seg["segment_index"]
    dialogue = seg.get("dialogue") or []

    if not dialogue:
        # 空分镜，生成静音
        seg_clip = clips_dir / f"{seg_index}{ext}"
        seg_clip.write_bytes(b"")
        return _SegResult(seg_index=seg_index, clip_path=seg_clip, cues=[], duration=0.0, chars=0)

    logger.info("tts segment %d start lines=%d", seg_index, len(dialogue))

    seg_clips: list[Path] = []
    seg_cues: list[SubtitleCue] = []
    gap_clips: list[Path] = []
    total_chars = 0

    for line_idx, line in enumerate(dialogue):
        speaker = line.get("speaker", "")
        text = (line.get("text") or "").strip()
        if not text:
            continue

        config = speaker_configs.get(speaker, {})
        voice = config.get("voice_id") or _DEFAULT_SPEAKER_CONFIGS.get(speaker, {}).get("voice_id", "")
        rate = config.get("speech_rate", 1.0)

        logger.info(
            "tts segment %d line %d speaker=%s voice=%s rate=%.2f text_chars=%d text=%s",
            seg_index, line_idx, speaker, voice, rate, len(text), text,
        )

        # 引导词：合成前加"那，"，合成后裁掉
        tts_text, lead_in = prepare_lead_in(text, voice=voice)
        
        result = _tts_with_retry(tts_text, word_timestamps=True, rate=rate, voice=voice)
        line_clip = clips_dir / f"{seg_index}_{line_idx}{ext}"
        line_clip.write_bytes(result.audio)

        words = normalize_word_timestamps(result.words)
        if lead_in and words:
            words = strip_tts_lead_in(line_clip, words, lead_in)
        if words:
            words = apply_tts_segment_trim(line_clip, words)

        line_duration = probe_duration(line_clip)

        seg_cues.append(SubtitleCue(
            segment_index=seg_index,
            text=text,
            duration_sec=line_duration,
        ))

        # 非首句前插入句间停留静音
        if seg_clips and phrase_gap_sec > 0:
            gap_path = clips_dir / f"{seg_index}_gap_{line_idx}{ext}"
            generate_silent_mp3(gap_path, phrase_gap_sec)
            gap_clips.append(gap_path)

        seg_clips.append(line_clip)

        if result.usage:
            total_chars += int(result.usage.get("characters") or 0)

    # SRT 时间校正：非末句的 cue 需包含后续 gap 时长，避免从第 2 句起时间偏移
    if len(seg_cues) > 1 and phrase_gap_sec > 0:
        for cue in seg_cues[:-1]:
            cue.duration_sec += phrase_gap_sec

    # 拼接该分镜的所有角色音频（含句间停留）
    seg_clip = clips_dir / f"{seg_index}{ext}"
    interleaved: list[Path] = []
    for i, clip in enumerate(seg_clips):
        if i > 0 and gap_clips:
            interleaved.append(gap_clips[i - 1])
        interleaved.append(clip)
    if len(interleaved) == 1:
        interleaved[0].rename(seg_clip)
    elif interleaved:
        concat_clips(interleaved, seg_clip)
    else:
        seg_clip.write_bytes(b"")

    seg_duration = probe_duration(seg_clip)

    logger.info(
        "tts segment %d done duration=%.2fs cues=%d",
        seg_index, seg_duration, len(seg_cues),
    )

    return _SegResult(
        seg_index=seg_index,
        clip_path=seg_clip,
        cues=seg_cues,
        duration=seg_duration,
        chars=total_chars,
    )


class DailyTtsStage(StageExecutor):
    """日常对话多角色 TTS。

    每个 segment 的 dialogue 数组含 speaker/text，按角色分别合成后拼接。
    """

    name = "tts"
    _job_id: int | None = None

    def run(self, ctx: JobContext) -> None:
        settings = get_settings()
        with connection() as conn:
            job = repo_job.get_job(conn, ctx.job["id"])
            segments = repo_segment.list_segments(conn, ctx.job["id"])

        info = parse_job_info(job.get("info"))

        # 从 context 或 job.info 读取角色配置
        raw_configs = ctx.tts_speaker_configs or info.get("tts", {}).get("speaker_configs") or _DEFAULT_SPEAKER_CONFIGS
        phrase_gap_sec = raw_configs.get("phrase_gap_sec", _DEFAULT_PHRASE_GAP_SEC)
        speaker_configs = {k: v for k, v in raw_configs.items() if k != "phrase_gap_sec"}

        # 持久化到 job.info 以便下次复用
        persist_configs = {**speaker_configs, "phrase_gap_sec": phrase_gap_sec}
        self._persist_speaker_configs(job["id"], persist_configs)

        self._job_id = ctx.job["id"]
        result = self._synthesize_multi_speaker(
            segments,
            ctx.media_dir / "audio",
            speaker_configs,
            phrase_gap_sec,
        )

        normalize_loudness(
            result["audio_path"],
            target_lufs=settings.audio_target_lufs,
            true_peak=settings.audio_true_peak,
        )
        loudness = analyze_loudness(result["audio_path"])
        silence = analyze_silence(
            result["audio_path"],
            noise_db=settings.audio_silence_noise_db,
        )

        with connection() as conn:
            for seg, duration in zip(segments, result["segment_durations"]):
                repo_segment.update_segment(conn, seg["id"], duration_sec=duration)
                seg["duration_sec"] = duration
            repo_job.update_job(
                conn,
                ctx.job["id"],
                audio_path=str(result["audio_path"].resolve()),
                subtitle_path=str(result["subtitle_path"].resolve()),
                tts_usage_json=result.get("usage_summary"),
            )
            repo_job_log.append_log(
                conn,
                ctx.job["id"],
                self.name,
                (
                    f"audio {result['duration_sec']:.1f}s, "
                    f"segments={len(result['segment_durations'])}, "
                    f"cues={len(result['subtitle_cues'])}, "
                    f"lufs={loudness.integrated_lufs}, "
                    f"max_silence={silence.max_gap_sec:.2f}s"
                ),
            )
            apply_quality_checks(
                conn,
                ctx.job["id"],
                self.name,
                {
                    "tts": check_tts_audio(
                        result["audio_path"],
                        result["duration_sec"],
                        subtitle_cues=result["subtitle_cues"],
                        segments=segments,
                        loudness=loudness,
                        silence=silence,
                    ),
                },
                existing_report=job.get("quality_report"),
            )

    def _persist_speaker_configs(self, job_id: int, configs: dict) -> None:
        with connection() as conn:
            job = repo_job.get_job(conn, job_id)
            info = parse_job_info(job.get("info"))
            info.setdefault("tts", {})["speaker_configs"] = configs
            repo_job.update_job(conn, job_id, info_json=info)

    def _synthesize_multi_speaker(
        self,
        segments: list[dict],
        output_dir: Path,
        speaker_configs: dict[str, dict],
        phrase_gap_sec: float = _DEFAULT_PHRASE_GAP_SEC,
    ) -> dict:
        """按角色分别合成每个分镜的对话，分镜间并发，然后拼接。"""
        from app.services.tts.tts_ali import _audio_extension
        from app.services.media.ffmpeg_utils import build_srt_from_cues

        output_dir.mkdir(parents=True, exist_ok=True)
        clips_dir = output_dir / "clips"
        clips_dir.mkdir(parents=True, exist_ok=True)

        ext = _audio_extension()

        # 检查是否有 dialogue 结构
        has_dialogue = any(seg.get("dialogue") for seg in segments)
        if not has_dialogue:
            return self._fallback_single_voice(segments[0], segments, output_dir, speaker_configs)

        settings = get_settings()
        max_workers = min(len(segments), max(1, settings.tts_max_workers))

        logger.info(
            "tts start: segments=%d phrase_gap=%.2fs speakers=%s max_workers=%d",
            len(segments),
            phrase_gap_sec,
            list(speaker_configs.keys()),
            max_workers,
        )

        def _run_seg(seg: dict) -> _SegResult:
            return _synthesize_segment_dialogue(
                seg, clips_dir, ext, speaker_configs, phrase_gap_sec,
                job_id=self._job_id,
            )

        seg_results: list[_SegResult] = []
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {pool.submit(_run_seg, seg): seg for seg in segments}
            for fut in as_completed(futures):
                seg_results.append(fut.result())

        seg_results.sort(key=lambda r: r.seg_index)

        clip_paths = [r.clip_path for r in seg_results]
        all_subtitle_cues: list[SubtitleCue] = []
        segment_durations: list[float] = []
        total_chars = 0
        for r in seg_results:
            all_subtitle_cues.extend(r.cues)
            segment_durations.append(r.duration)
            total_chars += r.chars

        # 拼接所有分镜
        audio_path = output_dir / f"narration{ext}"
        concat_clips(clip_paths, audio_path)
        total_duration = sum(segment_durations)

        # 写字幕
        cues_path = tts_mgr.subtitle_cues_path_for(output_dir)
        tts_mgr.save_subtitle_cues(cues_path, all_subtitle_cues)
        subtitle_path = output_dir / "subtitles.srt"
        subtitle_path.write_text(build_srt_from_cues(all_subtitle_cues), encoding="utf-8")

        logger.info(
            "daily tts done duration=%.2fs cues=%s billing_chars=%s",
            total_duration,
            len(all_subtitle_cues),
            total_chars,
        )

        return {
            "audio_path": audio_path,
            "subtitle_path": subtitle_path,
            "subtitle_cues_path": cues_path,
            "duration_sec": total_duration,
            "segment_durations": segment_durations,
            "subtitle_cues": all_subtitle_cues,
            "usage_summary": {"total_characters": total_chars},
        }

    def _fallback_single_voice(
        self,
        first_seg: dict,
        all_segments: list[dict],
        output_dir: Path,
        speaker_configs: dict,
    ) -> dict:
        """回退到单角色合成（使用灿灿的声音）。"""
        from app.services.tts.tts_ali import AliTTSClient

        can_config = speaker_configs.get("灿灿", _DEFAULT_SPEAKER_CONFIGS["灿灿"])
        client = AliTTSClient()
        narration = ""
        result = client.synthesize(
            narration,
            all_segments,
            output_dir,
            voice=can_config.get("voice_id"),
            speech_rate=can_config.get("speech_rate"),
        )
        return {
            "audio_path": result.audio_path,
            "subtitle_path": result.subtitle_path,
            "subtitle_cues_path": result.subtitle_cues_path,
            "duration_sec": result.duration_sec,
            "segment_durations": result.segment_durations,
            "subtitle_cues": result.subtitle_cues,
            "usage_summary": result.usage_summary(),
        }
