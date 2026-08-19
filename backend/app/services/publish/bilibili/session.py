"""B 站登录态：Cookie 文件读写与 nav 校验。"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

import requests

from app.config import get_settings

logger = logging.getLogger(__name__)

NAV_URL = "https://api.bilibili.com/x/web-interface/nav"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36"
)
COOKIE_SESSDATA = "SESSDATA"
COOKIE_BILI_JCT = "bili_jct"
_REQUIRED_COOKIES = (COOKIE_SESSDATA, COOKIE_BILI_JCT)
COOKIE_EXPIRED_CODE = "bili_cookie_expired"
SYNC_COOKIE_CMD = "请在投稿页重新扫码登录"


def cookie_expired_message() -> str:
    return f"B 站 Cookie 已过期或未登录，{SYNC_COOKIE_CMD}"


def _expired_status(*, reason: str, code: object = None) -> dict[str, Any]:
    status: dict[str, Any] = {
        "ok": False,
        "code": COOKIE_EXPIRED_CODE,
        "message": cookie_expired_message(),
        "reason": reason,
    }
    if code is not None:
        status["nav_code"] = code
    return status


def cookie_path_from_settings() -> Path:
    return get_settings().bili_cookie_path


class BiliSession:
    """本地 Cookie（Playwright storage_state）与登录校验。"""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or cookie_path_from_settings()

    def load(self) -> dict[str, Any]:
        if not self.path.is_file():
            return {"cookies": [], "origins": []}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("bili cookie file unreadable: %s", exc)
            return {"cookies": [], "origins": []}
        if isinstance(data, list):
            return {"cookies": data, "origins": []}
        if not isinstance(data, dict):
            return {"cookies": [], "origins": []}
        cookies = data.get("cookies")
        if not isinstance(cookies, list):
            cookies = []
        origins = data.get("origins")
        if not isinstance(origins, list):
            origins = []
        return {"cookies": cookies, "origins": origins}

    def save(self, state: dict[str, Any] | list[dict[str, Any]]) -> Path:
        if isinstance(state, list):
            payload: dict[str, Any] = {"cookies": state, "origins": []}
        else:
            cookies = state.get("cookies") if isinstance(state, dict) else None
            origins = state.get("origins") if isinstance(state, dict) else None
            payload = {
                "cookies": cookies if isinstance(cookies, list) else [],
                "origins": origins if isinstance(origins, list) else [],
            }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass
        logger.info("bili cookies saved: %s", self.path)
        return self.path

    def cookie_dict(self) -> dict[str, str]:
        result: dict[str, str] = {}
        for item in self.load().get("cookies") or []:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            result[name] = str(item.get("value") or "")
        return result

    def has_session_cookies(self) -> bool:
        cookies = self.cookie_dict()
        return all(bool(cookies.get(name)) for name in _REQUIRED_COOKIES)

    def check(self) -> dict[str, Any]:
        """请求 nav，确认 SESSDATA 仍有效。"""
        cookies = self.cookie_dict()
        if not all(cookies.get(name) for name in _REQUIRED_COOKIES):
            return _expired_status(reason="cookie missing")
        try:
            resp = requests.get(
                NAV_URL,
                cookies=cookies,
                headers={
                    "User-Agent": USER_AGENT,
                    "Referer": "https://www.bilibili.com/",
                },
                timeout=15,
            )
            resp.raise_for_status()
            payload = resp.json()
        except (requests.RequestException, ValueError) as exc:
            return {"ok": False, "message": f"nav request failed: {exc}"}
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict) or not data.get("isLogin"):
            reason = "not logged in"
            if isinstance(payload, dict) and payload.get("message"):
                reason = str(payload["message"])
            return _expired_status(
                reason=reason,
                code=payload.get("code") if isinstance(payload, dict) else None,
            )
        mid = data.get("mid")
        uname = str(data.get("uname") or "").strip()
        return {
            "ok": True,
            "mid": int(mid) if mid is not None else None,
            "uname": uname,
        }
