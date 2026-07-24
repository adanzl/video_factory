"""片头 stage：按 job.info 片头风格生成 intro / cover。"""
from __future__ import annotations
from app.repositories import repo_job
from app.utils.job_info import intro_category_from_job, intro_generate_category
from worker.context import JobContext
from worker.stages.base import StageExecutor
from worker.stages.intro.base import run_intro_for_category
from app.repositories.sql_exec import atomic
__all__ = ['IntroStage', 'HistoryMysteryIntroStage', 'ScienceIntroStage']

class IntroStage(StageExecutor):
    name = 'intro'

    def run(self, ctx: JobContext) -> None:
        with atomic():
            job = repo_job.get_job(ctx.job['id'])
        run_intro_for_category(ctx, job, stage=self)

class HistoryMysteryIntroStage(IntroStage):
    """兼容旧引用；逻辑已合并至 IntroStage。"""

class ScienceIntroStage(IntroStage):
    """兼容旧引用；逻辑已合并至 IntroStage。"""
