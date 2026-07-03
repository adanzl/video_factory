"""选题提示词拼装：通用 + 格式 + 分类专属。"""

from __future__ import annotations

import re

from app.services.topic.catalog import (
    CATEGORY_CURRENT,
    CATEGORY_HISTORY,
    CATEGORY_SCIENCE,
    distribute_templates,
    get_category_spec,
    resolve_category,
)
from app.services.topic.prompts.common import (
    COMMON_COMPLIANCE_RULE,
    COMMON_PRODUCTION_RULE,
    CONVERSATIONAL_TITLE_RULE,
    CURRENT_THEME_ANCHOR_RULE,
    CURRENT_VISUAL_ANCHOR_RULE,
    FORBIDDEN_FAQ_TITLE_RULE,
    HOOK_MOTIVATION_RULE,
    VISUAL_ANCHOR_RULE,
)
from app.services.topic.prompts.format import optimize_json_format, topic_json_format
from app.services.topic.text import (
    conversational_rewrite_example,
    needs_conversational_rewrite,
)

_CONVERSATIONAL_TITLE_RE = re.compile(r"[？?]")


def _parse_keywords(keywords: str | list[str] | None) -> list[str]:
    if not keywords:
        return []
    if isinstance(keywords, str):
        parts = re.split(r"[,，、\s]+", keywords.strip())
        return [p.strip() for p in parts if p.strip()]
    return [str(k).strip() for k in keywords if str(k).strip()]


def _category_rules(category: str) -> str:
    if category == CATEGORY_HISTORY:
        return (
            "标题格式：历史代号 + 一句话悬念，"
            "如「烛影斧声：宋太祖半夜暴毙」「雍正暴毙：圆明园咯血无人敢近」。"
            "必须包含反常画面，不笼统。"
            "选知名历史人物（慈禧、和珅、秦始皇、雍正、杨贵妃、崇祯、曹操、成吉思汗等）。"
            "标题须含具体反转或矛盾细节，写不下的放进 hook。"
        )
    if category == CATEGORY_CURRENT:
        return (
            "从时事/热议现象抽出长尾科普角度，标题不写具体日期、人名、赛果、官宣。"
            f"{CURRENT_THEME_ANCHOR_RULE}"
            f"{CONVERSATIONAL_TITLE_RULE}"
            f"{FORBIDDEN_FAQ_TITLE_RULE}"
            f"{VISUAL_ANCHOR_RULE}"
            f"{CURRENT_VISUAL_ANCHOR_RULE}"
            "剥离时效后讲清原理、规则或误区，适合长期搜索。"
        )
    return (
        f"{CONVERSATIONAL_TITLE_RULE}"
        f"{FORBIDDEN_FAQ_TITLE_RULE}"
        f"{VISUAL_ANCHOR_RULE}"
        "字不够可以略写，态度要够。"
    )


def _template_instruction(category: str, templates: list[str]) -> str:
    spec = get_category_spec(category)
    if len(set(templates)) == 1:
        name = templates[0]
        hint = next((t.hint for t in spec.templates if t.name == name), "")
        return f"每条 title 的 template 固定为「{name}」。" + (f"结构提示：{hint}。" if hint else "")

    lines = ["按下列模板分配生成（每条 title 的 template 须与分配一致）："]
    for idx, name in enumerate(templates, start=1):
        hint = next((t.hint for t in spec.templates if t.name == name), "")
        lines.append(f"{idx}. template={name}" + (f"（{hint}）" if hint else ""))
    return "\n".join(lines)


def _needs_optimize_conversational_rewrite(
    title: str,
    *,
    category: str,
    template: str | None,
) -> bool:
    if needs_conversational_rewrite(title, category=category, template=template):
        return True
    if category in {CATEGORY_SCIENCE, CATEGORY_CURRENT}:
        return "?" not in title and "？" not in title
    return False


def _conversational_rewrite_instruction(title: str) -> str:
    example = conversational_rewrite_example(title)
    return (
        "【格式最优先】优化后 title 必须含中文问号「？」，"
        "且写成一整句「误区问句？一步反驳」。"
        "禁止输出无问号陈述句（如「霍尔木兹只有一条航道」）、半句问法、仅语气词收尾。"
        "反驳可用：够你跑路、真以为、压根、根本不是、哪有那么…，"
        "勿句句以「明明」开头，也忌说教建议（足够你躲桌下）。"
        "反驳半句须承接问句同一命题；问句与回应措辞须与原标题不同，但结构必须是「？+反驳」。"
        f"同一主题合格示例：{example}"
    )


def _optimize_system_conversational_block() -> str:
    return (
        "【格式最优先】优化后 title 必须是一整句「误区问句？一步反驳」，"
        "无中文问号「？」的陈述句一律不合格。"
        "在保持该结构前提下，再改进画面锚点与 hook；禁止换题或蹭热点。"
    )


def _visual_anchor_instruction() -> str:
    return (
        "【画面锚点】从本题主题提炼可见载体写进 title，配合图解词（规则、能量、表…），"
        "禁止抽象比喻（油路、命脉、博弈）；须能据此想象分镜首帧。"
    )


