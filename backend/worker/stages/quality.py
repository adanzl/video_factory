from __future__ import annotations

from pathlib import Path

from app.quality.orchestrator import run_quality_checks
from app.repositories import job_log_repo, job_repo, segment_repo
from app.repositories.connection import connection
from worker.context import JobContext
from worker.stages.base import StageExecutor


class QualityStage(StageExecutor):
    name = "quality"

    def run(self, ctx: JobContext) -> None:
        with connection() as conn:
            job = job_repo.get_job(conn, ctx.job["id"])
            segments = segment_repo.list_segments(conn, ctx.job["id"])
        script = job.get("script_json") or {}
        audio_path = Path(job["audio_path"]) if job.get("audio_path") else None
        duration = sum(seg.get("duration_sec") or 0 for seg in segments)
        report = run_quality_checks(
            script=script,
            segments=segments,
            audio_path=audio_path,
            duration_sec=duration,
        )
        with connection() as conn:
            job_repo.update_job(
                conn,
                ctx.job["id"],
                quality_report=report.to_dict(),
                fail_stage=report.fail_stage,
            )
            job_log_repo.append_log(
                conn,
                ctx.job["id"],
                self.name,
                f"quality={report.level}",
            )
        if report.level == "major" and report.fail_stage:
            raise RuntimeError(f"quality major, rollback to {report.fail_stage}")
