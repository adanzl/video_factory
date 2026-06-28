"""历史悬案片头与封面（历史悬案主题色）。"""

from __future__ import annotations

from app.repositories import job_repo
from app.repositories.connection import connection
from worker.context import JobContext
from worker.stages.base import StageExecutor
from app.utils.job_info import INTRO_CATEGORY_HISTORY
from worker.stages.intro.base import run_intro_for_category


class HistoryMysteryIntroStage(StageExecutor):
    name = "intro"

    def run(self, ctx: JobContext) -> None:
        with connection() as conn:
            job = job_repo.get_job(conn, ctx.job["id"])
        run_intro_for_category(
            ctx,
            job,
            category=INTRO_CATEGORY_HISTORY,
            stage=self,
        )
