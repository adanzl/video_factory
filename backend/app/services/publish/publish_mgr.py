"""投稿模块总入口。"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.services.publish.bilibili.dynamic import build_fan_dynamic
from app.services.publish.bilibili.schedule import resolve_publish_dtime_from_job
from app.services.publish.bilibili.session import BiliSession, cookie_expired_message
from app.services.publish.bilibili.tags import (
    build_publish_tags,
    resolve_activity_tag,
    resolve_activity_topic,
)
from app.services.publish.bilibili.tid import (
    resolve_human_type2,
    resolve_neutral_mark,
    resolve_tid,
)
from app.services.publish.bilibili.uploader import BiliUploader
from app.utils.final_asset import resolve_final_path_file
from app.utils.job_info import merge_job_info, parse_job_info

__all__ = ["BiliCookieExpired", "PublishMgr", "publish_mgr"]


class BiliCookieExpired(RuntimeError):
    """远程 Cookie 缺失或失效，需本机同步。"""

    def __init__(self, status: dict[str, Any] | None = None) -> None:
        self.status = status or {}
        super().__init__(str(self.status.get("message") or cookie_expired_message()))


class PublishMgr:
    """投稿管理器。"""

    def session_store(self) -> BiliSession:
        return BiliSession()

    def session_status(self) -> dict[str, Any]:
        return self.session_store().check()

    def require_session(self) -> dict[str, Any]:
        status = self.session_status()
        if not status.get("ok"):
            raise BiliCookieExpired(status)
        return status

    def publish_for_job(self, job: dict[str, Any], *, manual: bool = False) -> dict[str, Any]:
        settings = get_settings()
        if settings.mock_mode:
            return {
                "platform": "bilibili",
                "status": "skipped",
                "message": "MOCK_MODE，跳过实际上传",
            }
        if job.get("skip_publish") and not manual:
            return {
                "platform": "bilibili",
                "status": "skipped",
                "message": "skip_publish=true，跳过上传",
            }
        existing = parse_job_info(job.get("info")).get("publish_result")
        if (
            not manual
            and isinstance(existing, dict)
            and existing.get("status") == "success"
            and existing.get("bvid")
        ):
            return {**existing, "message": "already published"}

        script = job.get("script_json") if isinstance(job.get("script_json"), dict) else {}
        title = str(job.get("title") or script.get("title") or "").strip()
        description = str(script.get("video_description") or "").strip()
        pipeline = str(job.get("pipeline") or "").strip()
        tags = build_publish_tags(job)
        video_raw = resolve_final_path_file(job.get("final_path"))
        cover_raw = str(job.get("cover_path") or "").strip()
        if not title:
            raise ValueError("title empty")
        if not video_raw:
            raise FileNotFoundError("final video missing")
        video_path = Path(video_raw)
        cover_path = Path(cover_raw) if cover_raw else None
        tid = resolve_tid(pipeline)
        human_type2 = resolve_human_type2(pipeline)
        neutral_mark = resolve_neutral_mark(pipeline)
        topic_id: int | None = None
        mission_id: int | None = None
        if pipeline == "chat":
            topic = resolve_activity_topic(
                self.session_store().http(),
                resolve_activity_tag(),
            )
            if topic:
                topic_id = int(topic["topic_id"])
                mission_id = int(topic.get("mission_id") or 0)
        dtime, planned_at = resolve_publish_dtime_from_job(job)
        dynamic = build_fan_dynamic(title, pipeline=pipeline)
        result = self.publish(
            title=title,
            video_path=video_path,
            cover_path=cover_path,
            description=description,
            tags=tags,
            tid=tid,
            dtime=dtime,
            dynamic=dynamic,
            human_type2=human_type2,
            neutral_mark=neutral_mark,
            topic_id=topic_id,
            mission_id=mission_id,
        )
        if planned_at is not None:
            result["scheduled_at"] = planned_at.isoformat()
        return result

    def publish(
        self,
        *,
        title: str,
        video_path: Path,
        cover_path: Path | None,
        description: str = "",
        tags: list[str] | None = None,
        tid: int | None = None,
        dtime: int | None = None,
        dynamic: str = "",
        human_type2: int | None = None,
        neutral_mark: str | None = None,
        topic_id: int | None = None,
        mission_id: int | None = None,
    ) -> dict:
        self.require_session()
        return self._publish_bili(
            title=title,
            video_path=video_path,
            cover_path=cover_path,
            description=description,
            tags=tags or [],
            tid=tid if tid is not None else resolve_tid(None),
            dtime=dtime,
            dynamic=dynamic,
            human_type2=human_type2,
            neutral_mark=neutral_mark,
            topic_id=topic_id,
            mission_id=mission_id,
        )

    def _publish_bili(
        self,
        *,
        title: str,
        video_path: Path,
        cover_path: Path | None,
        description: str,
        tags: list[str],
        tid: int,
        dtime: int | None = None,
        dynamic: str = "",
        human_type2: int | None = None,
        neutral_mark: str | None = None,
        topic_id: int | None = None,
        mission_id: int | None = None,
    ) -> dict:
        result = BiliUploader(self.session_store()).publish(
            title=title,
            description=description,
            tags=tags,
            video_path=video_path,
            cover_path=cover_path,
            tid=tid,
            dtime=dtime,
            dynamic=dynamic,
            human_type2=human_type2,
            neutral_mark=neutral_mark,
            topic_id=topic_id,
            mission_id=mission_id,
        )
        result["at"] = datetime.now(timezone.utc).isoformat()
        return result

    def save_job_result(self, job: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
        from app.repositories import repo_job

        job_id = int(job["id"])
        info = merge_job_info(job.get("info"), publish_result=result)
        updates: dict[str, Any] = {"info": info}
        if result.get("status") == "success" and result.get("bvid"):
            updates["publish"] = True
        return repo_job.update_job(job_id, **updates)


publish_mgr = PublishMgr()
