"""gold_chat 批量流程（不经过 H0–H4 采集编排）。"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

from app.config import Config
from app.repositories import repo_gold_story
from app.services.gold_story.gold_chat.convert import convert_gold_chat
from app.services.gold_story.gold_chat.export import gold_chat_export_dir, load_gold_chat_for_row
from app.services.gold_story.gold_chat.status import record_gold_chat_failure


def _already_exported(row: dict[str, Any], config: Config) -> bool:
    sid = str(row.get("source_id") or "").strip()
    if not sid:
        return False
    payload = row.get("payload")
    backfilled = bool(
        isinstance(payload, dict)
        and payload.get("gold_chat_exported_at")
        and payload.get("gold_chat_json")
    )
    return backfilled and load_gold_chat_for_row(row, config=config) is not None


def run_gold_chat_batch(
    *,
    config: Config | None = None,
    max_items: int = 10,
    status: str = "active",
    source_ids: list[str] | None = None,
    gold_story_ids: list[int] | None = None,
    skip_existing: bool = True,
    task_id: str | None = None,
    task_owner_id: int | None = None,
) -> dict[str, Any]:
    """从库内金故事批量转 gold_chat 并导出。"""
    from app.repositories.schema import apply_gold_story_schema
    from app.repositories import sql_exec as sql
    from app.repositories.db_obj import db

    conn = db.session.connection().connection.dbapi_connection
    apply_gold_story_schema(conn)  # type: ignore[union-attr]
    sql.commit()

    cfg = config or Config()
    max_items = max(1, min(max_items, 50))
    rows: list[dict[str, Any]] = []

    if gold_story_ids:
        for gid in list(dict.fromkeys(gold_story_ids))[:max_items]:
            try:
                rows.append(repo_gold_story.get_story(int(gid)))
            except KeyError:
                rows.append({"id": int(gid), "source_id": ""})
    elif source_ids:
        for sid in list(dict.fromkeys(source_ids))[:max_items]:
            row = repo_gold_story.get_by_source_id(source_id=str(sid).strip())
            rows.append(row or {"id": 0, "source_id": str(sid).strip()})
    else:
        rows = repo_gold_story.list_stories(
            status=status or None,
            limit=max_items,
        )

    results: list[dict[str, Any]] = []
    ok_count = 0
    skip_count = 0
    fail_count = 0

    def _task_current() -> bool:
        if task_id is None:
            return True
        try:
            owner = repo_gold_story.get_story(int(task_owner_id or 0))
        except KeyError:
            return False
        task = (owner.get("payload") or {}).get("gold_chat_task") or {}
        return (task.get("task_id") == task_id and task.get("status") == "running"
                and float(task.get("expires_at") or 0) > time.time())

    seen: set[tuple[int, str]] = set()
    for selected in rows:
        gid = int(selected.get("id") or 0)
        sid = str(selected.get("source_id") or "").strip()
        key = (gid, "" if gid else sid)
        if key in seen:
            continue
        seen.add(key)
        base = {"source_id": sid, "gold_story_id": gid, "title": selected.get("title"),
                "status": selected.get("status")}
        try:
            row = repo_gold_story.get_story(gid)
        except KeyError:
            fail_count += 1
            results.append({**base, "action": "error", "error": "金故事不存在或已删除"})
            continue
        sid = str(row.get("source_id") or "").strip()
        base.update(source_id=sid, title=row.get("title"), status=row.get("status"))
        if not _task_current():
            fail_count += 1
            results.append({**base, "action": "error", "error": "批次任务已结束或被替换，已停止转换"})
            continue
        if row.get("status") == "archived" and selected.get("status") != "archived":
            skip_count += 1
            results.append({**base, "action": "skip", "reason": "archived_during_batch"})
            continue
        if skip_existing and _already_exported(row, cfg):
            skip_count += 1
            results.append({**base, "action": "skip", "reason": "already_exported"})
            logger.info("[GOLD_CHAT] batch skip source_id=%s reason=already_exported", sid)
            continue
        try:
            if task_id is not None:
                row = {**row, "_gold_chat_task_id": task_id, "_gold_chat_task_owner_id": task_owner_id}
            outcome = convert_gold_chat(row, config=cfg)
            ok_count += 1
            logger.info(
                "[GOLD_CHAT] batch ok source_id=%s lines=%s chars=%s score=%s",
                sid,
                outcome.get("chat_lines"),
                outcome.get("chat_chars"),
                outcome.get("structure_score"),
            )
            results.append({**base, "action": "ok", **outcome})
        except Exception as exc:
            fail_count += 1
            if gid > 0 and _task_current():
                try:
                    record_gold_chat_failure(gid, exc, source_id=sid, stage="batch")
                except Exception as record_exc:
                    logger.warning("[GOLD_CHAT] batch error persistence failed id=%s: %s", gid, record_exc)
            if not isinstance(exc, ValueError):
                logger.exception("[GOLD_CHAT] batch failed source_id=%s: %s", sid, exc)
            results.append({**base, "action": "error", "error": str(exc)})

    logger.info(
        "[GOLD_CHAT] batch done selected=%d ok=%d skipped=%d failed=%d",
        len(results), ok_count, skip_count, fail_count,
    )

    report = {
        "workflow": "gold_chat",
        "requested": max_items,
        "selected": len(results),
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
