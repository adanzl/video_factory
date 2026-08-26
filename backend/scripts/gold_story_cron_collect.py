"""金故事 M1 采集 CLI（H0–H4）。

用法:
  cd backend
  conda run -n flask_env python -m scripts.gold_story_cron_collect collect --max 5
  conda run -n flask_env python -m scripts.gold_story_cron_collect run --max 1
  conda run -n flask_env python -m scripts.gold_story_cron_collect run --max 1 --dry-run
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
from app.services.daily_story.gold_story.collect import (
    collect_candidates,
    write_candidate_list,
)
from app.services.daily_story.gold_story.collect.pipeline import run_collect_pipeline


def _cmd_collect(args: argparse.Namespace) -> int:
    cfg = Config()
    app = create_app()
    with app.app_context():
        rows = collect_candidates(
            config=cfg,
            max_candidates=args.max,
            keywords=_keywords(args),
        )
        write_candidate_list(rows, cfg.gold_story_candidates_file)
    payload = {
        "count": len(rows),
        "file": str(cfg.gold_story_candidates_file),
        "items": [
            {
                "source_id": r.source_id,
                "title": r.title,
                "view": r.view_count,
                "reply": r.reply_count,
                "keyword": r.keyword,
            }
            for r in rows
        ],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if rows else 1


def _cmd_run(args: argparse.Namespace) -> int:
    app = create_app()
    with app.app_context():
        report = run_collect_pipeline(
            max_candidates=args.max,
            keywords=_keywords(args),
            skip_transcript=args.skip_transcript,
            dry_run=args.dry_run,
            write_list=True,
        )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.dry_run:
        return 0 if report.get("candidates") else 1
    if report.get("inserted"):
        return 0
    # 有候选但全 skip/reject 仍算链路跑通
    return 0 if report.get("candidates") else 1


def _keywords(args: argparse.Namespace) -> list[str] | None:
    raw = str(args.keyword or "").strip()
    if raw:
        return [raw]
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="金故事 M1 采集（H0–H4）")
    sub = parser.add_subparsers(dest="command", required=True)

    for name in ("collect", "run"):
        p = sub.add_parser(name, help="collect=仅 H0/H1；run=H0–H4 全流程")
        p.add_argument("--max", type=int, default=5, help="最多处理 BV 数")
        p.add_argument(
            "--keyword",
            help="只搜一个词（默认轮换 DEFAULT_SEARCH_KEYWORDS）",
        )
        if name == "run":
            p.add_argument(
                "--dry-run",
                action="store_true",
                help="只采集+转写统计，不调 LLM、不入库",
            )
            p.add_argument(
                "--skip-transcript",
                action="store_true",
                help="不跑 H0b，仅用简介/热评走 H2",
            )
        p.set_defaults(func=_cmd_collect if name == "collect" else _cmd_run)

    args = parser.parse_args(argv)
    if args.command == "collect":
        return int(_cmd_collect(args))
    return int(_cmd_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
