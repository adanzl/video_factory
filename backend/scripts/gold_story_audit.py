"""金故事 H4a 机审 CLI。

用法:
  cd backend
  conda run -n flask_env python -m scripts.gold_story_audit list --status rejected
  conda run -n flask_env python -m scripts.gold_story_audit rerun --id 27
  conda run -n flask_env python -m scripts.gold_story_audit rerun --all-active
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
from app.services.daily_story.gold_story.export_story import export_story_files
from app.services.daily_story.gold_story.export_story import (
    _load_repaired_transcript_text,
    _load_transcript_text,
)
from app.services.daily_story.gold_story.review import audit_story


def _load_transcript_for_row(row: dict, cfg: Config) -> str:
    sid = str(row.get("source_id") or "")
    repaired = _load_repaired_transcript_text(source_id=sid, row=row, config=cfg)
    if repaired:
        return repaired
    return _load_transcript_text(source_id=sid, row=row, config=cfg)


def _rerun_one(row: dict, cfg: Config) -> dict:
    payload = row.get("payload") or {}
    h3 = {
        "title": row.get("title"),
        "beat": payload.get("beat") or [],
        "mechanism": row.get("mechanism"),
        "structure_type": row.get("structure_type"),
        "conflict_core": row.get("conflict_core"),
    }
    h3b = {
        "dialogue_seed": payload.get("dialogue_seed") or [],
        "speaker_map_note": payload.get("speaker_map_note") or "",
    }
    h3a = payload.get("scene_contract") if isinstance(payload.get("scene_contract"), dict) else {}
    story_raw = str(row.get("story_raw") or payload.get("story_raw") or "")
    transcript = _load_transcript_for_row(row, cfg)
    result = audit_story(
        title=str(row.get("title") or ""),
        video_title=str(payload.get("search_keyword") or row.get("title") or ""),
        story_raw=story_raw,
        conflict_core=str(row.get("conflict_core") or ""),
        transcript=transcript,
        h3=h3,
        h3a=h3a,
        h3b=h3b,
        config=cfg,
    )
    status = "active" if result.get("pass") else "rejected"
    repo_gold_story.update_story_status(int(row["id"]), status=status, audit=result)
    row = repo_gold_story.get_story(int(row["id"]))
    paths = export_story_files(
        source_id=str(row.get("source_id") or ""),
        row=row,
        config=cfg,
    )
    return {
        "id": row.get("id"),
        "source_id": row.get("source_id"),
        "status": status,
        "audit_pass": result.get("pass"),
        "reasons": result.get("reject_reasons") or [],
        "export": paths,
    }


def _cmd_list(args: argparse.Namespace) -> int:
    cfg = Config()
    app = create_app()
    with app.app_context():
        rows = repo_gold_story.list_stories(status=args.status, limit=args.limit)
    print(json.dumps(rows, ensure_ascii=False, indent=2, default=str))
    return 0


def _cmd_rerun(args: argparse.Namespace) -> int:
    cfg = Config()
    app = create_app()
    with app.app_context():
        if args.all_active:
            rows = repo_gold_story.list_stories(status="active", limit=args.limit)
        elif args.id:
            rows = [repo_gold_story.get_story(int(args.id))]
        else:
            print("need --id or --all-active", file=sys.stderr)
            return 1
        results = [_rerun_one(row, cfg) for row in rows]
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="金故事 H4a 机审")
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="按 status 列出")
    p_list.add_argument("--status", default="rejected")
    p_list.add_argument("--limit", type=int, default=50)
    p_list.set_defaults(func=_cmd_list)

    p_rerun = sub.add_parser("rerun", help="对已有条目重跑机审")
    p_rerun.add_argument("--id", type=int)
    p_rerun.add_argument("--all-active", action="store_true")
    p_rerun.add_argument("--limit", type=int, default=100)
    p_rerun.set_defaults(func=_cmd_rerun)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
