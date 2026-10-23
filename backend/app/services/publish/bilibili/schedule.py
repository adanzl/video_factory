"""B 站定时发布：按 HH:MM 计算下一次发布时间。"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

PUBLISH_TZ = ZoneInfo("Asia/Shanghai")
# 任务还没保存过 publish_schedule（从未投稿）时用的默认时分
DEFAULT_PUBLISH_TIME = "07:00"


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


def _skip_weekend(candidate: datetime) -> datetime:
    """周六/周日顺延到下周一，时分不变。"""
    original = candidate
    while candidate.weekday() >= 5:
        candidate += timedelta(days=1)
    if candidate != original:
        logger.info(
            "publish date %s falls on weekend, postponed to %s",
            original.isoformat(),
            candidate.isoformat(),
        )
    return candidate


def resolve_next_publish_dtime(
    time_hm: str,
    *,
    now: datetime | None = None,
    tz: ZoneInfo = PUBLISH_TZ,
) -> tuple[int, datetime]:
    """返回 (unix 秒, 本地计划 datetime)。

    规则：取当天 HH:MM，已过点则 +1 天；结果落在周六/周日则顺延到下周一。
    """
    now_local = (now or datetime.now(tz)).astimezone(tz)
    hour = int(time_hm[:2])
    minute = int(time_hm[3:])
    candidate = now_local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= now_local:
        candidate += timedelta(days=1)
    candidate = _skip_weekend(candidate)
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


def preview_publish_plan(job: dict[str, Any]) -> dict[str, Any] | None:
    """给前端展示用的排期预览（挂在 /jobs/get 的响应里）。

    只按 job 已保存的时分算一次，供页面显示「将于 X 发布」；
    从未投稿的任务还没存时分，按 DEFAULT_PUBLISH_TIME 给一份（defaulted=True）。
    真正投稿时 publish_mgr 会按提交瞬间重新算 dtime，前端不再重算。
    """
    from app.utils.job_info import parse_job_info

    try:
        schedule = parse_publish_schedule(
            parse_job_info(job.get("info")).get("publish_schedule")
        )
    except ValueError:
        return None
    defaulted = schedule is None
    if defaulted:
        schedule = {"enabled": True, "time": DEFAULT_PUBLISH_TIME}
    time_hm = str(schedule.get("time") or "").strip()
    if not schedule.get("enabled") or not time_hm:
        return {
            "enabled": False,
            "time": time_hm or None,
            "next_at": None,
            "defaulted": False,
        }
    _, planned_at = resolve_next_publish_dtime(time_hm)
    return {
        "enabled": True,
        "time": time_hm,
        "next_at": planned_at.isoformat(),
        "defaulted": defaulted,
    }
