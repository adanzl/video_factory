"""B 站账号密码登录（Playwright）。验证码/短信需在有头窗口内完成。"""

from __future__ import annotations

import logging
import re
import time
from typing import Any

from app.config import get_settings
from app.services.publish.bilibili.session import (
    COOKIE_BILI_JCT,
    COOKIE_SESSDATA,
    BiliSession,
    USER_AGENT,
)

logger = logging.getLogger(__name__)

LOGIN_URL = "https://passport.bilibili.com/login"
_STEALTH_JS = (
    "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
)
_LAUNCH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--disable-dev-shm-usage",
]
_PASSWORD_TAB_LABELS = ("密码登录", "账号登录")
_ACCOUNT_BOX = 'input[placeholder*="账号"], input[placeholder*="手机号"], input[placeholder*="邮箱"]'
_PASSWORD_BOX = 'input[type="password"]'


class BiliPasswordLogin:
    """用 .env 账号密码登录，成功后把 storage_state 交给 BiliSession。"""

    def __init__(self, session: BiliSession | None = None) -> None:
        self.session = session or BiliSession()

    def login(self, *, force: bool = False) -> dict[str, Any]:
        if not force:
            status = self.session.check()
            if status.get("ok"):
                logger.info("bilibili already logged in as %s", status.get("uname"))
                return {"status": "already", **status}

        settings = get_settings()
        username = (settings.bili_username or "").strip()
        password = settings.bili_password or ""
        if not username or not password:
            raise ValueError("缺少 BILI_USERNAME / BILI_PASSWORD")

        logger.info("bilibili password login as %s", username)
        state = self._playwright_login(
            username,
            password,
            headless=bool(settings.bili_browser_headless),
            timeout_sec=int(settings.bili_browser_timeout_sec),
        )
        self.session.save(state)
        status = self.session.check()
        if not status.get("ok"):
            raise RuntimeError(status.get("message") or "登录后校验失败")
        return {"status": "ok", **status}

    def _playwright_login(
        self,
        username: str,
        password: str,
        *,
        headless: bool,
        timeout_sec: int,
    ) -> dict[str, Any]:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError(
                "需要 playwright：pip install playwright && playwright install chromium"
            ) from exc

        timeout_ms = max(30, timeout_sec) * 1000
        with sync_playwright() as playwright:
            browser = self._launch_browser(playwright, headless=headless)
            try:
                context = browser.new_context(
                    user_agent=USER_AGENT,
                    viewport={"width": 1280, "height": 800},
                    locale="zh-CN",
                )
                context.add_init_script(_STEALTH_JS)
                page = context.new_page()
                page.set_default_timeout(timeout_ms)
                page.goto(LOGIN_URL, wait_until="load")
                self._ensure_password_form(page)
                self._fill_credentials(page, username, password)
                self._click_login(page)
                if not headless:
                    logger.info("若出现验证码或短信验证，请在打开的浏览器窗口内完成")
                self._wait_session_cookies(context, page, timeout_ms=timeout_ms)
                return context.storage_state()
            finally:
                browser.close()

    @staticmethod
    def _launch_browser(playwright: Any, *, headless: bool) -> Any:
        kwargs: dict[str, Any] = {
            "headless": headless,
            "args": list(_LAUNCH_ARGS),
        }
        try:
            return playwright.chromium.launch(channel="chrome", **kwargs)
        except Exception:
            return playwright.chromium.launch(**kwargs)

    @staticmethod
    def _password_input(page: Any) -> Any:
        return page.locator(_PASSWORD_BOX).first

    @classmethod
    def _ensure_password_form(cls, page: Any) -> None:
        password_box = cls._password_input(page)
        try:
            if password_box.is_visible():
                return
        except Exception:
            pass
        for label in _PASSWORD_TAB_LABELS:
            loc = page.get_by_text(label, exact=True)
            try:
                if loc.count() and loc.first.is_visible():
                    loc.first.click()
                    break
            except Exception:
                continue
        try:
            password_box.wait_for(state="visible", timeout=15000)
        except Exception as exc:
            raise RuntimeError("未找到账号或密码输入框，登录页结构可能已改") from exc

    @staticmethod
    def _fill_credentials(page: Any, username: str, password: str) -> None:
        account = page.locator(_ACCOUNT_BOX).first
        password_box = page.locator(_PASSWORD_BOX).first
        account.wait_for(state="visible", timeout=10000)
        password_box.wait_for(state="visible", timeout=10000)
        account.click()
        account.fill(username)
        password_box.click()
        password_box.fill(password)

    @staticmethod
    def _click_login(page: Any) -> None:
        button = page.get_by_role("button", name=re.compile(r"^登录$"))
        try:
            button.first.wait_for(state="visible", timeout=5000)
        except Exception:
            button = page.get_by_text("登录", exact=True)
        try:
            button.first.click()
        except Exception as exc:
            raise RuntimeError("未找到登录按钮") from exc

    @staticmethod
    def _wait_session_cookies(context: Any, page: Any, *, timeout_ms: int) -> None:
        deadline = time.monotonic() + timeout_ms / 1000
        hints = ("账号或密码错误", "用户名或密码错误", "验证码错误")
        while time.monotonic() < deadline:
            names = {
                str(item.get("name") or "")
                for item in context.cookies()
                if isinstance(item, dict)
            }
            if COOKIE_SESSDATA in names and COOKIE_BILI_JCT in names:
                return
            try:
                body = page.inner_text("body")
            except Exception:
                body = ""
            for hint in hints:
                if hint in body:
                    raise RuntimeError(hint)
            time.sleep(0.5)
        shot = get_settings().bili_cookie_path.parent / "last_login.png"
        try:
            shot.parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(shot), full_page=True)
            logger.warning("login timeout screenshot: %s", shot)
        except Exception:
            shot = None
        extra = f" url={page.url}"
        if shot:
            extra += f" screenshot={shot}"
        raise RuntimeError(
            "登录超时：请在窗口内完成验证码/短信后重试，或确认账号密码正确"
            + extra
        )
