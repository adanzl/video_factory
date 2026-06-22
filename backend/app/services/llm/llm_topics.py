"""选题生成：Prompt 与响应解析。"""

from __future__ import annotations

import re
from typing import Any

_TOPIC_TRACKS = frozenset(
    {
        "日常科学原理",
        "生活避坑实用常识",
        "数码小白避坑",
        "古代冷门生活史",
    }
)
_TOPIC_TEMPLATES = frozenset({"误区反问式", "反差好奇式", "实操避坑式"})


def build_topic_system_prompt(*, max_title_len: int) -> str:
    return (
        "你是 B 站科普短视频选题策划。输出 JSON，字段 topics。"
        "topics 为数组，每项含 title、track、template、hook。"
        f"title 为视频标题：不含空格换行，≤{max_title_len} 字，适合封面三行展示，"
        "必须有反常识/误区/反差钩子，禁止平淡陈述。"
        "track 从以下四选一：日常科学原理、生活避坑实用常识、数码小白避坑、古代冷门生活史。"
        "template 从以下三选一：误区反问式、反差好奇式、实操避坑式。"
        "hook 用一句话说明为什么观众会点进来（15-30字）。"
        "硬性禁止：医疗养生、理财股市、时政情感、热点新闻、真人出镜场景、"
        "无法核验的争议、预测性表述。"
        "偏好：画面可用卡通/示意插画表达，科学常识或生活原理，长尾搜索向。"
        "标题分布建议：误区反问式约 7 条、反差好奇式约 2 条、实操避坑式约 1 条。"
        'JSON 输出样例：{"topics": [{"title": "标题", "track": "日常科学原理", '
        '"template": "误区反问式", "hook": "一句话钩子"}]}'
    )


def build_topic_user_prompt(*, theme: str, count: int) -> str:
    return (
        f"主题方向：{theme.strip()}\n"
        f"请生成 {count} 个互不重复、适合 AI 全自动科普成片的中文视频标题。"
    )


def normalize_title(title: str, *, max_len: int) -> str:
    cleaned = re.sub(r"\s+", "", title.strip())
    if len(cleaned) > max_len:
        return cleaned[:max_len]
    return cleaned


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
        title = normalize_title(str(item.get("title") or ""), max_len=max_title_len)
        if not title or title in seen:
            continue
        track = str(item.get("track") or "").strip()
        template = str(item.get("template") or "").strip()
        hook = str(item.get("hook") or "").strip()
        if track not in _TOPIC_TRACKS:
            track = "日常科学原理"
        if template not in _TOPIC_TEMPLATES:
            template = "误区反问式"
        seen.add(title)
        out.append(
            {
                "title": title,
                "track": track,
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
                "track": "日常科学原理",
                "template": "误区反问式",
                "hook": "",
            }
        )
    return out
