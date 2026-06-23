"""将用户关键词改写为 Pixabay 友好的英文搜索词。"""

from __future__ import annotations

import logging
import re

from app.services.clip_search.query_rewrite_prompts import (
    build_pixabay_query_system_prompt,
    build_pixabay_query_user_prompt,
    parse_pixabay_query_payload,
)
from app.services.llm.llm_mgr import llm_mgr

logger = logging.getLogger(__name__)

_CJK_RE = re.compile(r"[\u3400-\u9fff]")


def needs_pixabay_query_rewrite(query: str, *, language: str | None) -> bool:
    """中文输入或语言偏好为中文时，走 LLM 改写。"""
    if language == "zh":
        return True
    return bool(_CJK_RE.search(query))


def rewrite_pixabay_search_query(
    query: str,
    *,
    language: str | None = None,
) -> str:
    cleaned = query.strip()
    if not cleaned:
        raise ValueError("query is required")
    if not needs_pixabay_query_rewrite(cleaned, language=language):
        return cleaned

    rewritten = llm_mgr.rewrite_pixabay_query(cleaned, language=language)
    if not rewritten.strip():
        return cleaned
    logger.info(
        "[CLIP] pixabay query rewrite: %r -> %r",
        cleaned[:80],
        rewritten[:80],
    )
    return rewritten.strip()
