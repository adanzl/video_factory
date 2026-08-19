from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.config import config
from app.services.publish.bilibili.login import BiliPasswordLogin
from app.services.publish.bilibili.session import BiliSession
from app.services.publish.bilibili.tid import resolve_tid


def _cookie_items() -> list[dict]:
    return [
        {
            "name": "SESSDATA",
            "value": "sess",
            "domain": ".bilibili.com",
            "path": "/",
        },
        {
            "name": "bili_jct",
            "value": "csrf",
            "domain": ".bilibili.com",
            "path": "/",
        },
    ]


def test_session_save_load_roundtrip(tmp_path) -> None:
    path = tmp_path / "cookies.json"
    session = BiliSession(path)
    session.save(_cookie_items())
    cookies = session.cookie_dict()
    assert cookies["SESSDATA"] == "sess"
    assert cookies["bili_jct"] == "csrf"
    assert session.has_session_cookies()


def test_session_check_ok(tmp_path, monkeypatch) -> None:
    session = BiliSession(tmp_path / "cookies.json")
    session.save(_cookie_items())
    resp = MagicMock()
    resp.json.return_value = {
        "code": 0,
        "data": {"isLogin": True, "mid": 42, "uname": "leo"},
    }
    monkeypatch.setattr(
        "app.services.publish.bilibili.session.requests.get",
        lambda *args, **kwargs: resp,
    )
    status = session.check()
    assert status["ok"] is True
    assert status["mid"] == 42
    assert status["uname"] == "leo"


def test_session_check_missing_cookie(tmp_path) -> None:
    session = BiliSession(tmp_path / "missing.json")
    status = session.check()
    assert status["ok"] is False
    assert status["message"] == "cookie missing"


def test_login_skips_when_session_valid(tmp_path, monkeypatch) -> None:
    session = BiliSession(tmp_path / "cookies.json")
    monkeypatch.setattr(
        session,
        "check",
        lambda: {"ok": True, "uname": "leo", "mid": 1},
    )
    result = BiliPasswordLogin(session).login()
    assert result["status"] == "already"
    assert result["uname"] == "leo"


def test_login_requires_credentials(tmp_path, monkeypatch) -> None:
    session = BiliSession(tmp_path / "cookies.json")
    monkeypatch.setattr(session, "check", lambda: {"ok": False, "message": "cookie missing"})
    monkeypatch.setattr(config, "bili_username", None)
    monkeypatch.setattr(config, "bili_password", None)
    with pytest.raises(ValueError, match="BILI_USERNAME"):
        BiliPasswordLogin(session).login()


def test_resolve_tid_chat(monkeypatch) -> None:
    monkeypatch.setattr(config, "bili_tid", 201)
    monkeypatch.setattr(config, "bili_tid_chat", 164)
    assert resolve_tid("chat") == 164
    assert resolve_tid("standard") == 201
    assert resolve_tid(None) == 201
