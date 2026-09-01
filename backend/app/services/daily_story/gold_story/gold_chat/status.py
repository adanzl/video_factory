"""gold_chat 转换结果落库（成功清错、失败可追溯）。"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.repositories import repo_gold_story

logger = logging.getLogger(__name__)

_GOLD_CHAT_ERROR_CLEAR_KEYS = (
    "gold_chat_last_error",
    "gold_chat_last_failed_at",
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def format_gold_chat_error(exc: BaseException) -> str:
    text = str(exc or "").strip()
    if text:
        return text
    return exc.__class__.__name__


def gold_chat_error_from_payload(payload: dict[str, Any] | None) -> dict[str, str] | None:
    if not isinstance(payload, dict):
        return None
    err = str(payload.get("gold_chat_last_error") or "").strip()
    if not err:
        return None
    out: dict[str, str] = {"error": err}
    failed_at = str(payload.get("gold_chat_last_failed_at") or "").strip()
    if failed_at:
        out["failed_at"] = failed_at
    return out


def record_gold_chat_failure(
    gold_story_id: int,
    exc: BaseException,
    *,
    source_id: str = "",
    stage: str = "convert",
) -> None:
    """转换失败写入 payload，供详情页展示。"""
    gid = int(gold_story_id)
    if gid <= 0:
        return
    message = format_gold_chat_error(exc)
    now = _now_iso()
    repo_gold_story.patch_story_payload(
        gid,
        {
            "gold_chat_last_error": message,
            "gold_chat_last_failed_at": now,
            "gold_chat_last_error_stage": str(stage or "convert").strip() or "convert",
        },
    )
    logger.error(
        "[GOLD_CHAT] failure recorded id=%s source_id=%s stage=%s error=%s",
        gid,
        source_id or "?",
        stage,
        message,
    )


def clear_gold_chat_failure(gold_story_id: int, *, source_id: str = "") -> None:
    """转换成功导出后清除失败记录。"""
    gid = int(gold_story_id)
    if gid <= 0:
        return
    repo_gold_story.patch_story_payload(
        gid,
        {key: None for key in _GOLD_CHAT_ERROR_CLEAR_KEYS}
        | {"gold_chat_last_error_stage": None},
    )
    logger.info(
        "[GOLD_CHAT] failure cleared id=%s source_id=%s",
        gid,
        source_id or "?",
    )
