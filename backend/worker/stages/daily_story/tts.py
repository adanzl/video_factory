"""日常故事（对话）多角色 TTS 阶段。"""

from __future__ import annotations

import logging
from pathlib import Path

from app.config import get_settings
from app.quality.quality_mgr import apply_quality_checks, check_tts_audio
from app.repositories import repo_job_log, repo_job, repo_segment
from app.repositories.connection import connection
from app.services.tts.audio_analysis import analyze_loudness, analyze_silence, normalize_loudness
from app.services.tts.tts_mgr import tts_mgr, SubtitleCue
from app.services.media.ffmpeg_utils import concat_clips, probe_duration
from app.utils.job_info import parse_job_info
from worker.context import JobContext
from worker.stages.base import StageExecutor

logger = logging.getLogger(__name__)

# 默认角色配置（昭昭/灿灿）
_DEFAULT_SPEAKER_CONFIGS: dict[str, dict] = {
    "昭昭": {"voice_id": "cosyvoice-v3.5-flash-leo-f9d115bfdf2346edbeb9d21ecd4f9ce9", "speech_rate": 1.1},
    "灿灿": {"voice_id": "cosyvoice-v3.5-flash-leo-60621bdce780434ab0734555e5196d7d", "speech_rate": 1.1},
}


class DailyTtsStage(StageExecutor):
    """日常对话多角色 TTS。

    每个 segment 的 dialogue 数组含 speaker/text，按角色分别合成后拼接。
    """

    name = "tts"

    def run(self, ctx: JobContext) -> None:
        settings = get_settings()
        with connection() as conn:
            job = repo_job.get_job(conn, ctx.job["id"])
            segments = repo_segment.list_segments(conn, ctx.job["id"])

        script = job.get("script_json") or {}
        info = parse_job_info(job.get("info"))

        # 从 context 或 job.info 读取角色配置
        speaker_configs = ctx.tts_speaker_configs or info.get("tts", {}).get("speaker_configs") or _DEFAULT_SPEAKER_CONFIGS

        # 持久化到 job.info 以便下次复用
        self._persist_speaker_configs(job["id"], speaker_configs)

        result = self._synthesize_multi_speaker(
            script,
            segments,
            ctx.media_dir / "audio",
            speaker_configs,
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
        script: dict,
        segments: list[dict],
        output_dir: Path,
        speaker_configs: dict[str, dict],
    ) -> dict:
        """按角色分别合成每个分镜的对话，然后拼接。"""
        from app.services.tts.tts_ali import _run_tts_task, _audio_extension, VOICE_MODEL_MAP
        from app.services.tts.breath_cue import build_phrase_breath_cues
        from app.services.tts.phrase_timing import build_segment_tts_text, normalize_word_timestamps
        from app.services.tts.segment_trim import apply_tts_segment_trim
        from app.services.tts.tts_leadin import prepare_lead_in, strip_tts_lead_in
        from app.services.media.ffmpeg_utils import build_srt_from_cues

        output_dir.mkdir(parents=True, exist_ok=True)
        clips_dir = output_dir / "clips"
        clips_dir.mkdir(parents=True, exist_ok=True)

        ext = _audio_extension()
        all_subtitle_cues: list[SubtitleCue] = []
        segment_durations: list[float] = []
        clip_paths: list[Path] = []
        total_chars = 0

        for seg in segments:
            seg_index = seg["segment_index"]
            dialogue = seg.get("dialogue") or []

            if not dialogue:
                # 无 dialogue 结构，回退到单角色合成
                return self._fallback_single_voice(seg, segments, output_dir, speaker_configs)

            # 为每个角色的台词分别合成
            seg_clips: list[Path] = []
            seg_cues: list[SubtitleCue] = []
            time_offset = 0.0

            for line_idx, line in enumerate(dialogue):
                speaker = line.get("speaker", "")
                text = (line.get("text") or "").strip()
                if not text:
                    continue

                config = speaker_configs.get(speaker, {})
                voice = config.get("voice_id") or _DEFAULT_SPEAKER_CONFIGS.get(speaker, {}).get("voice_id", "")
                rate = config.get("speech_rate", 1.0)

                # 合成单句
                result = _run_tts_task(text, word_timestamps=True, rate=rate, voice=voice)
                line_clip = clips_dir / f"{seg_index}_{line_idx}{ext}"
                line_clip.write_bytes(result.audio)

                words = normalize_word_timestamps(result.words)
                if words:
                    words = apply_tts_segment_trim(line_clip, words)

                line_duration = probe_duration(line_clip)

                # 构建字幕 cue
                seg_cues.append(SubtitleCue(
                    segment_index=seg_index,
                    text=text,
                    duration_sec=line_duration,
                ))

                seg_clips.append(line_clip)
                time_offset += line_duration

                if result.usage:
                    total_chars += int(result.usage.get("characters") or 0)

            # 拼接该分镜的所有角色音频
            seg_clip = clips_dir / f"{seg_index}{ext}"
            if len(seg_clips) == 1:
                seg_clips[0].rename(seg_clip)
            elif seg_clips:
                concat_clips(seg_clips, seg_clip)
            else:
                # 空分镜，生成静音
                seg_clip.write_bytes(b"")

            seg_duration = probe_duration(seg_clip)
            segment_durations.append(seg_duration)
            clip_paths.append(seg_clip)
            all_subtitle_cues.extend(seg_cues)

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
