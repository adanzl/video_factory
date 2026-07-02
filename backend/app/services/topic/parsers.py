"""选题 LLM 响应解析。"""

from __future__ import annotations

from typing import Any

from app.services.topic.catalog import (
    ALL_TOPIC_TEMPLATES,
    CATEGORY_SCIENCE,
    normalize_category,
)
from app.services.topic.text import (
    incomplete_conversational_issue,
    misconception_template_issue,
    needs_conversational_rewrite,
    normalize_title,
    open_faq_title_issue,
)


def parse_topics_payload(raw: dict[str, Any], *, max_title_len: int) -> list[dict[str, str]]:
    for key in ("topics", "titles"):
        items = raw.get(key)
        if not isinstance(items, list) or not items:
            continue
        if all(isinstance(item, str) for item in items):
            out = _topics_from_titles(items, max_title_len=max_title_len)
            if out:
                return out
        if key == "topics":
            break

    items = raw.get("topics")
    if not isinstance(items, list) or not items:
        raise ValueError("LLM response missing topics array")

    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        raw_category = str(item.get("category") or item.get("track") or "").strip()
        title = normalize_title(str(item.get("title") or ""), max_len=max_title_len)
        if not title or title in seen:
            continue
        category = normalize_category(raw_category or None)
        if open_faq_title_issue(title, category=category):
            continue
        template = str(item.get("template") or "").strip()
        if template not in ALL_TOPIC_TEMPLATES:
            template = "误区反问式"
        if misconception_template_issue(title, category=category, template=template):
            continue
        if incomplete_conversational_issue(title):
            continue
        raw_kws = item.get("keywords") or item.get("keyword") or ""
        if isinstance(raw_kws, list):
            kw_str = ",".join(str(k).strip()[:6] for k in raw_kws if str(k).strip())
        else:
            kw_str = str(raw_kws).strip()[:24]
        hook = str(item.get("hook") or "").strip()
        seen.add(title)
        out.append(
            {
                "title": title,
                "keyword": kw_str or None,
                "category": category,
                "template": template,
                "hook": hook,
            }
        )
    if not out:
        raise ValueError("LLM topics array has no valid entries")
    return out


def _topics_from_titles(titles: list[str], *, max_title_len: int) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw in titles:
        title = normalize_title(raw, max_len=max_title_len)
        if not title or title in seen:
            continue
        if open_faq_title_issue(title, category=CATEGORY_SCIENCE):
            continue
        seen.add(title)
        out.append(
            {
                "title": title,
                "category": CATEGORY_SCIENCE,
                "template": "误区反问式",
                "hook": "",
            }
        )
    return out
