#!/usr/bin/env python3
"""本机登录 B 站，再把 Cookie 同步到远程。

用法（仓库根目录）:

  python scripts/sync_bili_cookie.py
  python scripts/sync_bili_cookie.py --force
  python scripts/sync_bili_cookie.py --sync-only
"""

from __future__ import annotations

import argparse
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

REMOTE_BASE = "/mnt/data/project/video_factory"
REMOTE_COOKIE = f"{REMOTE_BASE}/data/secrets/bilibili/cookies.json"
SSH_CANDIDATES = (
    ("mini", None),
    ("vip.sy.frp.one", 57904),
    ("57c42474b0ea.ofalias.net", 58186),
)
SSH_USER = "leo"

logger = logging.getLogger(__name__)


def _ssh_password() -> str:
    from dotenv import load_dotenv

    load_dotenv(ROOT_DIR / ".env")
    password = os.getenv("SSH_PASSWORD") or ""
    if not password.strip():
        raise RuntimeError("缺少 SSH_PASSWORD")
    return password


def _ssh_prefix(password: str) -> list[str]:
    sshpass = shutil.which("sshpass")
    if not sshpass:
        raise RuntimeError("需要 sshpass：brew install sshpass")
    env_prefix = [sshpass, "-e"]
    os.environ["SSHPASS"] = password
    return env_prefix


def _ssh_base(host: str, port: int | None) -> list[str]:
    cmd = [
        "ssh",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-o",
        "ConnectTimeout=8",
        "-o",
        "PreferredAuthentications=publickey,password",
    ]
    if port:
        cmd.extend(["-p", str(port)])
    cmd.append(f"{SSH_USER}@{host}" if host != "mini" else host)
    return cmd


def _scp_base(host: str, port: int | None) -> list[str]:
    cmd = [
        "scp",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-o",
        "ConnectTimeout=8",
        "-o",
        "PreferredAuthentications=publickey,password",
    ]
    if port:
        cmd.extend(["-P", str(port)])
    return cmd


def _run(cmd: list[str], *, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def _pick_host(prefix: list[str]) -> tuple[str, int | None]:
    last_error = ""
    for host, port in SSH_CANDIDATES:
        probe = prefix + _ssh_base(host, port) + ["echo ok"]
        try:
            result = _run(probe, timeout=12)
        except subprocess.TimeoutExpired:
            logger.info("ssh skip %s: timeout", host)
            continue
        if result.returncode == 0:
            logger.info("ssh host %s", host)
            return host, port
        last_error = (result.stderr or result.stdout or "").strip()
        logger.info("ssh skip %s: %s", host, last_error.splitlines()[-1] if last_error else "fail")
    raise RuntimeError(last_error or "无法连接远程主机")


def _login_local(*, force: bool) -> dict:
    from app.services.publish.bilibili.session import BiliSession

    if force:
        raise RuntimeError("账号密码登录已移除，请先在前端扫码登录，再同步 Cookie")

    session = BiliSession()
    status = session.check()
    if not status.get("ok"):
        raise RuntimeError(
            f"本地 Cookie 无效：{status.get('message') or '未登录'}；"
            "请先在前端投稿页扫码登录"
        )
    logger.info(
        "local cookie ok: %s mid=%s",
        status.get("uname"),
        status.get("mid"),
    )
    if not session.path.is_file():
        raise RuntimeError(f"cookie 文件不存在: {session.path}")
    return {"session": session, "status": "already", **status}


def _sync_cookie(local_path: Path, *, prefix: list[str], host: str, port: int | None) -> None:
    remote_dir = str(Path(REMOTE_COOKIE).parent)
    target = f"{SSH_USER}@{host}:{REMOTE_COOKIE}" if host != "mini" else f"{host}:{REMOTE_COOKIE}"
    logger.info("sync %s -> %s", local_path, target)
    mkdir = prefix + _ssh_base(host, port) + [f"mkdir -p {remote_dir}"]
    result = _run(mkdir)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "").strip())
    scp = prefix + _scp_base(host, port) + [str(local_path), target]
    result = _run(scp, timeout=60)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "").strip())
    chmod = prefix + _ssh_base(host, port) + [f"chmod 600 {REMOTE_COOKIE}"]
    result = _run(chmod)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "").strip())
    logger.info("remote cookie updated")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="本机登录 B 站并同步 Cookie 到远程")
    parser.add_argument("--force", action="store_true", help="强制重新登录后再同步")
    parser.add_argument(
        "--sync-only",
        action="store_true",
        help="不登录，只把本地已有 Cookie 同步到远程",
    )
    args = parser.parse_args()

    if args.sync_only:
        from app.services.publish.bilibili.session import BiliSession

        session = BiliSession()
        status = session.check()
        if not status.get("ok"):
            print(f"local cookie invalid: {status.get('message')}")
            return 1
        logger.info("local cookie ok: %s mid=%s", status.get("uname"), status.get("mid"))
    else:
        login = _login_local(force=bool(args.force))
        session = login["session"]
        status = login

    prefix = _ssh_prefix(_ssh_password())
    host, port = _pick_host(prefix)
    _sync_cookie(session.path, prefix=prefix, host=host, port=port)
    print(
        f"synced: {status.get('uname')} mid={status.get('mid')} "
        f"-> {host}:{REMOTE_COOKIE}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
