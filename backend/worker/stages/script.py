from __future__ import annotations

from app.repositories import job_log_repo, job_repo, segment_repo
from app.repositories.connection import connection
from app.services.llm.llm_mgr import generate_script
from worker.context import JobContext
from worker.stages.base import StageExecutor


class ScriptStage(StageExecutor):
    name = "script"

    def run(self, ctx: JobContext) -> None:
        script = generate_script(ctx.job["title"])
        with connection() as conn:
            job_repo.update_job(conn, ctx.job["id"], script_json=script)
            segment_repo.insert_segments(conn, ctx.job["id"], script["segments"])
            job_log_repo.append_log(
                conn,
                ctx.job["id"],
                self.name,
                f"script ready, segments={len(script['segments'])}",
            )
        ctx.job["script_json"] = script
