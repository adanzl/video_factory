"""投稿模块总入口。"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.repositories import repo_job_log
from app.services.publish.bilibili.dynamic import build_fan_dynamic
from app.services.publish.bilibili.schedule import resolve_publish_dtime_from_job
from app.services.publish.bilibili.session import BiliSession, cookie_expired_message
from app.services.publish.bilibili.tags import (
    build_publish_tags,
    resolve_activity_tag,
    resolve_activity_topic,
)
from app.services.publish.bilibili.tid import (
    describe_publish_partition,
    resolve_content_mark_label,
    resolve_copyright,
    resolve_creation_statement,
    resolve_human_type2,
    resolve_tid,
)
from app.services.publish.bilibili.uploader import BiliUploader
from app.utils.final_asset import resolve_final_path_file
from app.utils.job_info import merge_job_info, parse_job_info

__all__ = ["BiliCookieExpired", "PublishMgr", "publish_mgr"]

logger = logging.getLogger(__name__)


class BiliCookieExpired(RuntimeError):
    """远程 Cookie 缺失或失效，需本机同步。"""

    def __init__(self, status: dict[str, Any] | None = None) -> None:
        self.status = status or {}
        super().__init__(str(self.status.get("message") or cookie_expired_message()))


def _format_publish_plan(
    *,
    job_id: int,
    manual: bool,
    pipeline: str,
    title: str,
    tid: int,
    human_type2: int | None,
    copyright: int,
    creation_statement: dict[str, Any] | None,
    content_mark_label: str | None,
    topic_name: str | None,
    topic_id: int | None,
    mission_id: int | None,
    tags: list[str],
    dtime: int | None,
    video_path: Path,
    cover_path: Path | None,
) -> str:
    partition = describe_publish_partition(pipeline).get("display") or f"tid={tid}"
    parts = [
        f"job={job_id}",
        f"manual={manual}",
        f"pipeline={pipeline or 'standard'}",
        f"title={title[:40]!r}",
        f"partition={partition}(tid={tid}"
        + (f",human_type2={human_type2}" if human_type2 is not None else "")
        + ")",
        f"copyright={copyright}",
    ]
    if creation_statement:
        mark_id = creation_statement.get("id")
        mark = content_mark_label or creation_statement.get("content") or mark_id
        parts.append(f"creation_statement={mark_id}({mark})")
    elif content_mark_label:
        parts.append(f"mark={content_mark_label!r}")
    if topic_id:
        topic = topic_name or "?"
        parts.append(f"topic={topic!r}/{topic_id}/{mission_id or 0}")
    tag_preview = ",".join(tags[:5])
    if len(tags) > 5:
        tag_preview += ",..."
    parts.append(f"tags=[{tag_preview}] ({len(tags)})")
    parts.append(f"dtime={dtime if dtime is not None else 'now'}")
    parts.append(f"video={video_path.name}")
    if cover_path:
        parts.append(f"cover={cover_path.name}")
    return "bili publish plan: " + " ".join(parts)


def _format_publish_result(result: dict[str, Any]) -> str:
    status = result.get("status") or "unknown"
    msg = result.get("message") or ""
    bits = [f"bili publish {status}"]
    if result.get("bvid"):
        bits.append(str(result["bvid"]))
    if result.get("tid") is not None:
        bits.append(f"tid={result['tid']}")
    if result.get("human_type2") is not None:
        bits.append(f"human_type2={result['human_type2']}")
    if result.get("mark_id") is not None:
        label = result.get("neutral_mark") or ""
        bits.append(
            f"creation_statement={result['mark_id']}"
            + (f"({label})" if label else "")
        )
    if result.get("topic_id"):
        bits.append(
            f"topic_id={result['topic_id']}/{result.get('mission_id') or 0}"
        )
    if msg and status != "success":
        bits.append(f"msg={msg}")
    return " ".join(bits)


def _log_publish_plan(job_id: int | None, message: str) -> None:
    logger.info(message)
    if job_id is not None:
        repo_job_log.append_log(job_id, "publish", message)


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
        copyright = resolve_copyright(pipeline)
        creation_statement = resolve_creation_statement(pipeline)
        content_mark_label = resolve_content_mark_label(pipeline)
        topic_id: int | None = None
        mission_id: int | None = None
        topic_name: str | None = None
        if pipeline == "chat":
            topic_name = resolve_activity_tag()
            topic = resolve_activity_topic(
                self.session_store().http(),
                topic_name,
            )
            if topic:
                topic_id = int(topic["topic_id"])
                mission_id = int(topic.get("mission_id") or 0)
                topic_name = str(topic.get("topic_name") or topic_name)
        dtime, planned_at = resolve_publish_dtime_from_job(job)
        dynamic = build_fan_dynamic(title, pipeline=pipeline)
        job_id_raw = job.get("id")
        job_id = int(job_id_raw) if job_id_raw is not None else None
        _log_publish_plan(
            job_id,
            _format_publish_plan(
                job_id=job_id or 0,
                manual=manual,
                pipeline=pipeline,
                title=title,
                tid=tid,
                human_type2=human_type2,
                copyright=copyright,
                creation_statement=creation_statement,
                content_mark_label=content_mark_label,
                topic_name=topic_name,
                topic_id=topic_id,
                mission_id=mission_id,
                tags=tags,
                dtime=dtime,
                video_path=video_path,
                cover_path=cover_path,
            ),
        )
        result = self.publish(
            title=title,
            video_path=video_path,
            cover_path=cover_path,
            description=description,
            tags=tags,
            tid=tid,
            copyright=copyright,
            dtime=dtime,
            dynamic=dynamic,
            human_type2=human_type2,
            creation_statement=creation_statement,
            topic_id=topic_id,
            mission_id=mission_id,
        )
        if content_mark_label:
            result["neutral_mark"] = content_mark_label
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
        copyright: int | None = None,
        dtime: int | None = None,
        dynamic: str = "",
        human_type2: int | None = None,
        creation_statement: dict[str, Any] | None = None,
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
            copyright=copyright if copyright is not None else resolve_copyright(None),
            dtime=dtime,
            dynamic=dynamic,
            human_type2=human_type2,
            creation_statement=creation_statement,
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
        copyright: int,
        dtime: int | None = None,
        dynamic: str = "",
        human_type2: int | None = None,
        creation_statement: dict[str, Any] | None = None,
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
            copyright=copyright,
            dtime=dtime,
            dynamic=dynamic,
            human_type2=human_type2,
            creation_statement=creation_statement,
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
