"""B 站登录检查（账号密码已移除，请用前端扫码）。

用法（backend 目录）:

  python -m scripts.bili_login --check
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.publish.bilibili.session import BiliSession


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="B 站 Cookie 登录状态检查")
    parser.add_argument("--check", action="store_true", help="校验已有 Cookie")
    parser.add_argument("--force", action="store_true", help="已废弃（账号密码登录已移除）")
    args = parser.parse_args()

    session = BiliSession()
    if args.check or not args.force:
        status = session.check()
        if status.get("ok"):
            print(f"logged in: {status.get('uname')} mid={status.get('mid')}")
            return 0
        print(f"not logged in: {status.get('message')}")
        if args.force:
            print("账号密码登录已移除，请在前端投稿页扫码登录", file=sys.stderr)
            return 2
        return 1

    print("账号密码登录已移除，请在前端投稿页扫码登录", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
