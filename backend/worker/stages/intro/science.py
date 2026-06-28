"""童趣科普 / 生活经验等默认片头与封面。"""

from __future__ import annotations

from app.repositories import job_repo
from app.repositories.connection import connection
from worker.context import JobContext
from worker.stages.base import StageExecutor
from worker.stages.intro.base import run_intro_for_category


class ScienceIntroStage(StageExecutor):
    name = "intro"

    def run(self, ctx: JobContext) -> None:
        with connection() as conn:
            job = job_repo.get_job(conn, ctx.job["id"])
        run_intro_for_category(ctx, job, category=None, stage=self)
