from __future__ import annotations

from app.repositories import job_log_repo, job_repo
from app.repositories.connection import connection
from app.services.visual.visual_mgr import generate_cover
from worker.context import JobContext
from worker.stages.base import StageExecutor


class CoverStage(StageExecutor):
    name = "cover"

    def run(self, ctx: JobContext) -> None:
        cover_path = ctx.rel("cover.jpg")
        generate_cover(ctx.job["title"], cover_path)
        with connection() as conn:
            job_repo.update_job(conn, ctx.job["id"], cover_path=str(cover_path))
            job_log_repo.append_log(conn, ctx.job["id"], self.name, f"cover at {cover_path}")
