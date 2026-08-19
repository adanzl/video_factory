"""B 站分区 tid。

稿件默认公开（审核通过后开放浏览），不走「仅自己可见」。
"""

from __future__ import annotations

from typing import Any

CHAT_PIPELINE = "chat"
DEFAULT_TID = 201  # 知识 → 科学科普
CHAT_TID = 164  # 生活 → 亲子


def resolve_tid(pipeline: str | None, *, settings: Any | None = None) -> int:
    """chat 走亲子，其余用全局默认分区。"""
    from app.config import get_settings

    cfg = settings or get_settings()
    if (pipeline or "").strip() == CHAT_PIPELINE:
        return int(cfg.bili_tid_chat)
    return int(cfg.bili_tid)
