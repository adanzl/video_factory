"""选题标题文本规范化与结构校验。"""

from __future__ import annotations

import re

from app.services.topic.catalog import CATEGORY_HISTORY, resolve_category

_OPEN_FAQ_PATTERNS = re.compile(
    r"能提前多久|提前多久|能预警多久|预警能.{0,4}多久|"
    r"能管多久|能撑多久|能坚持多久|能活多久|能存多久|"
    r"^[^？?：:]{2,16}是什么$|"
    r"有什么用|有何用|干嘛用|作何用|"
    r"是多少|有多少|几[秒分天时]钟|多长时间"
)


def open_faq_title_issue(title: str, *, category: str | None = None) -> str | None:
    """科学/时事类禁止百科式中性提问（无误区、无反驳落点）。"""
    if resolve_category(category) == CATEGORY_HISTORY:
        return None
    text = title.strip()
    if not text:
        return None
    # 问句含 FAQ 关键词但已有完整反驳半句时允许（如「能提前多久？明明只有几十秒」）
    if incomplete_conversational_issue(text) is None:
        mark_idx = max(text.rfind("？"), text.rfind("?"))
        if mark_idx >= 0 and text[mark_idx + 1 :].strip():
            return None
    if _OPEN_FAQ_PATTERNS.search(text):
        return "百科式中性提问：缺少误区反驳或反差结构"
    return None


def misconception_template_issue(
    title: str,
    *,
    category: str | None = None,
    template: str | None = None,
) -> str | None:
    """误区反问式须为问号对话体，禁止纯陈述句。"""
    if resolve_category(category) == CATEGORY_HISTORY:
        return None
    if template != "误区反问式":
        return None
    text = title.strip()
    if not text:
        return None
    if "?" not in text and "？" not in text:
        return "误区反问式：须为问号对话体且含实质反驳"
    return None


def incomplete_conversational_issue(title: str) -> str | None:
    """对话反转式禁止半句问法（问号后无回应）。"""
    text = title.strip()
    mark_idx = max(text.rfind("？"), text.rfind("?"))
    if mark_idx < 0:
        return None
    if not text[mark_idx + 1 :].strip():
        return "对话反转式：问号后缺少回应"
    return None


def needs_conversational_rewrite(
    title: str,
    *,
    category: str | None = None,
    template: str | None = None,
) -> bool:
    """科学/时事类标题是否须改成完整对话反转句式。"""
    if resolve_category(category) == CATEGORY_HISTORY:
        return False
    if open_faq_title_issue(title, category=category):
        return True
    if misconception_template_issue(title, category=category, template=template):
        return True
    if incomplete_conversational_issue(title):
        return True
    return False


def normalize_title(title: str, *, max_len: int) -> str:
    cleaned = re.sub(r"\s+", "", title.strip())
    if len(cleaned) <= max_len + 2:
        return cleaned
    truncated = cleaned[:max_len]
    for punct in ("。", "！", "？", "，", "——"):
        idx = truncated.rfind(punct)
        if idx >= max_len // 2:
            return truncated[:idx]
    return cleaned[:max_len]
