"""gold_chat 独立批量 CLI（与 H0–H4 采集流水线分离）。

用法:
  cd backend
  conda run -n flask_env python -m scripts.gold_chat_batch run --max 10
  conda run -n flask_env python -m scripts.gold_chat_batch run \\
    --source-id BV1QSQ7BYEhH --force
  conda run -n flask_env python -m scripts.gold_chat_batch polish \\
    --source-id BV1ms411a7im
  conda run -n flask_env python -m scripts.gold_chat_batch list
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import Config
from app.core import create_app
from app.repositories import repo_gold_story
from app.services.daily_story.gold_story.gold_chat.batch import run_gold_chat_batch
from app.services.daily_story.gold_story.gold_chat.export import gold_chat_export_dir
from app.services.daily_story.gold_story.gold_chat.polish import polish_gold_chat_export


def _cmd_run(args: argparse.Namespace) -> int:
    cfg = Config()
    app = create_app()
    with app.app_context():
        source_ids = None
        if args.source_id:
            source_ids = [s.strip() for s in args.source_id.split(",") if s.strip()]
        gold_ids = None
        if args.id:
            gold_ids = [int(x.strip()) for x in str(args.id).split(",") if x.strip()]

        report = run_gold_chat_batch(
            config=cfg,
            max_items=args.max,
            status=args.status or "active",
            source_ids=source_ids,
            gold_story_ids=gold_ids,
            skip_existing=not args.force,
        )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report.get("ok"):
        return 0
    if not report.get("selected"):
        return 1
    return 1


def _cmd_polish(args: argparse.Namespace) -> int:
    cfg = Config()
    app = create_app()
    sid = str(args.source_id or "").strip()
    if not sid and args.id:
        with app.app_context():
            row = repo_gold_story.get_story(int(args.id))
            sid = str(row.get("source_id") or "")
    if not sid:
        print("need --source-id or --id", file=sys.stderr)
        return 1
    with app.app_context():
        try:
            report = polish_gold_chat_export(sid, config=cfg)
        except (FileNotFoundError, ValueError) as exc:
            print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
            return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("ok") else 1


def _cmd_list(args: argparse.Namespace) -> int:
    cfg = Config()
    out_dir = gold_chat_export_dir(cfg)
    app = create_app()
    with app.app_context():
        rows = repo_gold_story.list_stories(
            status=args.status or None,
            limit=max(1, args.limit),
        )
    exports = []
    if out_dir.is_dir():
        for p in sorted(out_dir.glob("BV*.json")):
            exports.append(p.name)
    payload = {
        "export_dir": str(out_dir),
        "exported_json_count": len(exports),
        "exported_samples": exports[:20],
        "db_stories": [
            {
                "id": r.get("id"),
                "source_id": r.get("source_id"),
                "title": r.get("title"),
                "status": r.get("status"),
                "has_gold_chat": (out_dir / f"{r.get('source_id')}.json").is_file(),
            }
            for r in rows
        ],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    cfg = Config()
    parser = argparse.ArgumentParser(
        description="gold_chat：金故事转日常对白（独立流程）",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="批量转 gold_chat 并导出")
    p_run.add_argument(
        "--max",
        type=int,
        default=cfg.gold_story_cron_max,
        help="最多处理条数（默认 GOLD_STORY_CRON_MAX）",
    )
    p_run.add_argument(
        "--status",
        default="active",
        help="库内筛选 status（默认 active）",
    )
    p_run.add_argument(
        "--source-id",
        help="指定 BV，逗号分隔",
    )
    p_run.add_argument(
        "--id",
        help="指定 gold_story.id，逗号分隔",
    )
    p_run.add_argument(
        "--force",
        action="store_true",
        help="已导出也重跑",
    )
    p_run.set_defaults(func=_cmd_run)

    p_polish = sub.add_parser("polish", help="童语化润色已导出 gold_chat")
    p_polish.add_argument("--source-id", help="指定 BV")
    p_polish.add_argument("--id", help="指定 gold_story.id")
    p_polish.set_defaults(func=_cmd_polish)

    p_list = sub.add_parser("list", help="库内条目 vs 已导出对照")
    p_list.add_argument("--status", default="active")
    p_list.add_argument("--limit", type=int, default=20)
    p_list.set_defaults(func=_cmd_list)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
