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
        "历史悬案",
    }
)
_TOPIC_TEMPLATES = frozenset({"误区反问式", "反差好奇式", "实操避坑式", "悬念钩子式", "未解之谜式"})


def build_topic_system_prompt(*, max_title_len: int, track: str | None = None) -> str:
    if track == "历史悬案":
        return _history_mystery_prompt(max_title_len)
    return _general_topic_prompt(max_title_len)


def _history_mystery_prompt(max_title_len: int) -> str:
    return (
        "你是 B 站历史悬案视频选题策划。输出 JSON，字段 topics。"
        "topics 为数组，每项含 title、keyword、track、template、hook。"
        f"title 不含空格换行，≤{max_title_len} 字。"
        "标题格式：历史代号 + 一句话悬念，例如「烛影斧声：宋太祖半夜暴毙」「雍正暴毙：圆明园咯血无人敢近」。"
        "必须包含一个反常画面，不笼统。"
        "选知名历史人物（慈禧、和珅、秦始皇、雍正、杨贵妃、崇祯、曹操、成吉思汗等），不选冷门人物。"
        "track 固定为「历史悬案」。template 从五选一：误区反问式、反差好奇式、实操避坑式、悬念钩子式、未解之谜式。"
        "hook 一句话说明为什么观众会点进来（15-30字）。"
        "keywords 为该主题涉及的核心实体数组（人名/地名/事件名，每项2-6字，1-3项）。"
        "硬性禁止：医疗养生、理财股市、时政情感、热点新闻、真人出镜、无法核验的争议。"
        "标题必须包含一个具体反转或矛盾细节。写不下的信息放进 hook。"
        'JSON 输出样例：{"topics": [{"title": "标题", "keywords": ["和珅","嘉庆"], "track": "历史悬案", '
        '"template": "误区反问式", "hook": "一句话钩子"}]}'
    )


def _general_topic_prompt(max_title_len: int) -> str:
    return (
        "你是 B 站短视频选题策划。输出 JSON，字段 topics。"
        "topics 为数组，每项含 title、keyword、track、template、hook。"
        f"title 不含空格换行，≤{max_title_len} 字。"
        "标题可选对话反转式风格：用问句抛出事件，回应部分要带嘲讽——用「明明」「就这」「真以为」等词制造「你在担心啥？」的态度。"
        "例如：日本断供光刻胶？明明仓库都堆成山了。美国限芯令？工程师咖啡都凉了。字不够可以略写，但态度要够。\n"
        "track 从以下四选一：日常科学原理、生活避坑实用常识、数码小白避坑、古代冷门生活史。"
        "科技产业链、芯片、光刻胶、手机等话题选「数码小白避坑」或「日常科学原理」。"
        "template 从五选一：误区反问式、反差好奇式、实操避坑式、悬念钩子式、未解之谜式。"
        "hook 一句话说明为什么观众会点进来（15-30字）。keywords 为2-6字核心实体。"
        "硬性禁止：医疗养生、理财股市、时政情感、热点新闻、真人出镜。"
        'JSON 输出样例：{"topics": [{"title": "标题", "keywords": ["光刻胶","芯片"], "track": "日常科学原理", '
        '"template": "误区反问式", "hook": "一句话钩子"}]}'
    )


def build_topic_user_prompt(*, theme: str, count: int) -> str:
    return (
        f"主题方向：{theme.strip()}\n"
        f"请生成 {count} 个互不重复、适合 AI 全自动科普成片的中文视频标题。"
    )


def normalize_title(title: str, *, max_len: int, track: str = "") -> str:
    cleaned = re.sub(r"\s+", "", title.strip())
    if len(cleaned) <= max_len + 2:
        return cleaned
    truncated = cleaned[:max_len]
    for p in ("。", "！", "？", "，", "——"):
        idx = truncated.rfind(p)
        if idx >= max_len // 2:
            return truncated[:idx]
    return cleaned[:max_len]


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
        title = normalize_title(str(item.get("title") or ""), max_len=max_title_len, track=item.get("track", ""))
        if not title or title in seen:
            continue
        raw_kws = item.get("keywords") or item.get("keyword") or ""
        if isinstance(raw_kws, list):
            kw_str = ",".join(str(k).strip()[:6] for k in raw_kws if str(k).strip())
        else:
            kw_str = str(raw_kws).strip()[:8]
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
                "keyword": kw_str or None,
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
