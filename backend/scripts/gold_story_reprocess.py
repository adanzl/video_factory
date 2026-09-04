"""金故事重跑 CLI：删库留 N 条 + Whisper 转写 + H2–H4 回写。

用法:
  cd backend
  conda run -n flask_env python -m scripts.gold_story_reprocess prune
  conda run -n flask_env python -m scripts.gold_story_reprocess run --ids 6,7,15,18,21,23
  conda run -n flask_env python -m scripts.gold_story_reprocess all
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
from app.services.gold_story.collect.pipeline import (
    overwrite_existing_stories,
)

KEEP_ACTIVE_IDS = (18, 23, 31, 34)
KEEP_ACTIVE_BVS = (
    "BV1sh411G7aX",
    "BV18vLh6yEvm",
    "BV1ND4y1X7Mm",
    "BV1ms411a7im",
)
KEEP_SIX_IDS = KEEP_ACTIVE_IDS
KEEP_SIX_BVS = KEEP_ACTIVE_BVS


def _cmd_prune(_: argparse.Namespace) -> int:
    app = create_app()
    with app.app_context():
        deleted = repo_gold_story.delete_stories_except(list(KEEP_SIX_IDS))
        rows = repo_gold_story.list_stories(limit=20)
    payload = {
        "keep_ids": list(KEEP_SIX_IDS),
        "keep_bvs": list(KEEP_SIX_BVS),
        "deleted": deleted,
        "remaining": len(rows),
        "items": [
            {"id": r.get("id"), "source_id": r.get("source_id"), "title": r.get("title")}
            for r in rows
        ],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    ids = [int(x.strip()) for x in str(args.ids).split(",") if x.strip()]
    if not ids:
        print("need --ids", file=sys.stderr)
        return 1
    app = create_app()
    with app.app_context():
        results = overwrite_existing_stories(
            ids,
            force_transcript=not args.skip_transcript,
        )
    print(json.dumps(results, ensure_ascii=False, indent=2))
    ok = sum(1 for r in results if r.get("action") == "ok")
    return 0 if ok else 1


def _cmd_all(_: argparse.Namespace) -> int:
    app = create_app()
    with app.app_context():
        deleted = repo_gold_story.delete_stories_except(list(KEEP_SIX_IDS))
        results = overwrite_existing_stories(
            list(KEEP_SIX_IDS),
            force_transcript=True,
        )
    payload = {"deleted": deleted, "results": results}
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    ok = sum(1 for r in results if r.get("action") == "ok")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="金故事重跑（真实逐字稿）")
    sub = parser.add_subparsers(dest="command", required=True)

    p_prune = sub.add_parser("prune", help=f"只保留 {len(KEEP_SIX_IDS)} 条")
    p_prune.set_defaults(func=_cmd_prune)

    p_run = sub.add_parser("run", help="对指定 id 重跑转写+结构化")
    p_run.add_argument("--ids", required=True, help="gold_story.id，逗号分隔")
    p_run.add_argument(
        "--skip-transcript",
        action="store_true",
        help="不跑 H0b（仅用已有 txt）",
    )
    p_run.set_defaults(func=_cmd_run)

    p_all = sub.add_parser("all", help="prune + 重跑保留的 6 条")
    p_all.set_defaults(func=_cmd_all)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
