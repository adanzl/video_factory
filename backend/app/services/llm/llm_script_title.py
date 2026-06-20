"""脚本标题优化：在成稿后强化吸引力并满足字数约束。"""

from __future__ import annotations

from typing import Any

from app.services.llm.llm_topics import normalize_title


def build_title_optimize_system_prompt(*, max_title_len: int) -> str:
    return (
        "你是 B 站科普短视频标题优化师。根据初稿标题与口播摘要，输出 JSON，字段 title。"
        f"title 为优化后的视频标题：不含空格换行，≤{max_title_len} 字，适合封面最多三行展示。"
        "优化目标：比初稿更有点击欲，保留核心主题，强化反常识/误区/反差钩子。"
        "优先使用误区反问式、反差好奇式、实操避坑式之一，避免平淡陈述与标题党夸张。"
        "禁止：医疗养生、理财股市、时政情感、热点新闻、真人出镜、无法核验的争议。"
        "不得改变口播主题方向，不得引入口播未涉及的新概念。"
    )


def build_title_optimize_user_prompt(
    *,
    draft_title: str,
    narration: str,
    max_title_len: int,
) -> str:
    snippet = narration.strip().replace("\n", "")
    if len(snippet) > 400:
        snippet = snippet[:400] + "…"
    return (
        f"初稿标题：{draft_title}\n"
        f"口播摘要（前段）：{snippet}\n"
        f"请输出更吸引人且 ≤{max_title_len} 字的 title。"
    )


def parse_title_optimize_payload(raw: dict[str, Any], *, max_title_len: int) -> str:
    title = raw.get("title")
    if not isinstance(title, str) or not title.strip():
        raise ValueError("LLM title optimize response missing title")
    return normalize_title(title, max_len=max_title_len)
