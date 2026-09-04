"""金故事 structure 纠偏 CLI：对已入库稿跑 resolve（含 M2+C→M13+O 等）。

用法:
  cd backend
  conda run -n flask_env python -m scripts.gold_story_resolve_structure \\
    --ids 53 --dry-run
  conda run -n flask_env python -m scripts.gold_story_resolve_structure \\
    --ids 53
  conda run -n flask_env python -m scripts.gold_story_resolve_structure \\
    --all-active
  conda run -n flask_env python -m scripts.gold_story_resolve_structure \\
    --status active --mechanism M2 --structure-type C
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core import create_app
from app.repositories import repo_gold_story
from app.services.gold_story.gold_chat.type_bridge import (
    resolve_gold_chat_structure_row,
)


def _persist(row: dict[str, Any]) -> None:
    gid = int(row.get("id") or 0)
    mech = str(row.get("mechanism") or "").strip().upper()
    st = str(row.get("structure_type") or "").strip().upper()
    if gid <= 0 or not mech or not st:
        raise ValueError(f"invalid row for persist: id={gid} {mech}+{st}")
    repo_gold_story.update_mechanism_and_structure(
        gid,
        mechanism=mech,
        structure_type=st,
    )
    payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
    patch: dict[str, Any] = {}
    note = str(payload.get("structure_mapping_note") or "").strip()
    if note:
        patch["structure_mapping_note"] = note
    sc = payload.get("scene_contract")
    if isinstance(sc, dict):
        patch["scene_contract"] = sc
    if patch:
        repo_gold_story.patch_story_payload(gid, patch)


def resolve_one(row: dict[str, Any], *, dry_run: bool) -> dict[str, Any]:
    before_m = str(row.get("mechanism") or "").strip().upper()
    before_s = str(row.get("structure_type") or "").strip().upper()
    fixed, notes = resolve_gold_chat_structure_row(row)
    after_m = str(fixed.get("mechanism") or "").strip().upper()
    after_s = str(fixed.get("structure_type") or "").strip().upper()
    out: dict[str, Any] = {
        "id": row.get("id"),
        "source_id": row.get("source_id"),
        "title": row.get("title"),
        "before": f"{before_m}+{before_s}",
        "after": f"{after_m}+{after_s}",
        "notes": notes,
        "changed": bool(notes),
        "dry_run": dry_run,
        "applied": False,
    }
    if not notes:
        return out
    if dry_run:
        return out
    _persist(fixed)
    out["applied"] = True
    return out


def _iter_rows(
    *,
    ids: list[int] | None,
    all_active: bool,
    status: str | None,
    mechanism: str | None,
    structure_type: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    if ids:
        rows: list[dict[str, Any]] = []
        for gid in ids:
            row = repo_gold_story.get_story(int(gid))
            if row:
                rows.append(row)
        return rows

    st = "active" if all_active else status
    page = max(1, min(int(limit), 200))
    offset = 0
    rows = []
    while True:
        batch = repo_gold_story.list_stories(
            status=st,
            mechanism=mechanism,
            structure_type=structure_type,
            exclude_archived=True,
            limit=page,
            offset=offset,
        )
        if not batch:
            break
        rows.extend(batch)
        if len(batch) < page:
            break
        offset += page
        if len(rows) >= limit:
            break
    return rows[:limit]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="金故事 structure 纠偏（已入库）")
    parser.add_argument(
        "--ids",
        help="gold_story.id，逗号分隔（优先于筛选）",
    )
    parser.add_argument(
        "--all-active",
        action="store_true",
        help="处理 status=active（分页拉齐）",
    )
    parser.add_argument("--status", default=None, help="按 status 筛选")
    parser.add_argument("--mechanism", default=None, help="按 mechanism 筛选")
    parser.add_argument(
        "--structure-type",
        default=None,
        help="按 structure_type 筛选",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=200,
        help="最多处理条数（默认 200）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只打印将改什么，不写库",
    )
    args = parser.parse_args(argv)

    ids: list[int] | None = None
    if args.ids:
        ids = [int(x.strip()) for x in str(args.ids).split(",") if x.strip()]
        if not ids:
            print("need valid --ids", file=sys.stderr)
            return 1
    elif not args.all_active and not args.status and not args.mechanism:
        print(
            "need --ids / --all-active / --status / --mechanism",
            file=sys.stderr,
        )
        return 1

    app = create_app()
    with app.app_context():
        rows = _iter_rows(
            ids=ids,
            all_active=bool(args.all_active),
            status=args.status,
            mechanism=args.mechanism,
            structure_type=args.structure_type,
            limit=int(args.limit),
        )
        results = [resolve_one(row, dry_run=bool(args.dry_run)) for row in rows]

    changed = sum(1 for r in results if r.get("changed"))
    applied = sum(1 for r in results if r.get("applied"))
    summary = {
        "total": len(results),
        "changed": changed,
        "applied": applied,
        "dry_run": bool(args.dry_run),
        "results": results,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
