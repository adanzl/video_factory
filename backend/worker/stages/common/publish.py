from __future__ import annotations

from datetime import datetime, timezone

from app.repositories import repo_job, repo_job_log
from app.repositories.sql_exec import atomic
from app.services.publish.publish_mgr import BiliCookieExpired, publish_mgr
from app.utils.job_info import content_style_from_job
from worker.context import JobContext
from worker.stages.base import StageExecutor


class PublishStage(StageExecutor):
    """发布阶段：补全简介/标签，再按登录态上传 B 站。"""

    name = "publish"

    def run(self, ctx: JobContext) -> None:
        job_id = ctx.job["id"]
        ensure_publish_meta(job_id)
        upload_bili_publish(job_id)

    def _ensure_publish_meta(self, job_id: int) -> None:
        with atomic():
            job = repo_job.get_job(job_id)
            script = job.get("script_json")
            if not isinstance(script, dict):
                raise RuntimeError("script not ready for publish")
            title = str(script.get("title") or job.get("title") or "").strip()
            narration = str(script.get("narration") or "").strip()
            if not title or not narration:
                raise RuntimeError("title/narration empty, cannot generate publish meta")
            need_description = not str(script.get("video_description") or "").strip()
            pipeline = str(job.get("pipeline") or "").strip()
            need_tags = pipeline != "chat" and not (
                isinstance(script.get("tags"), list) and script.get("tags")
            )
            if not need_description and (not need_tags):
                repo_job_log.append_log(job_id, self.name, "publish meta ready")
                return
            content_style = content_style_from_job(job)
            updated = dict(script)
        from app.services.llm.llm_mgr import llm_mgr

        notes: list[str] = []
        warn_logs: list[str] = []
        if need_description:
            try:
                updated["video_description"] = llm_mgr.generate_video_description(
                    title, narration, content_style=content_style
                )
                notes.append("video_description generated")
            except Exception as exc:
                warn_logs.append(f"video description failed: {exc}")
        if need_tags:
            try:
                updated["tags"] = llm_mgr.generate_tags(
                    title, narration, content_style=content_style
                )
                notes.append("tags generated")
            except Exception as exc:
                warn_logs.append(f"tags failed: {exc}")
        with atomic():
            for msg in warn_logs:
                repo_job_log.append_log(job_id, self.name, msg, level="warning")
            if notes:
                repo_job.update_job(job_id, script_json=updated)
                repo_job_log.append_log(job_id, self.name, "; ".join(notes))
            else:
                repo_job_log.append_log(
                    job_id, self.name, "publish meta generation skipped"
                )


def ensure_publish_meta(job_id: int) -> None:
    PublishStage()._ensure_publish_meta(job_id)


def upload_bili_publish(job_id: int) -> None:
    with atomic():
        job = repo_job.get_job(job_id)
    try:
        result = publish_mgr.publish_for_job(job)
    except BiliCookieExpired as exc:
        result = {
            "platform": "bilibili",
            "status": "failed",
            "message": str(exc),
            "at": datetime.now(timezone.utc).isoformat(),
        }
        _persist_publish_result(job, result, level="warning")
        return
    except Exception as exc:
        result = {
            "platform": "bilibili",
            "status": "failed",
            "message": f"bilibili upload failed: {exc}",
            "at": datetime.now(timezone.utc).isoformat(),
        }
        _persist_publish_result(job, result, level="warning")
        return
    _persist_publish_result(job, result)


def _persist_publish_result(
    job: dict,
    result: dict,
    *,
    level: str = "info",
) -> None:
    job_id = int(job["id"])
    with atomic():
        publish_mgr.save_job_result(job, result)
        bvid = result.get("bvid") or ""
        repo_job_log.append_log(
            job_id,
            PublishStage.name,
            f"bilibili {result.get('status')}: {result.get('message')}"
            + (f" {bvid}" if bvid else ""),
            level=level,
        )
