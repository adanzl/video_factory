"""B 站账号密码登录，把 Cookie 写到 BILI_COOKIE_PATH。

用法（backend 目录）:

  python -m scripts.bili_login
  python -m scripts.bili_login --check
  python -m scripts.bili_login --force
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.publish.bilibili.login import BiliPasswordLogin
from app.services.publish.bilibili.session import BiliSession


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="B 站账号密码登录")
    parser.add_argument("--check", action="store_true", help="只校验已有 Cookie，不打开浏览器")
    parser.add_argument("--force", action="store_true", help="忽略有效 Cookie，强制重新登录")
    args = parser.parse_args()

    session = BiliSession()
    if args.check:
        status = session.check()
        if status.get("ok"):
            print(f"logged in: {status.get('uname')} mid={status.get('mid')}")
            return 0
        print(f"not logged in: {status.get('message')}")
        return 1

    result = BiliPasswordLogin(session).login(force=bool(args.force))
    print(
        f"{result.get('status')}: {result.get('uname')} mid={result.get('mid')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
