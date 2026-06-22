from __future__ import annotations

from app.repositories import job_log_repo
from app.repositories.connection import connection
from worker.context import JobContext
from worker.stages.base import StageExecutor


class PublishStage(StageExecutor):
    """发布阶段：不再调用平台 API，仅标记任务完成（素材在发布页手动下载/复制）。"""

    name = "publish"

    def run(self, ctx: JobContext) -> None:
        with connection() as conn:
            job_log_repo.append_log(
                conn,
                ctx.job["id"],
                self.name,
                "manual publish: copy description and download cover/final from publish page",
            )
