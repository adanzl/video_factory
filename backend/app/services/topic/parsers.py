"""选题 LLM 响应解析。"""

from __future__ import annotations

from typing import Any

from app.services.topic.catalog import (
    ALL_TOPIC_TEMPLATES,
    CATEGORY_SCIENCE,
    normalize_category,
)
from app.services.topic.text import (
    normalize_title,
    topic_title_issue,
)

_TOPIC_PARSE_RETRY_MARKERS = ("均未通过", "未返回 topics")


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
        raise ValueError("LLM 未返回 topics 数组")

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
        template = str(item.get("template") or "").strip()
        if template not in ALL_TOPIC_TEMPLATES:
            template = "误区反问式"
        if topic_title_issue(title, category=category, template=template):
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
        raise ValueError(_format_all_filtered_error(items, max_title_len=max_title_len))
    return out


def format_topic_parse_feedback(raw: dict[str, Any], *, max_title_len: int) -> str:
    items = raw.get("topics")
    if not isinstance(items, list) or not items:
        return "- LLM 未返回有效的 topics 数组"
    rejections = _collect_topic_rejections(items, max_title_len=max_title_len)
    if not rejections:
        return "- 标题均未通过校验（原因未知）"
    return "\n".join(f"- {line}" for line in rejections[:5])


def is_topic_parse_retryable(exc: ValueError) -> bool:
    msg = str(exc)
    return any(marker in msg for marker in _TOPIC_PARSE_RETRY_MARKERS)


def _format_all_filtered_error(items: list[Any], *, max_title_len: int) -> str:
    rejections = _collect_topic_rejections(items, max_title_len=max_title_len)
    if not rejections:
        return "生成的标题均未通过质量校验，请换主题或稍后重试"
    sample = "；".join(rejections[:3])
    return f"生成的标题均未通过质量校验：{sample}"


def _collect_topic_rejections(items: list[Any], *, max_title_len: int) -> list[str]:
    lines: list[str] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            lines.append("条目格式错误（非 JSON 对象）")
            continue
        raw_category = str(item.get("category") or item.get("track") or "").strip()
        title = normalize_title(str(item.get("title") or ""), max_len=max_title_len)
        if not title:
            lines.append("标题为空")
            continue
        if title in seen:
            lines.append(f"「{title}」：重复标题")
            continue
        seen.add(title)
        category = normalize_category(raw_category or None)
        template = str(item.get("template") or "").strip()
        if template not in ALL_TOPIC_TEMPLATES:
            template = "误区反问式"
        issue = topic_title_issue(title, category=category, template=template)
        if issue:
            lines.append(f"「{title}」：{issue}")
        else:
            lines.append(f"「{title}」：未通过校验")
    return lines


def _topics_from_titles(titles: list[str], *, max_title_len: int) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw in titles:
        title = normalize_title(raw, max_len=max_title_len)
        if not title or title in seen:
            continue
        if topic_title_issue(title, category=CATEGORY_SCIENCE, template="误区反问式"):
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
