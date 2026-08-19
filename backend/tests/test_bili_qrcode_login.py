from __future__ import annotations

import time

from app.services.publish.bilibili.qrcode_login import (
    STATUS_CONFIRMED,
    STATUS_EXPIRED,
    STATUS_NEED_VERIFY,
    STATUS_SCANNED,
    STATUS_WAITING,
    BiliQrLoginMgr,
    QrLoginSession,
)
from app.services.publish.bilibili.session import BiliSession


def test_create_qrcode_session(monkeypatch) -> None:
    mgr = BiliQrLoginMgr()
    monkeypatch.setattr(
        mgr,
        "_request_json",
        lambda _url: {
            "code": 0,
            "data": {
                "qrcode_key": "key-1",
                "url": "https://example.com/login",
            },
        },
    )
    result = mgr.create_session()
    assert result["session_id"]
    assert result["status"] == STATUS_WAITING
    assert result["qrcode_svg"].startswith("data:image/svg+xml;base64,")


def test_parse_poll_payload_statuses() -> None:
    assert BiliQrLoginMgr._parse_poll_payload({"data": {"code": 86101}})["status"] == STATUS_WAITING
    scanned = BiliQrLoginMgr._parse_poll_payload({"data": {"code": 86090}})
    assert scanned["status"] == STATUS_SCANNED
    assert "验证码" in scanned["message"]
    assert BiliQrLoginMgr._parse_poll_payload({"data": {"code": 86038}})["status"] == STATUS_EXPIRED
    assert BiliQrLoginMgr._parse_poll_payload({"data": {"code": 0}})["status"] == STATUS_CONFIRMED
    verify = BiliQrLoginMgr._parse_poll_payload({"data": {"code": 999, "message": "需要短信验证码"}})
    assert verify["status"] == STATUS_NEED_VERIFY


def test_qrcode_status_route_create_and_expire(app_ctx, monkeypatch) -> None:
    from app.services.publish.bilibili import qrcode_login as mod

    client = app_ctx.test_client()
    monkeypatch.setattr(
        mod.qrcode_login_mgr,
        "create_session",
        lambda: {
            "session_id": "sid-1",
            "status": STATUS_WAITING,
            "expires_in": 180,
            "qrcode_url": "https://example.com/login",
            "qrcode_svg": "data:image/svg+xml;base64,abc",
        },
    )
    create_resp = client.post("/v_factory/api/publish/bili/login/qrcode", json={})
    assert create_resp.status_code == 201
    monkeypatch.setattr(
        mod.qrcode_login_mgr,
        "poll_session",
        lambda session_id: {
            "ok": False,
            "status": STATUS_EXPIRED,
            "message": "二维码已过期，请重新生成",
        },
    )
    status_resp = client.get(
        "/v_factory/api/publish/bili/login/qrcode/status?session_id=sid-1"
    )
    assert status_resp.status_code == 410
    body = status_resp.get_json()
    assert body["code"] == "bili_qrcode_expired"


def test_poll_session_confirmed_saves_cookie(monkeypatch, tmp_path) -> None:
    mgr = BiliQrLoginMgr()
    mgr._sessions["sid"] = QrLoginSession(
        session_id="sid",
        qrcode_key="key",
        login_url="https://example.com",
        created_at=time.time(),
        status=STATUS_WAITING,
    )
    monkeypatch.setattr(
        mgr,
        "_poll_raw",
        lambda _key: (
            {"data": {"code": 0}},
            [
                {
                    "name": "SESSDATA",
                    "value": "a",
                    "domain": ".bilibili.com",
                    "path": "/",
                },
                {
                    "name": "bili_jct",
                    "value": "b",
                    "domain": ".bilibili.com",
                    "path": "/",
                },
            ],
        ),
    )
    session = BiliSession(tmp_path / "cookies.json")
    monkeypatch.setattr(
        "app.services.publish.bilibili.qrcode_login.BiliSession",
        lambda: session,
    )
    monkeypatch.setattr(session, "check", lambda: {"ok": True, "uname": "leo", "mid": 1})
    result = mgr.poll_session("sid")
    assert result["ok"] is True
    assert result["status"] == STATUS_CONFIRMED
    assert session.path.is_file()


def test_poll_session_need_verify_when_no_cookie(monkeypatch) -> None:
    mgr = BiliQrLoginMgr()
    mgr._sessions["sid"] = QrLoginSession(
        session_id="sid",
        qrcode_key="key",
        login_url="https://example.com",
        created_at=time.time(),
    )
    monkeypatch.setattr(mgr, "_poll_raw", lambda _key: ({"data": {"code": 0}}, []))
    result = mgr.poll_session("sid")
    assert result["ok"] is False
    assert result["status"] == STATUS_NEED_VERIFY
    assert "Cookie" in result["message"]
