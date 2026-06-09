from __future__ import annotations

from pathlib import Path

from app.config import get_settings
from app.quality.checkers import check_final
from app.quality.gate import apply_quality_checks
from app.repositories import job_log_repo, job_repo, segment_repo
from app.repositories.connection import connection
from app.services.media.audio_analysis import analyze_loudness
from app.services.media.media_mgr import merge_final
from worker.context import JobContext
from worker.stages.base import StageExecutor


class MergeStage(StageExecutor):
    name = "merge"

    def run(self, ctx: JobContext) -> None:
        with connection() as conn:
            job = job_repo.get_job(conn, ctx.job["id"])
            segments = segment_repo.list_segments(conn, ctx.job["id"])

        result = merge_final(
            media_dir=ctx.media_dir,
            segments=segments,
            audio_path=Path(job["audio_path"]),
            subtitle_path=Path(job["subtitle_path"]) if job.get("subtitle_path") else None,
            intro_path=Path(job["intro_path"]) if job.get("intro_path") else None,
        )
        loudness = analyze_loudness(result.final_path)

        with connection() as conn:
            job_repo.update_job(conn, ctx.job["id"], final_path=str(result.final_path))
            job_log_repo.append_log(
                conn,
                ctx.job["id"],
                self.name,
                (
                    f"final at {result.final_path}, "
                    f"lufs={loudness.integrated_lufs}"
                ),
            )
            apply_quality_checks(
                conn,
                ctx.job["id"],
                self.name,
                {
                    "final": check_final(result.final_path, loudness=loudness),
                },
                existing_report=job.get("quality_report"),
            )