def build_topic_system_prompt(
    *,
    max_title_len: int,
    category: str | None = None,
    keywords: str | list[str] | None = None,
    count: int = 10,
) -> str:
    resolved = resolve_category(category)
    spec = get_category_spec(resolved)
    templates = distribute_templates(resolved, count)
    kw_note = ""
    parsed_kw = _parse_keywords(keywords)
    if parsed_kw:
        kw_note = f"用户关键词须融入标题或 keywords 字段：{', '.join(parsed_kw)}。"

    return (
        f"你是 {spec.role}。"
        f"{topic_json_format(max_title_len=max_title_len, category_value=resolved)}"
        f"{COMMON_PRODUCTION_RULE}"
        f"{COMMON_COMPLIANCE_RULE}"
        f"{HOOK_MOTIVATION_RULE}"
        f"{_category_rules(resolved)}"
        f"template 从分类模板中选取：{', '.join(spec.template_names)}。"
        f"{_template_instruction(resolved, templates)}"
        f"{kw_note}"
    )


def build_topic_user_prompt(
    *,
    category: str | None = None,
    theme: str = "",
    count: int = 10,
    keywords: str | list[str] | None = None,
) -> str:
    resolved = resolve_category(category)
    spec = get_category_spec(resolved)
    templates = distribute_templates(resolved, count)
    parsed_kw = _parse_keywords(keywords)

    lines: list[str] = [f"大分类：{spec.label}"]
    theme_text = theme.strip()
    if theme_text:
        lines.append(f"主题方向：{theme_text}")
        if resolved == CATEGORY_CURRENT:
            lines.append(
                f"硬性：须紧扣主题「{theme_text}」抽科普角度，"
                "禁止换成无关泛科普；title 不写国名/日期，hook 须点明时事锚点。"
            )
            lines.append(
                "硬性：title 的可画名词须从本题科普角度提炼，"
                "配合图解词（规则、能量、表…），禁止抽象比喻或套无关固定词。"
            )
        else:
            lines.append(f"硬性：标题须紧扣主题方向「{theme_text}」。")
    elif spec.default_theme:
        lines.append(f"主题方向：{spec.default_theme}")
    if parsed_kw:
        lines.append(f"关键词：{', '.join(parsed_kw)}")
    elif theme_text:
        lines.append("关键词：无（须从上述主题方向提炼，勿擅自换成其他话题）")
    else:
        lines.append(f"关键词：无（可围绕{spec.keywords_hint}自由发挥）")
    lines.append(f"请生成 {count} 个互不重复、适合 AI 全自动成片的中文视频标题。")
    if len(set(templates)) > 1:
        lines.append("模板分配：")
        for idx, name in enumerate(templates, start=1):
            lines.append(f"  {idx}. {name}")
    elif templates:
        lines.append(f"模板：{templates[0]}")
    return "\n".join(lines)


def build_topic_optimize_system_prompt(
    *,
    max_title_len: int,
    category: str | None = None,
) -> str:
    resolved = resolve_category(category)
    spec = get_category_spec(resolved)
    base = (
        f"你是 {spec.role.replace('策划', '优化师')}。输出 JSON，topics 数组仅 1 项。"
        f"{optimize_json_format(max_title_len=max_title_len, category_value=resolved)}"
        "优化规则：保持同一题材与核心概念，只改进标题吸引力与 hook，禁止换题或蹭热点。"
    )
    if resolved == CATEGORY_HISTORY:
        return (
            base
            + "须保持同一历史人物/悬案，标题仍为「代号：悬念」格式。"
            + "禁止换成现代生活或无关题材。"
        )
    if resolved == CATEGORY_CURRENT:
        return (
            base
            + _optimize_system_conversational_block()
            + f"{FORBIDDEN_FAQ_TITLE_RULE}"
            + f"{VISUAL_ANCHOR_RULE}"
            + f"{CURRENT_VISUAL_ANCHOR_RULE}"
            + f"{CURRENT_THEME_ANCHOR_RULE}"
            + f"{HOOK_MOTIVATION_RULE}"
            + "标题仍须剥离具体时效与人名。"
        )
    return (
        base
        + _optimize_system_conversational_block()
        + f"{FORBIDDEN_FAQ_TITLE_RULE}"
        + f"{VISUAL_ANCHOR_RULE}"
        + f"{HOOK_MOTIVATION_RULE}"
        + "category、template 须与用户原值一致。"
    )


def build_topic_optimize_user_prompt(
    *,
    title: str,
    category: str | None = None,
    template: str | None = None,
    hook: str | None = None,
) -> str:
    resolved = resolve_category(category)
    lines = [
        "请优化以下选题，输出 1 个新版本（topics 数组仅 1 项）。",
        "硬性要求：同一题材、同一核心知识点或事件，只润色标题与 hook，不得另起新题。",
        "标题表述须与原版不同，但读者应一眼看出是同一主题。",
        "",
        f"原标题：{title.strip()}",
        f"大分类：{resolved}",
    ]
    if template:
        lines.append(f"原模板：{template.strip()}（优化后 template 必须相同）")
    if hook:
        lines.append(f"原钩子：{hook.strip()}")
        lines.append(
            "若原 hook 说教、平淡或与 title 重复，须重写 hook："
            "用反差/追问/具体画面，遵守 hook 规则，禁止「别小看」「足够你」类表述。"
        )
    if resolved == CATEGORY_HISTORY:
        lines.append("须保持同一历史人物或悬案，标题仍为「代号：悬念」格式。")
    elif resolved in {CATEGORY_SCIENCE, CATEGORY_CURRENT}:
        lines.append(_conversational_rewrite_instruction(title.strip()))
        lines.append(
            "在保持上述「问句？反驳」结构不变的前提下改进画面锚点："
            "从本题主题提炼可见载体，配合图解词（规则、能量、表…），"
            "禁止抽象比喻（油路、命脉、博弈）。"
        )
    return "\n".join(lines)
