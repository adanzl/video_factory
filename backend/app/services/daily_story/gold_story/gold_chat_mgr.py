"""gold_chat API 业务层。"""

from __future__ import annotations

from typing import Any

from app.config import Config
from app.repositories import repo_gold_story
from app.services.daily_story.gold_story.gold_chat_batch import run_gold_chat_batch
from app.services.daily_story.gold_story.gold_chat_convert import (
    convert_gold_chat,
    gold_chat_summary,
    import_gold_chat_daily_story,
    load_gold_chat,
    load_gold_chat_for_row,
)
from app.services.daily_story.gold_story.export_story import load_transcript_for_row
from app.services.daily_story.gold_story.pipeline import run_collect_pipeline


def _ensure_schema() -> None:
    from app.repositories.db_obj import db
    from app.repositories.schema import apply_gold_story_schema
    from app.repositories import sql_exec as sql

    conn = db.session.connection().connection.dbapi_connection
    apply_gold_story_schema(conn)
    sql.commit()


def _row_to_list_item(row: dict[str, Any], *, config: Config) -> dict[str, Any]:
    sid = str(row.get("source_id") or "").strip()
    payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
    summary = gold_chat_summary(sid, config=config, row=row)
    bili_title = payload.get("bili_title")
    return {
        "id": row.get("id"),
        "source_id": sid,
        "url": payload.get("bili_url") or row.get("url"),
        "title": row.get("title"),
        "bili_title": bili_title,
        "status": row.get("status"),
        "mechanism": row.get("mechanism"),
        "structure_type": row.get("structure_type"),
        "conflict_core": row.get("conflict_core"),
        "auto_score": row.get("auto_score"),
        "gold_chat_daily_story_id": row.get("gold_chat_daily_story_id"),
        **summary,
    }


def _row_to_dump(row: dict[str, Any]) -> dict[str, Any]:
    """金故事 dump（story_raw + 结构化抽取）。"""
    payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
    dump: dict[str, Any] = {}
    for key in (
        "story_raw",
        "perspective",
        "funny_why",
        "beat",
        "banned_literals",
        "dialogue_seed",
        "setting",
        "closing_intent",
        "speaker_map_note",
        "scene_contract",
        "source_type",
    ):
        val = payload.get(key)
        if val not in (None, "", [], {}):
            dump[key] = val
    story_raw = str(row.get("story_raw") or payload.get("story_raw") or "").strip()
    if story_raw:
        dump["story_raw"] = story_raw
    transcript_path = row.get("transcript_path")
    if transcript_path:
        dump["transcript_path"] = transcript_path
    return dump


def _row_to_detail_header(row: dict[str, Any]) -> dict[str, Any]:
    payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
    sid = str(row.get("source_id") or "").strip()
    return {
        "id": row.get("id"),
        "source_id": sid,
        "url": payload.get("bili_url") or row.get("url"),
        "title": row.get("title"),
        "bili_title": payload.get("bili_title"),
        "status": row.get("status"),
        "mechanism": row.get("mechanism"),
        "structure_type": row.get("structure_type"),
        "conflict_core": row.get("conflict_core"),
        "auto_score": row.get("auto_score"),
        "gold_chat_daily_story_id": row.get("gold_chat_daily_story_id"),
    }


