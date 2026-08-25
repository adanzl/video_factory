"""探测 / 清理 / 回写金故事 funny_signal。"""

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
from app.services.daily_story.gold_story.collect import (
    _bili_http,
    fetch_top_replies,
    fetch_video_meta,
)
from app.services.daily_story.gold_story.funny_signal import (
    compute_audience_funny_metrics,
    metrics_to_payload,
    passes_funny_gate_from_payload,
)

KEEP_GOOD_IDS = (18, 23, 31, 34)
KEEP_GOOD_BVS = (
    "BV1sh411G7aX",
    "BV18vLh6yEvm",
    "BV1ND4y1X7Mm",
    "BV1ms411a7im",
)


def _probe_ids(ids: tuple[int, ...], cfg: Config) -> list[dict]:
    rows: list[dict] = []
    http = _bili_http(cfg)
    for gid in ids:
        row = repo_gold_story.get_story(int(gid))
        sid = str(row.get("source_id") or "")
        try:
            meta = fetch_video_meta(sid, config=cfg, session=http)
            replies = fetch_top_replies(
                int(meta.get("aid") or 0),
                config=cfg,
                session=http,
                limit=8,
            )
            metrics = compute_audience_funny_metrics(
                source_id=sid,
                cid=int(meta.get("cid") or 0),
                view_count=int(meta.get("view_count") or 0),
                reply_count=int(meta.get("reply_count") or 0),
                replies=replies,
                session=http,
            )
            payload = metrics_to_payload(metrics)
            l1_ok, _ = passes_funny_gate_from_payload(payload, level="l1")
            l2_ok, l2_reason = passes_funny_gate_from_payload(payload, level="l2")
            rows.append(
                {
                    "id": gid,
                    "source_id": sid,
                    "title": str(row.get("title") or "")[:40],
                    "db_status": row.get("status"),
                    **payload,
                    "L1_pass": l1_ok,
                    "L2_pass": l2_ok,
                    "L2_reason": l2_reason if not l2_ok else "",
                }
            )
        except Exception as exc:
            rows.append({"id": gid, "source_id": sid, "error": str(exc)})
    return rows


def _cmd_probe(args: argparse.Namespace) -> int:
    cfg = Config()
    app = create_app()
    ids = tuple(int(x) for x in args.ids.split(",")) if args.ids else KEEP_GOOD_IDS
    with app.app_context():
        rows = _probe_ids(ids, cfg)
    print(json.dumps(rows, ensure_ascii=False, indent=2))
    return 0


def _cmd_rescore(_: argparse.Namespace) -> int:
    """按已存弹幕/评论分量重算 funny_signal，并重套 L2。"""
    app = create_app()
    with app.app_context():
        rows = repo_gold_story.rescore_all_funny()
    flipped = [
        row
        for row in rows
        if not row.get("skipped") and row.get("old_status") != row.get("status")
    ]
    print(
        json.dumps(
            {
                "total": len(rows),
                "scored": sum(1 for row in rows if not row.get("skipped")),
                "skipped": sum(1 for row in rows if row.get("skipped")),
                "flipped": flipped,
                "rows": rows,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _cmd_sync(_: argparse.Namespace) -> int:
    """回写所有 active 条目的 funny_signal。"""
    cfg = Config()
    app = create_app()
    with app.app_context():
        rows = repo_gold_story.list_stories(status="active", limit=50)
        patched: list[dict] = []
        for row in rows:
            gid = int(row["id"])
            probed = _probe_ids((gid,), cfg)
            if not probed or probed[0].get("funny_signal") is None:
                continue
            patch = {
                k: probed[0][k]
                for k in (
                    "danmaku_total",
                    "danmaku_laugh_score",
                    "danmaku_laugh_ratio",
                    "comment_laugh_ratio",
                    "view_reply_ratio_norm",
                    "funny_signal",
                    "cute_not_funny",
                    "danmaku_fetch_ok",
                )
                if k in probed[0]
            }
            repo_gold_story.patch_story_payload(gid, patch)
            patched.append({"id": gid, "source_id": row.get("source_id"), **patch})
    print(json.dumps({"patched": patched}, ensure_ascii=False, indent=2))
    return 0


def _cmd_cleanup_exports(_: argparse.Namespace) -> int:
    """删除 stories/ 下不在 DB active 的导出文件。"""
    cfg = Config()
    app = create_app()
    with app.app_context():
        rows = repo_gold_story.list_stories(status="active", limit=100)
        keep = {str(r.get("source_id") or "") for r in rows}
        story_dir = cfg.gold_story_transcript_dir.parent / "stories"
        removed: list[str] = []
        if story_dir.is_dir():
            for path in story_dir.iterdir():
                if path.suffix not in {".json", ".md"}:
                    continue
                sid = path.stem
                if sid not in keep:
                    path.unlink(missing_ok=True)
                    removed.append(path.name)
    print(json.dumps({"kept": sorted(keep), "removed": removed}, ensure_ascii=False, indent=2))
    return 0


def _cmd_prune(_: argparse.Namespace) -> int:
    """删 rejected + 不过 L2 弹幕好笑的 active，保留 KEEP_GOOD 并回写 funny。"""
    cfg = Config()
    app = create_app()
    keep_ids = list(KEEP_GOOD_IDS)
    with app.app_context():
        deleted_rejected = repo_gold_story.delete_stories_by_status("rejected")
        deleted_other = repo_gold_story.delete_stories_except(keep_ids)
        patched: list[dict] = []
        for gid in keep_ids:
            rows = _probe_ids((gid,), cfg)
            if rows and rows[0].get("funny_signal") is not None:
                patch = {
                    k: rows[0][k]
                    for k in (
                        "danmaku_total",
                        "danmaku_laugh_score",
                        "danmaku_laugh_ratio",
                        "comment_laugh_ratio",
                        "view_reply_ratio_norm",
                        "funny_signal",
                        "cute_not_funny",
                        "danmaku_fetch_ok",
                    )
                    if k in rows[0]
                }
                repo_gold_story.patch_story_payload(gid, patch)
                patched.append({"id": gid, **patch})
    out = {
        "deleted_rejected": deleted_rejected,
        "deleted_other": deleted_other,
        "kept_ids": keep_ids,
        "patched": patched,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="金故事 funny_signal 工具")
    sub = parser.add_subparsers(dest="command", required=True)

    p_probe = sub.add_parser("probe", help="探测 funny_signal（不写库）")
    p_probe.add_argument("--ids", help="逗号分隔 gold_story.id")
    p_probe.set_defaults(func=_cmd_probe)

    p_sync = sub.add_parser("sync", help="回写 active 条目的 funny_signal")
    p_sync.set_defaults(func=_cmd_sync)

    p_rescore = sub.add_parser("rescore", help="全库按当前权重重评 funny_signal")
    p_rescore.set_defaults(func=_cmd_rescore)

    p_clean = sub.add_parser("cleanup-exports", help="删 stories/ 孤儿导出")
    p_clean.set_defaults(func=_cmd_cleanup_exports)

    p_prune = sub.add_parser("prune", help="清 rejected + 只保留 KEEP_GOOD 并回写 funny")
    p_prune.set_defaults(func=_cmd_prune)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))