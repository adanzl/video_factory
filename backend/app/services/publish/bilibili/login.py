"""B 站登录：账号密码方式已移除，请用前端扫码。"""

from __future__ import annotations

import logging
from typing import Any

from app.services.publish.bilibili.session import BiliSession

logger = logging.getLogger(__name__)


class BiliPasswordLogin:
    """兼容旧入口：仅复用已有 Cookie，不再支持账号密码。"""

    def __init__(self, session: BiliSession | None = None) -> None:
        self.session = session or BiliSession()

    def login(self, *, force: bool = False) -> dict[str, Any]:
        if not force:
            status = self.session.check()
            if status.get("ok"):
                logger.info("bilibili already logged in as %s", status.get("uname"))
                return {"status": "already", **status}
        raise ValueError("账号密码登录已移除，请在前端投稿页扫码登录")
