"""片头 stage：按内容风格分发到具体实现。"""

from __future__ import annotations

from app.repositories import job_repo
from app.repositories.connection import connection
from app.utils.job_info import intro_category_from_job, is_history_intro_category
from worker.context import JobContext
from worker.stages.base import StageExecutor
from worker.stages.intro.history_mystery import HistoryMysteryIntroStage
from worker.stages.intro.science import ScienceIntroStage

__all__ = ["IntroStage", "HistoryMysteryIntroStage", "ScienceIntroStage"]


class IntroStage(StageExecutor):
    name = "intro"

    def run(self, ctx: JobContext) -> None:
        with connection() as conn:
            job = job_repo.get_job(conn, ctx.job["id"])
        if is_history_intro_category(intro_category_from_job(job)):
            HistoryMysteryIntroStage().run(ctx)
            return
        ScienceIntroStage().run(ctx)
