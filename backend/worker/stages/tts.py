from __future__ import annotations

from app.config import get_settings
from app.quality.checkers import check_tts_audio
from app.quality.gate import apply_quality_checks
from app.repositories import job_log_repo, job_repo, segment_repo
from app.repositories.connection import connection
from app.services.media.audio_analysis import analyze_loudness, analyze_silence, normalize_loudness
from app.services.tts.tts_mgr import synthesize
from worker.context import JobContext
from worker.stages.base import StageExecutor


class TTSStage(StageExecutor):
    name = "tts"

    def run(self, ctx: JobContext) -> None:
        settings = get_settings()
        with connection() as conn:
            job = job_repo.get_job(conn, ctx.job["id"])
            segments = segment_repo.list_segments(conn, ctx.job["id"])
        script = job.get("script_json") or {}
        result = synthesize(script.get("narration", ""), segments, ctx.media_dir / "audio")
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

        with connection() as conn:
            for seg, duration in zip(segments, result.segment_durations):
                segment_repo.update_segment(conn, seg["id"], duration_sec=duration)
                seg["duration_sec"] = duration
            job_repo.update_job(
                conn,
                ctx.job["id"],
                audio_path=str(result.audio_path),
                subtitle_path=str(result.subtitle_path),
                tts_usage_json=result.usage_summary(),
            )
            job_log_repo.append_log(
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
                    ),
                },
                existing_report=job.get("quality_report"),
            )