class GoldChatMgr:
    def list_items(
        self,
        *,
        status: str | None = None,
        limit: int = 15,
        offset: int = 0,
    ) -> dict[str, Any]:
        _ensure_schema()
        cfg = Config()
        limit = max(1, min(limit, 200))
        offset = max(0, offset)
        rows = repo_gold_story.list_stories(
            status=status or None,
            limit=limit,
            offset=offset,
        )
        total = repo_gold_story.count_stories(status=status or None)
        items = [_row_to_list_item(row, config=cfg) for row in rows]
        return {"items": items, "total": total, "limit": limit, "offset": offset}

    def get_chat(
        self,
        *,
        gold_story_id: int | None = None,
        source_id: str | None = None,
    ) -> dict[str, Any]:
        _ensure_schema()
        cfg = Config()
        row: dict[str, Any] | None = None
        if gold_story_id is not None:
            row = repo_gold_story.get_story(int(gold_story_id))
            source_id = str(row.get("source_id") or "").strip()
        elif source_id:
            row = repo_gold_story.get_by_source_id(source_id=str(source_id).strip())
        else:
            raise ValueError("id 或 source_id 必填")

        if row is None:
            raise KeyError("金故事不存在")
        if not source_id:
            raise KeyError("gold_story missing source_id")

        payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
        export = load_gold_chat_for_row(row, config=cfg)
        gold_chat: dict[str, Any] | None = None
        has_gold_chat = export is not None

        if export is not None:
            gold_chat = {
                "chat_chars": export.get("chat_chars"),
                "chat_lines": export.get("chat_lines"),
                "exported_at": export.get("exported_at"),
                "daily_story": export.get("daily_story"),
                "gold_meta": export.get("gold_meta"),
            }
        elif payload.get("gold_chat_exported_at"):
            gold_chat = {
                "export_missing": True,
                "exported_at": payload.get("gold_chat_exported_at"),
                "chat_chars": payload.get("gold_chat_chars"),
                "chat_lines": payload.get("gold_chat_lines"),
                "scene_title": payload.get("gold_chat_scene_title"),
            }

        return {
            **_row_to_detail_header(row),
            "dump": _row_to_dump(row),
            "has_gold_chat": has_gold_chat,
            "gold_chat": gold_chat,
        }

    def get_transcript(
        self,
        *,
        gold_story_id: int | None = None,
        source_id: str | None = None,
    ) -> dict[str, Any]:
        _ensure_schema()
        cfg = Config()
        row: dict[str, Any] | None = None
        if gold_story_id is not None:
            row = repo_gold_story.get_story(int(gold_story_id))
        elif source_id:
            row = repo_gold_story.get_by_source_id(source_id=str(source_id).strip())
        else:
            raise ValueError("id 或 source_id 必填")

        if row is None:
            raise KeyError("金故事不存在")

        return load_transcript_for_row(row, config=cfg)

    def convert_one(
        self,
        *,
        gold_story_id: int | None = None,
        source_id: str | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        _ensure_schema()
        cfg = Config()
        row: dict[str, Any] | None = None
        if gold_story_id is not None:
            row = repo_gold_story.get_story(int(gold_story_id))
        elif source_id:
            row = repo_gold_story.get_by_source_id(source_id=str(source_id).strip())
        else:
            raise ValueError("id 或 source_id 必填")

        if row is None:
            raise KeyError("金故事不存在")

        sid = str(row.get("source_id") or "").strip()
        if not force and gold_chat_summary(sid, config=cfg).get("has_gold_chat"):
            export = load_gold_chat(sid, config=cfg)
            return {
                "action": "skip",
                "reason": "already_exported",
                "source_id": sid,
                "gold_story_id": row.get("id"),
                "export": export,
            }

        outcome = convert_gold_chat(row, config=cfg)
        return {"action": "ok", **outcome}

    def import_one(
        self,
        *,
        gold_story_id: int | None = None,
        source_id: str | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        _ensure_schema()
        cfg = Config()
        row: dict[str, Any] | None = None
        if gold_story_id is not None:
            row = repo_gold_story.get_story(int(gold_story_id))
        elif source_id:
            row = repo_gold_story.get_by_source_id(source_id=str(source_id).strip())
        else:
            raise ValueError("id 或 source_id 必填")

        if row is None:
            raise KeyError("金故事不存在")

        return import_gold_chat_daily_story(row, config=cfg, force=force)

    def batch_convert(
        self,
        *,
        max_items: int = 10,
        status: str = "active",
        gold_story_ids: list[int] | None = None,
        source_ids: list[str] | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        return run_gold_chat_batch(
            max_items=max_items,
            status=status,
            gold_story_ids=gold_story_ids,
            source_ids=source_ids,
            skip_existing=not force,
        )

    def collect(
        self,
        *,
        max_candidates: int = 10,
    ) -> dict[str, Any]:
        """H0–H4：B 站搜索采集并入库。"""
        _ensure_schema()
        max_candidates = max(1, min(int(max_candidates), 50))
        report = run_collect_pipeline(
            max_candidates=max_candidates,
            skip_transcript=False,
            dry_run=False,
            write_list=True,
        )
        skipped = sum(1 for r in report.get("results") or [] if r.get("action") == "skip")
        failed = sum(
            1 for r in report.get("results") or [] if r.get("action") == "error"
        )
        return {
            "workflow": "gold_story_collect",
            "max": max_candidates,
            "candidates": report.get("candidates", 0),
            "inserted": report.get("inserted", 0),
            "inserted_rejected": report.get("inserted_rejected", 0),
            "skipped": skipped,
            "failed": failed,
            "results": report.get("results") or [],
            "candidates_file": report.get("candidates_file"),
        }


gold_chat_mgr = GoldChatMgr()
