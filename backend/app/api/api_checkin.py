"""每日签到看板 API：只读 dc-db 结果库 + 手动/定时触发 run.sh + 运行参数读写。"""

from __future__ import annotations

import logging

from flask import Blueprint

from app.api.errors import APIError
from app.api.utils import get_json_body, get_query, json_accepted, json_ok, parse_query_int
from app.services.checkin.checkin_mgr import (
    CheckinBusyError,
    CheckinDisabledError,
    CheckinSettingError,
    checkin_mgr,
)
from app.utils.rds import RedisUnavailable

bp = Blueprint("api_checkin", __name__, url_prefix="/v_factory/api/checkin")

logger = logging.getLogger(__name__)

_PAGE_SIZE_MAX = 200


@bp.get("/overview")
def get_overview_route():
    """看板概览：今日成败、平台汇总、环境与调度状态。"""
    return json_ok(checkin_mgr.overview())


@bp.get("/records")
def get_records_route():
    """签到明细（分页）。"""
    page = parse_query_int("page", 1, required=False, minimum=1)
    page_size = parse_query_int(
        "page_size", 20, required=False, minimum=1, maximum=_PAGE_SIZE_MAX
    )
    return json_ok(
        checkin_mgr.list_records(
            platform=get_query("platform"),
            status=get_query("status"),
            keyword=get_query("keyword"),
            date=get_query("date"),
            page=page,
            page_size=page_size,
        )
    )


@bp.get("/state")
def get_state_route():
    """运行状态轮询：是否在跑、已跑多久、上次结果。"""
    setting, degraded = checkin_mgr.read_setting()
    return json_ok(
        {
            "run_state": checkin_mgr.run_state(),
            "schedule": checkin_mgr.schedule_state(setting),
            "environment": checkin_mgr.environment(setting),
            "redis_ok": not degraded,
        }
    )


@bp.post("/run")
def post_run_route():
    """立即运行一次 run.sh（后台线程，不阻塞请求）。"""
    try:
        state = checkin_mgr.start_run(trigger="manual")
    except CheckinDisabledError as exc:
        raise APIError(str(exc), status_code=400, code="disabled") from exc
    except CheckinBusyError as exc:
        raise APIError(str(exc), status_code=409, code="busy") from exc
    except FileNotFoundError as exc:
        raise APIError(str(exc), status_code=400, code="missing_script") from exc
    except RedisUnavailable as exc:
        # start_run 抛出的消息已带上下文，这里不再套前缀
        raise APIError(str(exc), status_code=503, code="redis_unavailable") from exc
    logger.info("[CHECKIN] manual run triggered")
    return json_accepted(state)


@bp.get("/setting")
def get_setting_route():
    """运行参数（存在 Redis）：脚本名、结果库、超时、定时。未启用时返回空。"""
    enabled = checkin_mgr.is_enabled()
    setting, degraded = checkin_mgr.read_setting()
    return json_ok(
        {
            "enabled": enabled,
            "setting": setting if enabled else {},
            "schedule": checkin_mgr.schedule_state(setting),
            "redis_ok": not degraded,
        }
    )


@bp.put("/setting")
def put_setting_route():
    """保存运行参数并立即按新配置重建定时任务。"""
    if not checkin_mgr.is_enabled():
        raise APIError("未配置 DC_DIR，每日签到未启用", status_code=400, code="disabled")
    body = get_json_body()
    try:
        setting = checkin_mgr.save_setting(body)
    except CheckinSettingError as exc:
        raise APIError(str(exc), status_code=400, code="invalid_setting") from exc
    except RedisUnavailable as exc:
        raise APIError(
            f"签到配置存在 Redis，但当前连不上：{exc}", status_code=503, code="redis_unavailable"
        ) from exc
    from app.core import get_scheduler

    scheduler = get_scheduler()
    if scheduler is not None:
        checkin_mgr.apply_schedule(scheduler)
    logger.info("[CHECKIN] setting updated: %s", setting)
    return json_ok({"setting": setting, "schedule": checkin_mgr.schedule_state()})
