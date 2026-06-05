from __future__ import annotations

from pathlib import Path

from app.repositories import job_log_repo
from app.repositories.connection import connection
from app.services.publish.publish_mgr import publish
from worker.context import JobContext
from worker.stages.base import StageExecutor


class PublishStage(StageExecutor):
    name = "publish"

    def run(self, ctx: JobContext) -> None:
        if ctx.job.get("skip_publish"):
            with connection() as conn:
                job_log_repo.append_log(conn, ctx.job["id"], self.name, "skipped (skip_publish)")
            return
        video_path = Path(ctx.job.get("final_path") or ctx.rel("final.mp4"))
        cover_path = Path(ctx.job["cover_path"]) if ctx.job.get("cover_path") else None
        result = publish(
            title=ctx.job["title"],
            video_path=video_path,
            cover_path=cover_path,
        )
        with connection() as conn:
            job_log_repo.append_log(
                conn,
                ctx.job["id"],
                self.name,
                f"publish result: {result.get('status')}",
            )
