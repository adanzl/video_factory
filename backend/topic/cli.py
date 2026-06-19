from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import get_settings
from app.core.log_config import setup_logging

setup_logging(
    log_dir=get_settings().log_dir,
    retention_days=get_settings().log_retention_days,
)

from app.services.llm.llm_mgr import llm_mgr


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="topic", description="科普视频选题生成")
    parser.add_argument("--theme", "-t", required=True, help="主题方向，如「高考志愿填报」")
    parser.add_argument("--count", "-n", type=int, default=10, help="生成数量（默认 10，最大 20）")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    parser.add_argument("--verbose", "-v", action="store_true", help="显示赛道、模板与钩子")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    count = max(1, min(args.count, 20))
    try:
        topics = llm_mgr.generate_topics(args.theme, count=count)
    except Exception as exc:
        print(f"选题生成失败: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps({"theme": args.theme, "topics": topics}, ensure_ascii=False, indent=2))
        return 0

    print(f"主题：{args.theme}\n")
    for i, item in enumerate(topics, start=1):
        print(f"{i}. {item['title']}")
        if args.verbose:
            hook = item.get("hook") or ""
            print(f"   赛道：{item.get('track', '')} | 模板：{item.get('template', '')}")
            if hook:
                print(f"   钩子：{hook}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
