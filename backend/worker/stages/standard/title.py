from __future__ import annotations

from app.repositories import job_log_repo, job_repo
from app.repositories.connection import connection
from worker.context import JobContext
from worker.stages.base import StageExecutor


class TitleStage(StageExecutor):
    name = "title"

    def run(self, ctx: JobContext) -> None:
        with connection() as conn:
            job_log_repo.append_log(conn, ctx.job["id"], self.name, "title validated")
