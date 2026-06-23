"""将用户关键词改写为素材库友好的英文搜索词。"""

from __future__ import annotations

import logging

from app.services.llm.llm_mgr import llm_mgr

logger = logging.getLogger(__name__)


def rewrite_ai_search_query(
    query: str,
    *,
    language: str | None = None,
) -> str:
    """AI 搜索：始终经 LLM 转为英文搜索词。"""
    cleaned = query.strip()
    if not cleaned:
        raise ValueError("query is required")

    rewritten = llm_mgr.rewrite_pixabay_query(cleaned, language=language)
    if not rewritten.strip():
        return cleaned
    logger.info(
        "[CLIP] ai search query rewrite: %r -> %r",
        cleaned[:80],
        rewritten[:80],
    )
    return rewritten.strip()
