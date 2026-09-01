"""gold_chat JSON/MD 导出与回读。"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

from app.config import Config
from app.repositories import repo_gold_story
from app.services.daily_story.gold_story.gold_chat.status import clear_gold_chat_failure
from app.services.daily_story.gold_story.collect import fetch_video_meta
from app.services.daily_story.gold_story.export_story import export_story_files
from app.services.daily_story.prompts import dialogue_total_chars

logger = logging.getLogger(__name__)


def gold_chat_export_dir(config: Config | None = None) -> Path:
    cfg = config or Config()
    return cfg.gold_story_transcript_dir.parent / "gold_chat"


def _chat_md_lines(dialogue: list[Any]) -> list[str]:
    lines: list[str] = []
    for item in dialogue or []:
        if not isinstance(item, dict):
            continue
        sp = str(item.get("speaker") or "").strip()
        text = str(item.get("line") or "").strip()
        if sp and text:
            lines.append(f"{sp}：{text}")
    return lines


def _bili_meta_patch(source_id: str, *, config: Config) -> dict[str, Any]:
    sid = str(source_id or "").strip()
    if not sid.startswith("BV"):
        return {}
    try:
        meta = fetch_video_meta(sid, config=config)
    except Exception as exc:
        logger.warning("gold_chat bili meta failed bvid=%s: %s", sid, exc)
        return {}
    url = str(meta.get("url") or "").strip() or f"https://www.bilibili.com/video/{sid}"
    patch: dict[str, Any] = {
        "bili_title": meta.get("title"),
        "bili_url": url,
        "bili_view_count": meta.get("view_count"),
        "bili_reply_count": meta.get("reply_count"),
    }
    return {k: v for k, v in patch.items() if v not in (None, "")}


def _backfill_gold_story_after_export(
    row: dict[str, Any],
    *,
    chat: dict[str, Any],
    paths: dict[str, str],
    config: Config,
) -> None:
    """gold_chat 导出后回写库内摘要与 B 站元数据。"""
    gid = int(row.get("id") or 0)
    sid = str(row.get("source_id") or "").strip()
    if gid <= 0 or not sid:
        return

    payload_patch = {
        **_bili_meta_patch(sid, config=config),
        "gold_chat_exported_at": datetime.now(timezone.utc).isoformat(),
        "gold_chat_scene_title": chat.get("scene_title"),
        "gold_chat_lines": len(chat.get("dialogue") or []),
        "gold_chat_chars": dialogue_total_chars(chat),
        "gold_chat_json": paths.get("json"),
        "gold_chat_md": paths.get("markdown"),
    }
    quality = chat.get("quality") if isinstance(chat.get("quality"), dict) else None
    if quality:
        from app.services.daily_story.quality import structure_score_of

        payload_patch["gold_chat_structure_score"] = structure_score_of(quality)
        payload_patch["gold_chat_quality_summary"] = quality.get("summary")
    repo_gold_story.patch_story_payload(gid, payload_patch)
    clear_gold_chat_failure(gid, source_id=sid)

    bili_url = payload_patch.get("bili_url")
    if isinstance(bili_url, str) and bili_url.strip():
        repo_gold_story.update_story_source_fields(gid, url=bili_url.strip())

    try:
        fresh = repo_gold_story.get_story(gid)
        export_story_files(source_id=sid, row=fresh, config=config)
    except Exception as exc:
        logger.warning("gold_chat story export failed id=%s: %s", gid, exc)


def export_gold_chat_files(
    *,
    source_id: str,
    row: dict[str, Any],
    chat: dict[str, Any],
    config: Config | None = None,
) -> dict[str, str]:
    """导出 JSON + 可读 MD 到 data/gold_story/gold_chat/。"""
    sid = str(source_id or row.get("source_id") or "").strip()
    out_dir = gold_chat_export_dir(config)
    out_dir.mkdir(parents=True, exist_ok=True)

    payload = cast(dict[str, Any], row.get("payload") or {})
    export = {
        "gold_story_id": row.get("id"),
        "source_id": sid,
        "url": row.get("url"),
        "title": row.get("title"),
        "mechanism": row.get("mechanism"),
        "structure_type": row.get("structure_type"),
        "status": row.get("status"),
        "conflict_core": chat.get("conflict_core") or row.get("conflict_core"),
        "chat_chars": dialogue_total_chars(chat),
        "chat_lines": len(chat.get("dialogue") or []),
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "daily_story": chat,
        "gold_meta": {
            "source_type": payload.get("source_type"),
            "scene_contract": payload.get("scene_contract"),
            "beat": payload.get("beat"),
            "dialogue_seed": payload.get("dialogue_seed"),
            "banned_literals": payload.get("banned_literals"),
            "closing_intent": payload.get("closing_intent"),
        },
    }

    json_path = out_dir / f"{sid}.json"
    md_path = out_dir / f"{sid}.md"
    json_path.write_text(
        json.dumps(export, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    md_lines = [
        f"# {chat.get('scene_title') or row.get('title') or sid}",
        "",
        f"- BV: {sid}",
        f"- URL: {row.get('url') or ''}",
        f"- 金故事 status: {row.get('status') or ''}",
        f"- 机制: {row.get('mechanism')} / 结构: {row.get('structure_type')}",
        f"- 对白: {export['chat_lines']} 句 / {export['chat_chars']} 字",
        "",
        "## 元数据",
        f"- setting: {chat.get('setting') or ''}",
        f"- key: {chat.get('key') or ''}",
        f"- conflict_core: {chat.get('conflict_core') or ''}",
        f"- punchline_explain: {chat.get('punchline_explain') or ''}",
        "",
        "## 对白",
        "",
    ]
    md_lines.extend(_chat_md_lines(chat.get("dialogue") or []))
    md_path.write_text("\n".join(md_lines), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(md_path)}


def load_gold_chat(
    source_id: str,
    *,
    config: Config | None = None,
) -> dict[str, Any] | None:
    """读取已导出的 gold_chat JSON；不存在则 None。"""
    sid = str(source_id or "").strip()
    if not sid:
        return None
    json_path = gold_chat_export_dir(config) / f"{sid}.json"
    if not json_path.is_file():
        return None
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def load_gold_chat_for_row(
    row: dict[str, Any],
    *,
    config: Config | None = None,
) -> dict[str, Any] | None:
    """读取金故事行对应的 gold_chat 导出（标准路径 + payload 记录的备用路径）。"""
    sid = str(row.get("source_id") or "").strip()
    if not sid:
        return None
    export = load_gold_chat(sid, config=config)
    if export is not None:
        return export
    payload = cast(dict[str, Any], row.get("payload") or {})
    alt_json = str(payload.get("gold_chat_json") or "").strip()
    if not alt_json:
        return None
    alt_path = Path(alt_json)
    if not alt_path.is_file():
        return None
    try:
        raw = json.loads(alt_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return raw if isinstance(raw, dict) else None



def _summary_from_payload(payload: dict[str, Any]) -> dict[str, Any] | None:
    if not payload.get("gold_chat_exported_at"):
        return None
    return {
        "has_gold_chat": True,
        "chat_chars": payload.get("gold_chat_chars"),
        "chat_lines": payload.get("gold_chat_lines"),
        "scene_title": payload.get("gold_chat_scene_title"),
        "exported_at": payload.get("gold_chat_exported_at"),
        "bili_title": payload.get("bili_title"),
    }


def gold_chat_summary(
    source_id: str,
    *,
    config: Config | None = None,
    row: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """列表页用的导出摘要（优先读导出 JSON，其次读库内 payload）。"""
    data = load_gold_chat(source_id, config=config)
    if data:
        daily = data.get("daily_story") if isinstance(data.get("daily_story"), dict) else {}
        chat_chars = data.get("chat_chars")
        if chat_chars is None and daily:
            chat_chars = dialogue_total_chars(daily)
        chat_lines = data.get("chat_lines")
        if chat_lines is None and daily:
            chat_lines = len(daily.get("dialogue") or [])
        return {
            "has_gold_chat": True,
            "chat_chars": chat_chars,
            "chat_lines": chat_lines,
            "scene_title": daily.get("scene_title") or data.get("scene_title"),  # type: ignore[union-attr]
            "exported_at": data.get("exported_at"),
        }

    if row is None:
        row = repo_gold_story.get_by_source_id(source_id=str(source_id or "").strip())
    if row:
        payload = cast(dict[str, Any], row.get("payload") or {})
        cached = _summary_from_payload(payload)
        if cached:
            return cached
    return {"has_gold_chat": False}
