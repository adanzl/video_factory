from __future__ import annotations

from app.repositories import repo_job, repo_job_log
from app.repositories.connection import connection
from app.utils.job_info import content_style_from_job
from worker.context import JobContext
from worker.stages.base import StageExecutor


class PublishStage(StageExecutor):
    """发布阶段：生成标签与视频介绍（若缺失），并标记可手动投稿。"""

    name = "publish"

    def run(self, ctx: JobContext) -> None:
        job_id = ctx.job["id"]
        with connection() as conn:
            job = repo_job.get_job(conn, job_id)
            script = job.get("script_json")
            if not isinstance(script, dict):
                raise RuntimeError("script not ready for publish")

            title = str(script.get("title") or job.get("title") or "").strip()
            narration = str(script.get("narration") or "").strip()
            if not title or not narration:
                raise RuntimeError("title/narration empty, cannot generate publish meta")

            need_description = not str(script.get("video_description") or "").strip()
            need_tags = not (isinstance(script.get("tags"), list) and script.get("tags"))
            if not need_description and not need_tags:
                repo_job_log.append_log(
                    conn,
                    job_id,
                    self.name,
                    "publish meta ready; manual publish: copy description/tags and download cover/final",
                )
                return
            content_style = content_style_from_job(job)
            updated = dict(script)

        # LLM 必须在事务外，避免长占 SQLite 锁卡死 gevent hub
        from app.services.llm.llm_mgr import llm_mgr

        notes: list[str] = []
        warn_logs: list[str] = []

        if need_description:
            try:
                updated["video_description"] = llm_mgr.generate_video_description(
                    title,
                    narration,
                    content_style=content_style,
                )
                notes.append("video_description generated")
            except Exception as exc:
                warn_logs.append(f"video description failed: {exc}")

        if need_tags:
            try:
                updated["tags"] = llm_mgr.generate_tags(
                    title,
                    narration,
                    content_style=content_style,
                )
                notes.append("tags generated")
            except Exception as exc:
                warn_logs.append(f"tags failed: {exc}")

        with connection() as conn:
            for msg in warn_logs:
                repo_job_log.append_log(
                    conn, job_id, self.name, msg, level="warning"
                )
            if notes:
                repo_job.update_job(conn, job_id, script_json=updated)
                repo_job_log.append_log(
                    conn,
                    job_id,
                    self.name,
                    "; ".join(notes)
                    + "; manual publish: copy description/tags and download cover/final",
                )
            else:
                repo_job_log.append_log(
                    conn,
                    job_id,
                    self.name,
                    "publish meta generation skipped; manual publish: copy description and download cover/final",
                )
