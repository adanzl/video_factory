from __future__ import annotations

from app.repositories import repo_job_log, repo_job
from app.repositories.connection import connection
from worker.context import JobContext
from worker.stages.base import StageExecutor


class TitleStage(StageExecutor):
    name = "title"

    def run(self, ctx: JobContext) -> None:
        with connection() as conn:
            repo_job_log.append_log(conn, ctx.job["id"], self.name, "title validated")
