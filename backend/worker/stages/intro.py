from __future__ import annotations

from app.repositories import job_log_repo, job_repo
from app.repositories.connection import connection
from app.services.visual.visual_mgr import generate_intro
from worker.context import JobContext
from worker.stages.base import StageExecutor


class IntroStage(StageExecutor):
    name = "intro"

    def run(self, ctx: JobContext) -> None:
        intro_path = ctx.rel("intro.mp4")
        generate_intro(ctx.job["title"], intro_path)
        with connection() as conn:
            job_repo.update_job(conn, ctx.job["id"], intro_path=str(intro_path))
            job_log_repo.append_log(conn, ctx.job["id"], self.name, f"intro at {intro_path}")
