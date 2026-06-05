from __future__ import annotations

from pathlib import Path

from app.repositories import job_log_repo, job_repo, segment_repo
from app.repositories.connection import connection
from app.services.media.media_mgr import compose_final
from worker.context import JobContext
from worker.stages.base import StageExecutor


class FFmpegStage(StageExecutor):
    name = "ffmpeg"

    def run(self, ctx: JobContext) -> None:
        with connection() as conn:
            job = job_repo.get_job(conn, ctx.job["id"])
            segments = segment_repo.list_segments(conn, ctx.job["id"])

        result = compose_final(
            media_dir=ctx.media_dir,
            segments=segments,
            audio_path=Path(job["audio_path"]),
            subtitle_path=Path(job["subtitle_path"]) if job.get("subtitle_path") else None,
            intro_path=Path(job["intro_path"]) if job.get("intro_path") else None,
        )

        with connection() as conn:
            for seg_id, clip_path in result.segment_clip_paths:
                segment_repo.update_segment(conn, seg_id, clip_path=str(clip_path))
            job_repo.update_job(conn, ctx.job["id"], final_path=str(result.final_path))
            job_log_repo.append_log(
                conn,
                ctx.job["id"],
                self.name,
                f"final at {result.final_path}",
            )
