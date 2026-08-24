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


class GoldChatMgr:
    def list_items(
        self,
        *,
        status: str | None = "active",
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

        if not source_id:
            raise KeyError("gold_story missing source_id")

        export = load_gold_chat_for_row(row, config=cfg)
        if export is None:
            payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
            if payload.get("gold_chat_exported_at"):
                raise FileNotFoundError(
                    f"gold_chat 摘要已在库内，但导出文件缺失: {source_id}；请重转"
                )
            raise FileNotFoundError(f"尚未导出 gold_chat: {source_id}")

        payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
        return {
            "gold_story": row,
            "bili_title": payload.get("bili_title"),
            "gold_chat_daily_story_id": row.get("gold_chat_daily_story_id"),
            **export,
        }

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


gold_chat_mgr = GoldChatMgr()
