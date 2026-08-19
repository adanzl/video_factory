"""B 站定时发布：按 HH:MM 计算下一次发布时间。"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

PUBLISH_TZ = ZoneInfo("Asia/Shanghai")


def parse_publish_schedule(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    enabled = bool(raw.get("enabled"))
    time_text = str(raw.get("time") or "").strip()
    if not enabled:
        return {"enabled": False, "time": time_text or None}
    if len(time_text) != 5 or time_text[2] != ":":
        raise ValueError("publish_schedule.time must be HH:MM")
    hour = int(time_text[:2])
    minute = int(time_text[3:])
    if hour > 23 or minute > 59:
        raise ValueError("publish_schedule.time must be HH:MM")
    return {"enabled": True, "time": time_text}


def resolve_next_publish_dtime(
    time_hm: str,
    *,
    now: datetime | None = None,
    tz: ZoneInfo = PUBLISH_TZ,
) -> tuple[int, datetime]:
    """返回 (unix 秒, 本地计划 datetime)。"""
    now_local = (now or datetime.now(tz)).astimezone(tz)
    hour = int(time_hm[:2])
    minute = int(time_hm[3:])
    candidate = now_local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= now_local:
        candidate += timedelta(days=1)
    return int(candidate.timestamp()), candidate


def resolve_publish_dtime_from_job(job: dict[str, Any]) -> tuple[int | None, datetime | None]:
    from app.utils.job_info import parse_job_info

    schedule = parse_publish_schedule(parse_job_info(job.get("info")).get("publish_schedule"))
    if not schedule or not schedule.get("enabled"):
        return None, None
    time_hm = str(schedule.get("time") or "").strip()
    if not time_hm:
        raise ValueError("publish_schedule.time is required when enabled")
    dtime, planned_at = resolve_next_publish_dtime(time_hm)
    return dtime, planned_at
