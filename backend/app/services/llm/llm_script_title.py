"""脚本标题优化：在成稿后强化吸引力并满足字数约束。"""

from __future__ import annotations

from typing import Any

from app.services.llm.llm_topics import normalize_title

_TITLE_HOOK_FORMULAS = (
    "【高点击标题模板】择最适合口播内容的一种强化（可组合，总字数仍须≤上限）："
    "①误区反问式：「你以为X？其实Y」「X不是Y，而是Z」「别再把X当Y了」；"
    "②反差好奇式：「X竟然会Y」「原来X是这样」「X背后藏着Y」；"
    "③悬念具象式：用具体场景/名词开头（如「雪崩瞬间」「磁铁靠近」），"
    "后半补反差或疑问（「为啥会…」「千万别…」「真相是…」）；"
    "④对话反转式：先抛出一个事件或矛盾（常用问号），再用带态度的口语回应——自信、调侃、挑衅，不要平淡陈述。如「日本断供光刻胶？中国的五年产能等你呢」「限芯令升级？华为笑而不语」；"
    "⑤对比打脸式：「X说Y，结果Z」「号称X，实际Y」，适合辟谣或反转类内容。"
)

_TITLE_TECHNIQUES = (
    "【写法技巧】"
    "前 8～12 字承载最大钩子（移动端封面第一眼）；"
    "用具体名词、数字、对比替代空泛词（禁用「小知识」「了解一下」「科普」作主体）；"
    "可用轻疑问、轻否定、轻反差，禁止标题党（震惊、绝绝子、不转不是、99%的人都）；"
    "禁止平淡陈述（「关于X的介绍」「X原理解读」「X是怎么回事」）。"
    "若口播为儿童科普口吻，标题面向家长/学生点击：好奇悬念优先，勿装婴儿语。"
)

_TITLE_SELF_CHECK = (
    "【输出前自检】"
    "① 3 秒内能否让人想问「真的吗/为什么」；"
    "② 是否比初稿更有信息增量或情绪张力；"
    "③ 是否未超出字数、未编造口播未提及的事实。"
)

# 对于已是对话反转式风格（含？和嘲讽语气）的初稿，保留其风格，仅优化字数
_DIALOGUE_RETENTION_NOTE = (
    "注意：如果初稿已经是「事件？嘲讽回应」格式（如「日本断供光刻胶？仓库堆成山了」），"
    "优化时后半句只删字不换字，保持原意和态度不变。超过字数就删末尾字，不要改写。"
)


def build_title_optimize_system_prompt(*, max_title_len: int) -> str:
    return (
        "你是 B 站科普短视频标题优化师。根据初稿标题与口播内容，输出 JSON，字段 title。"
        f"title 为优化后的视频标题：不含空格换行，≤{max_title_len} 字，适合封面最多三行展示。"
        "若初稿含冒号（：）、问号等标点，优化后须保留，勿删除。"
        "优化目标：显著提升点击欲，保留核心主题，让人忍不住点进来看答案。"
        f"{_TITLE_HOOK_FORMULAS}"
        f"{_TITLE_TECHNIQUES}"
        f"{_TITLE_SELF_CHECK}"
        f"{_DIALOGUE_RETENTION_NOTE}"
        "不得改变口播主题方向，不得引入口播未涉及的新概念或虚假夸张。"
        "硬性禁止：医疗养生、理财股市、时政情感、热点新闻、真人出镜、无法核验的争议。"
        'JSON 输出样例：{"title": "优化后标题"}'
    )


def build_title_optimize_user_prompt(
    *,
    draft_title: str,
    narration: str,
    max_title_len: int,
) -> str:
    snippet = narration.strip().replace("\n", "")
    if len(snippet) > 500:
        snippet = snippet[:500] + "…"
    return (
        f"初稿标题：{draft_title}\n"
        f"口播内容（用于提炼最强钩子，勿照搬长句）：{snippet}\n\n"
        "请先从口播中找出 1 个最强反常识点、反差或悬念，再据此写 title。"
        f"要求比初稿「{draft_title}」更有点击欲；若初稿已平淡，须明显改写而非换同义词。"
        f"输出 ≤{max_title_len} 字的 title。"
    )


def parse_title_optimize_payload(raw: dict[str, Any], *, max_title_len: int) -> str:
    title = raw.get("title")
    if not isinstance(title, str) or not title.strip():
        raise ValueError("LLM title optimize response missing title")
    return normalize_title(title, max_len=max_title_len)
