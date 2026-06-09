from __future__ import annotations

from app.repositories import job_log_repo
from app.repositories.connection import connection
from worker.context import JobContext
from worker.stages.base import StageExecutor


class HostStage(StageExecutor):
    """讲解人叠图占位 stage；HOST_ENABLED 未开或未实现时仅记日志。"""

    name = "host"

    def run(self, ctx: JobContext) -> None:
        with connection() as conn:
            if not ctx.settings.host_enabled:
                job_log_repo.append_log(
                    conn,
                    ctx.job["id"],
                    self.name,
                    "HOST_ENABLED=false，跳过讲解人叠图",
                )
                return
            job_log_repo.append_log(
                conn,
                ctx.job["id"],
                self.name,
                "讲解人叠图尚未接入（占位 stage）",
            )
