"""gold_chat 批量流程（不经过 H0–H4 采集编排）。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import Config
from app.repositories import repo_gold_story
from app.services.daily_story.gold_story.gold_chat.convert import convert_gold_chat
from app.services.daily_story.gold_story.gold_chat.export import gold_chat_export_dir


def _already_exported(source_id: str, config: Config) -> bool:
    sid = str(source_id or "").strip()
    if not sid:
        return False
    json_path = gold_chat_export_dir(config) / f"{sid}.json"
    return json_path.is_file()


def run_gold_chat_batch(
    *,
    config: Config | None = None,
    max_items: int = 10,
    status: str = "active",
    source_ids: list[str] | None = None,
    gold_story_ids: list[int] | None = None,
    skip_existing: bool = True,
) -> dict[str, Any]:
    """从库内金故事批量转 gold_chat 并导出。"""
    from app.repositories.schema import apply_gold_story_schema
    from app.repositories import sql_exec as sql
    from app.repositories.db_obj import db

    conn = db.session.connection().connection.dbapi_connection
    apply_gold_story_schema(conn)
    sql.commit()

    cfg = config or Config()
    max_items = max(1, min(max_items, 50))
    rows: list[dict[str, Any]] = []

    if gold_story_ids:
        for gid in gold_story_ids[:max_items]:
            try:
                rows.append(repo_gold_story.get_story(int(gid)))
            except KeyError:
                pass
    elif source_ids:
        for sid in source_ids[:max_items]:
            row = repo_gold_story.get_by_source_id(source_id=str(sid).strip())
            if row:
                rows.append(row)
    else:
        rows = repo_gold_story.list_stories(
            status=status or None,
            limit=max_items,
        )

    results: list[dict[str, Any]] = []
    ok_count = 0
    skip_count = 0
    fail_count = 0

    for row in rows:
        sid = str(row.get("source_id") or "").strip()
        base = {
            "source_id": sid,
            "gold_story_id": row.get("id"),
            "title": row.get("title"),
            "status": row.get("status"),
        }
        if skip_existing and _already_exported(sid, cfg):
            skip_count += 1
            results.append({**base, "action": "skip", "reason": "already_exported"})
            continue
        try:
            outcome = convert_gold_chat(row, config=cfg)
            ok_count += 1
            results.append({**base, "action": "ok", **outcome})
        except Exception as exc:
            fail_count += 1
            results.append({**base, "action": "error", "error": str(exc)})

    report = {
        "workflow": "gold_chat",
        "requested": max_items,
        "selected": len(rows),
        "ok": ok_count,
        "skipped": skip_count,
        "failed": fail_count,
        "export_dir": str(gold_chat_export_dir(cfg)),
        "results": results,
    }
    _write_batch_report(report, cfg)
    return report


def _write_batch_report(report: dict[str, Any], config: Config) -> Path:
    out_dir = gold_chat_export_dir(config)
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    json_path = out_dir / f"_batch_{ts}.json"
    md_path = out_dir / f"_batch_{ts}.md"

    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    md_lines = [
        "# gold_chat 批量报告",
        "",
        f"- workflow: {report.get('workflow')} @ {ts}",
        f"- 选取: {report.get('selected')} / 请求 {report.get('requested')}",
        f"- 成功: {report.get('ok')} / 跳过: {report.get('skipped')} / "
        f"失败: {report.get('failed')}",
        f"- 目录: {report.get('export_dir')}",
        "",
        "## 明细",
        "",
    ]
    for item in report.get("results") or []:
        action = item.get("action")
        sid = item.get("source_id")
        title = item.get("title") or ""
        if action == "ok":
            md_lines.append(
                f"- ✅ `{sid}` {title} — "
                f"{item.get('chat_lines')}句 / {item.get('chat_chars')}字"
            )
        elif action == "skip":
            md_lines.append(f"- ⏭ `{sid}` {title} — {item.get('reason')}")
        else:
            md_lines.append(
                f"- ❌ `{sid}` {title} — {item.get('error') or item.get('reason')}"
            )
    md_path.write_text("\n".join(md_lines), encoding="utf-8")
    report["batch_report"] = {"json": str(json_path), "markdown": str(md_path)}
    return json_path
