"""选题 LLM 响应解析。"""

from __future__ import annotations

from typing import Any

from app.services.topic.catalog import (
    ALL_TOPIC_TEMPLATES,
    CATEGORY_SCIENCE,
    normalize_category,
)
from app.services.topic.text import normalize_title


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
        raw_kws = item.get("keywords") or item.get("keyword") or ""
        if isinstance(raw_kws, list):
            kw_str = ",".join(str(k).strip()[:6] for k in raw_kws if str(k).strip())
        else:
            kw_str = str(raw_kws).strip()[:24]
        template = str(item.get("template") or "").strip()
        hook = str(item.get("hook") or "").strip()
        category = normalize_category(raw_category or None)
        if template not in ALL_TOPIC_TEMPLATES:
            template = "误区反问式"
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
