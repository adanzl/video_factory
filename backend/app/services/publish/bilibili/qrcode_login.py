"""B 站二维码登录：生成二维码、轮询状态并落盘 Cookie。"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass
from threading import Lock
from typing import Any

import requests

from app.services.publish.bilibili.session import BiliSession, USER_AGENT

logger = logging.getLogger(__name__)

QR_GENERATE_URL = "https://passport.bilibili.com/x/passport-login/web/qrcode/generate"
QR_POLL_URL = "https://passport.bilibili.com/x/passport-login/web/qrcode/poll"
QR_SESSION_TTL_SEC = 180

STATUS_WAITING = "waiting"
STATUS_SCANNED = "scanned"
STATUS_CONFIRMED = "confirmed"
STATUS_EXPIRED = "expired"
STATUS_NEED_VERIFY = "need_verify"


@dataclass
class QrLoginSession:
    session_id: str
    qrcode_key: str
    login_url: str
    created_at: float
    status: str = STATUS_WAITING


class BiliQrLoginMgr:
    """二维码登录会话管理。

    先走纯 HTTP 方案；若 B 站后续增加额外校验，可把状态标为 need_verify，
    前端提示用户在手机端完成短信/验证码。
    """

    def __init__(self) -> None:
        self._sessions: dict[str, QrLoginSession] = {}
        self._lock = Lock()

    def create_session(self) -> dict[str, Any]:
        payload = self._request_json(QR_GENERATE_URL)
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict):
            raise RuntimeError("二维码生成返回异常")
        qrcode_key = str(data.get("qrcode_key") or "").strip()
        login_url = str(data.get("url") or "").strip()
        if not qrcode_key or not login_url:
            raise RuntimeError("二维码生成缺少 qrcode_key/url")
        session = QrLoginSession(
            session_id=uuid.uuid4().hex,
            qrcode_key=qrcode_key,
            login_url=login_url,
            created_at=time.time(),
        )
        with self._lock:
            self._prune_locked()
            self._sessions[session.session_id] = session
        return {
            "session_id": session.session_id,
            "status": session.status,
            "expires_in": QR_SESSION_TTL_SEC,
            "qrcode_url": login_url,
            "qrcode_svg": self._build_qrcode_svg_data_url(login_url),
        }

    def poll_session(self, session_id: str) -> dict[str, Any]:
        with self._lock:
            self._prune_locked()
            session = self._sessions.get(session_id)
        if session is None:
            return {
                "ok": False,
                "status": STATUS_EXPIRED,
                "message": "二维码会话不存在或已过期，请重新生成",
            }
        payload, cookies = self._poll_raw(session.qrcode_key)
        parsed = self._parse_poll_payload(payload)
        status = parsed["status"]
        with self._lock:
            if session_id in self._sessions:
                self._sessions[session_id].status = status
        if status == STATUS_NEED_VERIFY:
            return {
                "ok": False,
                "status": STATUS_NEED_VERIFY,
                "message": parsed["message"],
            }
        if status == STATUS_CONFIRMED:
            if not cookies:
                return {
                    "ok": False,
                    "status": STATUS_NEED_VERIFY,
                    "message": (
                        "扫码已确认，但未取到登录 Cookie。"
                        "请在手机端完成短信/验证码后重新扫码"
                    ),
                }
            BiliSession().save({"cookies": cookies, "origins": []})
            checked = BiliSession().check()
            if not checked.get("ok"):
                return {
                    "ok": False,
                    "status": STATUS_NEED_VERIFY,
                    "message": "扫码完成，但登录态校验未通过，请在手机端完成验证码/短信验证后重试",
                }
            with self._lock:
                self._sessions.pop(session_id, None)
            return {
                "ok": True,
                "status": STATUS_CONFIRMED,
                "message": "扫码登录成功",
                "uname": checked.get("uname"),
                "mid": checked.get("mid"),
            }
        return {
            "ok": status in {STATUS_WAITING, STATUS_SCANNED},
            "status": status,
            "message": parsed["message"],
        }

    def _poll_raw(self, qrcode_key: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        response = requests.get(
            QR_POLL_URL,
            params={"qrcode_key": qrcode_key},
            headers={
                "User-Agent": USER_AGENT,
                "Referer": "https://passport.bilibili.com/login",
            },
            timeout=15,
            allow_redirects=False,
        )
        response.raise_for_status()
        payload = response.json()
        cookies = self._cookies_from_response(response)
        return payload, cookies

    @staticmethod
    def _request_json(url: str) -> dict[str, Any]:
        response = requests.get(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Referer": "https://passport.bilibili.com/login",
            },
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, dict) and payload.get("code") not in (0, None):
            raise RuntimeError(str(payload.get("message") or "B 站接口返回失败"))
        return payload

    @staticmethod
    def _build_qrcode_svg_data_url(content: str) -> str:
        import base64
        import io

        try:
            import qrcode
            import qrcode.image.svg
        except ImportError as exc:
            raise RuntimeError("缺少 qrcode 依赖：pip install qrcode") from exc
        image = qrcode.make(content, image_factory=qrcode.image.svg.SvgImage)
        buf = io.BytesIO()
        image.save(buf)
        encoded = base64.b64encode(buf.getvalue()).decode("ascii")
        return f"data:image/svg+xml;base64,{encoded}"

    @staticmethod
    def _parse_poll_payload(payload: dict[str, Any]) -> dict[str, str]:
        data = payload.get("data") if isinstance(payload, dict) else None
        code = data.get("code") if isinstance(data, dict) else None
        message = str(data.get("message") or payload.get("message") or "").strip()
        if code == 0:
            return {"status": STATUS_CONFIRMED, "message": "扫码确认完成，正在校验登录态"}
        if code == 86090:
            return {
                "status": STATUS_SCANNED,
                "message": "已扫码，请在手机端确认；若 B 站要求短信/验证码，也请在手机端完成",
            }
        if code == 86101:
            return {"status": STATUS_WAITING, "message": message or "等待扫码"}
        if code == 86038:
            return {"status": STATUS_EXPIRED, "message": "二维码已过期，请重新生成"}
        lowered = message.lower()
        if any(token in message for token in ("验证码", "短信", "手机验证")) or "verify" in lowered:
            return {
                "status": STATUS_NEED_VERIFY,
                "message": message or "扫码后还需要短信/验证码，请在手机端完成后再试",
            }
        return {
            "status": STATUS_NEED_VERIFY,
            "message": message or "扫码流程需要额外验证，请在手机端完成后重试",
        }

    @staticmethod
    def _cookies_from_response(response: requests.Response) -> list[dict[str, Any]]:
        cookies: list[dict[str, Any]] = []
        for cookie in response.cookies:
            cookies.append(
                {
                    "name": cookie.name,
                    "value": cookie.value,
                    "domain": cookie.domain or ".bilibili.com",
                    "path": cookie.path or "/",
                }
            )
        return cookies

    def _prune_locked(self) -> None:
        now = time.time()
        expired = [
            sid
            for sid, session in self._sessions.items()
            if now - session.created_at > QR_SESSION_TTL_SEC
        ]
        for sid in expired:
            self._sessions.pop(sid, None)


qrcode_login_mgr = BiliQrLoginMgr()
