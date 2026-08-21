#!/usr/bin/env python3
"""从 mini 拉取 B 站 Cookie 到本机（paramiko，无需 sshpass）。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

REMOTE_COOKIE = "/mnt/data/project/video_factory/data/secrets/bilibili/cookies.json"
LOCAL_COOKIE = ROOT / "data/secrets/bilibili/cookies.json"
HOSTS = (
    ("mini", 22),
    ("vip.sy.frp.one", 57904),
    ("57c42474b0ea.ofalias.net", 58186),
)
SSH_USER = "leo"


def _password() -> str:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    value = os.getenv("SSH_PASSWORD") or ""
    if not value.strip():
        raise RuntimeError("缺少 SSH_PASSWORD")
    return value


def _pull(host: str, port: int, password: str) -> None:
    import paramiko

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        hostname=host,
        port=port,
        username=SSH_USER,
        password=password,
        timeout=10,
        allow_agent=True,
        look_for_keys=True,
    )
    try:
        sftp = client.open_sftp()
        LOCAL_COOKIE.parent.mkdir(parents=True, exist_ok=True)
        sftp.get(REMOTE_COOKIE, str(LOCAL_COOKIE))
        sftp.close()
    finally:
        client.close()


def main() -> int:
    password = _password()
    last_err = ""
    for host, port in HOSTS:
        try:
            _pull(host, port, password)
            from app.services.publish.bilibili.session import BiliSession

            status = BiliSession(path=LOCAL_COOKIE).check()
            if not status.get("ok"):
                print(f"cookie 无效: {status.get('message')}")
                return 1
            print(f"ok: {status.get('uname')} mid={status.get('mid')}")
            print(f"saved: {LOCAL_COOKIE}")
            return 0
        except Exception as exc:
            last_err = str(exc)
            print(f"skip {host}:{port}: {last_err}")
    print(f"拉取失败: {last_err}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
