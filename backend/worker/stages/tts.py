from __future__ import annotations

from app.repositories import job_log_repo, job_repo, segment_repo
from app.repositories.connection import connection
from app.services.tts.tts_mgr import synthesize
from worker.context import JobContext
from worker.stages.base import StageExecutor


class TTSStage(StageExecutor):
    name = "tts"

    def run(self, ctx: JobContext) -> None:
        with connection() as conn:
            job = job_repo.get_job(conn, ctx.job["id"])
            segments = segment_repo.list_segments(conn, ctx.job["id"])
        script = job.get("script_json") or {}
        result = synthesize(script.get("narration", ""), segments, ctx.media_dir / "audio")
        with connection() as conn:
            for seg, duration in zip(segments, result.segment_durations):
                segment_repo.update_segment(conn, seg["id"], duration_sec=duration)
            job_repo.update_job(
                conn,
                ctx.job["id"],
                audio_path=str(result.audio_path),
                subtitle_path=str(result.subtitle_path),
            )
            job_log_repo.append_log(
                conn,
                ctx.job["id"],
                self.name,
                f"audio {result.duration_sec:.1f}s",
            )
