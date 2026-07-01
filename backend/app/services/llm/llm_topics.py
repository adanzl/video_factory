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

# 对话反转式标题：回应须一眼能懂，禁止多跳推理链（可复用于生成与优化 prompt）
_CONVERSATIONAL_TITLE_RULE = (
    "对话反转式：问句抛出误区，回应须一眼能懂地反驳/戳穿同一命题，一步直达，禁止多跳推理链。"
    "可用「明明」「就这」「真以为」等嘲讽语气。"
    "正例：日本断供光刻胶？明明仓库都堆成山了（两句同一话题，一步反驳）。"
    "反例：西班牙人怕热？电表转得比你慢（虽可脑补怕热→开空调→费电，但链条太长太绕，禁止）。"
    "回应与问句最好共用核心词或同一可见画面。"
)


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
        f"{_CONVERSATIONAL_TITLE_RULE}"
        "字不够可以略写，但态度要够。\n"
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


_CONVERSATIONAL_TITLE_RE = re.compile(r"[？?]")


def build_topic_optimize_system_prompt(*, max_title_len: int, track: str | None = None) -> str:
    """选题优化专用 system prompt：润色表达，不换题材。"""
    if track == "历史悬案":
        return (
            "你是 B 站历史悬案视频选题优化师。输出 JSON，字段 topics（数组仅 1 项）。"
            "每项含 title、keywords、track、template、hook。"
            f"title 不含空格换行，≤{max_title_len} 字。"
            "优化规则：保持同一历史人物/事件/悬案，只改进标题悬念与 hook，禁止换成其他国家、现代生活或无关题材。"
            "标题格式须仍为「历史代号：一句话悬念」，例如「烛影斧声：宋太祖半夜暴毙」。"
            "track 固定为「历史悬案」。template 保持用户给出的原模板。"
            "hook 15-30 字，说明点击动机。"
            'JSON 样例：{"topics": [{"title": "标题", "keywords": ["和珅"], "track": "历史悬案", '
            '"template": "悬念钩子式", "hook": "一句话钩子"}]}'
        )
    return (
        "你是 B 站科普短视频选题优化师。输出 JSON，字段 topics（数组仅 1 项）。"
        "每项含 title、keywords、track、template、hook。"
        f"title 不含空格换行，≤{max_title_len} 字。"
        "优化规则：保持同一科普主题、同一核心概念，只改进标题吸引力与 hook。"
        "禁止更换题材或蹭无关热点。"
        f"{_CONVERSATIONAL_TITLE_RULE}"
        "若原标题含问号对话体，优化后仍须一步直达、同一话题，禁止多跳推理链。"
        "track、template 须与用户给出的原值一致。"
        "hook 15-30 字。"
        'JSON 样例：{"topics": [{"title": "标题", "keywords": ["关键词"], "track": "日常科学原理", '
        '"template": "误区反问式", "hook": "一句话钩子"}]}'
    )


def build_topic_optimize_user_prompt(
    *,
    title: str,
    track: str | None = None,
    template: str | None = None,
    hook: str | None = None,
) -> str:
    lines = [
        "请优化以下选题，输出 1 个新版本（topics 数组仅 1 项）。",
        "硬性要求：同一题材、同一核心知识点或事件，只润色标题与 hook，不得另起新题。",
        "标题须与原版表达不同，但读者应一眼看出是同一主题。",
        "",
        f"原标题：{title.strip()}",
    ]
    if track:
        lines.append(f"原赛道：{track.strip()}（优化后 track 必须相同）")
    if template:
        lines.append(f"原模板：{template.strip()}（优化后 template 必须相同）")
    if hook:
        lines.append(f"原钩子：{hook.strip()}")
    if _CONVERSATIONAL_TITLE_RE.search(title):
        lines.append(
            "原标题为对话反转式：优化后问句与回应须一步直达、同一话题，"
            "禁止多跳推理链（如怕热→开空调→费电→电表，观众需脑补才能接上）。"
        )
    if track == "历史悬案":
        lines.append("须保持同一历史人物或悬案，标题仍为「代号：悬念」格式。")
    return "\n".join(lines)


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
