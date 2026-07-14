from __future__ import annotations

from app.config import get_settings
from app.quality.quality_mgr import apply_quality_checks, check_tts_audio
from app.repositories import repo_job_log, repo_job, repo_segment
from app.repositories.connection import connection
from app.services.tts.audio_analysis import analyze_loudness, analyze_silence, normalize_loudness
from app.services.tts.tts_mgr import tts_mgr
from app.utils.media import base_video_duration_sec, material_min_audio_duration_sec
from worker.context import JobContext
from worker.stages.base import StageExecutor


class TTSStage(StageExecutor):
    name = "tts"

    def run(self, ctx: JobContext) -> None:
        settings = get_settings()
        with connection() as conn:
            job = repo_job.get_job(conn, ctx.job["id"])
            segments = repo_segment.list_segments(conn, ctx.job["id"])
        script = job.get("script_json") or {}
        result = tts_mgr.synthesize(
            script.get("narration", ""),
            segments,
            ctx.media_dir / "audio",
            voice=ctx.tts_voice_id,
            speech_rate=ctx.tts_speech_rate,
        )
        normalize_loudness(
            result.audio_path,
            target_lufs=settings.audio_target_lufs,
            true_peak=settings.audio_true_peak,
        )
        loudness = analyze_loudness(result.audio_path)
        silence = analyze_silence(
            result.audio_path,
            noise_db=settings.audio_silence_noise_db,
        )
        min_audio_dur: float | None = None
        if (job.get("pipeline") or "standard").strip() == "material":
            base_dur = base_video_duration_sec(job=job, media_dir=ctx.media_dir)
            min_audio_dur = material_min_audio_duration_sec(base_dur)

        with connection() as conn:
            for seg, duration in zip(segments, result.segment_durations):
                repo_segment.update_segment(conn, seg["id"], duration_sec=duration)
                seg["duration_sec"] = duration
            audio_version = (job.get("audio_version") or 0) + 1
            repo_job.update_job(
                conn,
                ctx.job["id"],
                audio_path=str(result.audio_path.resolve()),
                subtitle_path=str(result.subtitle_path.resolve()),
                tts_usage_json=result.usage_summary(),
                audio_version=audio_version,
            )
            repo_job_log.append_log(
                conn,
                ctx.job["id"],
                self.name,
                (
                    f"audio {result.duration_sec:.1f}s, "
                    f"segments={len(result.segment_durations)}, "
                    f"cues={len(result.subtitle_cues)}, "
                    f"billing_chars={result.total_characters}, "
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
                        result.audio_path,
                        result.duration_sec,
                        subtitle_cues=result.subtitle_cues,
                        segments=segments,
                        loudness=loudness,
                        silence=silence,
                        min_duration_sec=min_audio_dur,
                    ),
                },
                existing_report=job.get("quality_report"),
            )
