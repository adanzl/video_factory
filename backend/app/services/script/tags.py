"""推荐标签：提示词、LLM 响应解析。"""

from __future__ import annotations

from typing import Any

from app.utils.job_info import CONTENT_STYLE_DAILY_STORY


def build_tags_system_prompt(*, content_style: str | None = None) -> str:
    if content_style == CONTENT_STYLE_DAILY_STORY:
        return (
            "你是 B 站家庭日常对话短剧标签推荐师。根据视频标题与对白内容，推荐 8 个话题标签。\n"
            "要求：\n"
            "1. 每个标签以 # 开头，如 #亲子日常 #儿童对话\n"
            "2. 标签需准确反映视频内容，不得编造口播未涉及的话题\n"
            "3. 标签之间用空格分隔\n"
            "4. 输出 8 个标签，不要多也不要少\n"
            "5. 面向孩子和有娃家长；可含亲子/儿童/家庭日常/搞笑对话等，禁止硬套科普标签\n"
            'JSON 输出样例：{"tags": "#亲子日常 #儿童对话 #姐弟 #家庭搞笑 #育儿 #生活日常 #昭墨日常 #短剧"}'
        )
    return (
        "你是 B 站短视频标签推荐师。根据视频标题与口播内容，推荐 8 个话题标签。\n"
        "要求：\n"
        "1. 每个标签以 # 开头，如 #科普 #冷知识\n"
        "2. 标签需准确反映视频内容，不得编造口播未涉及的话题\n"
        "3. 标签之间用空格分隔\n"
        "4. 输出 8 个标签，不要多也不要少\n"
        'JSON 输出样例：{"tags": "#科普 #冷知识 #涨知识 #科学 #实验 #自然 #物理 #化学"}'
    )


def build_tags_user_prompt(*, title: str, narration: str) -> str:
    snippet = narration.strip()
    if len(snippet) > 1200:
        snippet = snippet[:1200] + "…"
    return (
        f"视频标题：{title}\n"
        f"完整口播：\n{snippet}\n\n"
        "请推荐 8 个相关话题标签。"
    )


def parse_tags_payload(raw: dict[str, Any]) -> list[str]:
    tags_raw = raw.get("tags")
    if not isinstance(tags_raw, str) or not tags_raw.strip():
        raise ValueError("LLM tags response missing tags field")
    parts = [t.strip() for t in tags_raw.split("#") if t.strip()]
    return ["#" + t for t in parts[:8]]


def build_tags_prompts(
    title: str,
    narration: str,
    *,
    content_style: str | None = None,
) -> dict[str, str]:
    return {
        "step": "tags",
        "label": "推荐标签",
        "system": build_tags_system_prompt(content_style=content_style),
        "user": build_tags_user_prompt(title=title, narration=narration),
    }
