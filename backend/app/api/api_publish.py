from __future__ import annotations

from flask import Blueprint

from app.api.errors import APIError
from app.api.utils import get_query, json_created, json_ok
from app.services.publish.bilibili.publish_config import describe_publish_config
from app.services.publish.bilibili.qrcode_login import qrcode_login_mgr
from app.services.publish.publish_mgr import BiliCookieExpired, publish_mgr

bp = Blueprint("api_publish", __name__, url_prefix="/v_factory/api/publish")


@bp.get("/bili/session")
def bili_session_route():
    try:
        return json_ok(publish_mgr.require_session())
    except BiliCookieExpired as exc:
        raise APIError(str(exc), status_code=401, code="bili_cookie_expired") from exc


@bp.get("/bili/config")
def bili_config_route():
    pipeline = get_query("pipeline")
    http = None
    try:
        publish_mgr.require_session()
        http = publish_mgr.session_store().http()
    except BiliCookieExpired:
        pass
    return json_ok(describe_publish_config(pipeline, http=http))


@bp.post("/bili/login/qrcode")
def create_bili_qrcode_route():
    try:
        return json_created(qrcode_login_mgr.create_session())
    except Exception as exc:
        raise APIError(f"生成 B 站登录二维码失败: {exc}", status_code=502) from exc


@bp.get("/bili/login/qrcode/status")
def poll_bili_qrcode_route():
    session_id = get_query("session_id")
    if not session_id:
        raise APIError("session_id is required")
    try:
        result = qrcode_login_mgr.poll_session(session_id)
    except Exception as exc:
        raise APIError(f"查询 B 站扫码状态失败: {exc}", status_code=502) from exc
    if not result.get("ok") and result.get("status") == "expired":
        raise APIError(str(result.get("message") or "二维码已过期"), status_code=410, code="bili_qrcode_expired")
    return json_ok(result)


@bp.post("/bili/login/logout")
def logout_bili_route():
    session = publish_mgr.session_store()
    session.save({"cookies": [], "origins": []})
    return json_ok({"ok": True, "status": "logged_out"})
