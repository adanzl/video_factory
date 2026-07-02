from __future__ import annotations

import logging

from flask import Blueprint

from app.api.errors import APIError
from app.api.utils import get_json_body, json_ok
from app.services.config_mgr import apply_config_updates, get_config_payload

bp = Blueprint("api_config", __name__, url_prefix="/v_factory/api/config")

logger = logging.getLogger(__name__)


@bp.get("")
def get_config_route():
    """读取 Config 运行时配置（两层分组）。"""
    return json_ok(get_config_payload())


@bp.put("")
def update_config_route():
    """按 Config 属性名更新，持久化到 .env 并热加载。"""
    data = get_json_body()
    updates = data.get("updates")
    if not isinstance(updates, dict):
        raise APIError("updates must be a JSON object")

    try:
        result = apply_config_updates(updates)
    except ValueError as exc:
        raise APIError(str(exc)) from exc

    logger.info("[CONFIG] updated attrs: %s", ", ".join(result["updated"]))
    return json_ok(result)
