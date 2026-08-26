"""H5–H6：金故事检索与注入块预览 CLI。

用法:
  cd backend
  conda run -n flask_env python -m scripts.gold_story_block \\
    --theme 抢遥控器 --story-type C
  conda run -n flask_env python -m scripts.gold_story_block --list
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core import create_app
from app.repositories import repo_gold_story
from app.services.daily_story.gold_story.story_block import (
    build_gold_story_block,
    pick_for_injection,
)
from app.services.daily_story.prompts import build_gold_story_block as prompts_block


def _print_row(row: dict) -> None:
    print(f"id={row.get('id')} mechanism={row.get('mechanism')} "
          f"structure={row.get('structure_type')} score={row.get('auto_score')}")
    print(f"title={row.get('title')}")
    print(f"conflict_core={row.get('conflict_core')}")
    print("--- inject block ---")
    print(build_gold_story_block(row))
    print("--- prompts re-export ---")
    print(prompts_block(row))


def main() -> int:
    parser = argparse.ArgumentParser(description="金故事 H5 检索 / H6 注入块预览")
    parser.add_argument("--theme", default="", help="任务主题")
    parser.add_argument("--story-type", default="", help="A–E 结构类型")
    parser.add_argument("--theme-family", default="", help="可选 theme_family")
    parser.add_argument("--limit", type=int, default=3, help="list/pick 条数")
    parser.add_argument(
        "--list",
        action="store_true",
        help="列出库内 active/promoted",
    )
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        if args.list:
            rows = repo_gold_story.list_stories(limit=max(1, args.limit))
            if not rows:
                print("库内暂无 gold_story 行")
                return 0
            for row in rows:
                _print_row(row)
                print("=" * 40)
            return 0

        if not args.theme or not args.story_type:
            parser.error("需 --theme 与 --story-type，或 --list")

        row = pick_for_injection(
            theme=args.theme,
            story_type=args.story_type,
            theme_family=args.theme_family or None,
        )
        if not row:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "theme": args.theme,
                        "story_type": args.story_type,
                        "message": "无匹配金故事",
                    },
                    ensure_ascii=False,
                )
            )
            return 1

        _print_row(row)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
