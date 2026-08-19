"""投稿模块总入口。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.services.publish.bilibili.session import BiliSession, cookie_expired_message

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

    def publish(
        self,
        *,
        title: str,
        video_path: Path,
        cover_path: Path | None,
    ) -> dict:
        self.require_session()
        return self._publish_bili(
            title=title,
            video_path=video_path,
            cover_path=cover_path,
        )

    def _publish_bili(
        self,
        *,
        title: str,
        video_path: Path,
        cover_path: Path | None,
    ) -> dict:
        """B 站投稿（浏览器 Cookie，待接入上传）。"""
        return {
            "platform": "bilibili",
            "status": "skipped",
            "message": "publish adapter not configured",
            "title": title,
            "video_path": str(video_path),
            "cover_path": str(cover_path) if cover_path else None,
        }


publish_mgr = PublishMgr()
