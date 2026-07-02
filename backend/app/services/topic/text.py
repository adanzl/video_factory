"""选题标题文本规范化与结构校验。"""

from __future__ import annotations

import re

from app.services.topic.catalog import CATEGORY_HISTORY, resolve_category

_OPEN_FAQ_PATTERNS = re.compile(
    r"能提前多久|提前多久|能预警多久|预警能.{0,4}多久|"
    r"能管多久|能撑多久|能坚持多久|能活多久|能存多久|"
    r"^[^？?：:]{2,16}是什么$|"
    r"有什么用|有何用|干嘛用|作何用|"
    r"是多少|有多少|几[秒分天时]钟|多长时间"
)

_ATTITUDE_ONLY_RESPONSE = re.compile(
    r"^(就这|真就这|就那样|就这些?|笑而不语|等你呢|慌了神?|顶得住|天真了?)"
    r"([吗嘛啊呢吧！？?…]*)$"
)

_REBUTTAL_CUES = re.compile(
    r"明明|根本|并非|不是|没有|从未|辟谣|谣言|误区|误会|科学依据|站不住|对不上|"
    r"监测|气象局|形态|形状|证据|仓库|堆成|产线|电表|温度|气压|地震波"
)


def open_faq_title_issue(title: str, *, category: str | None = None) -> str | None:
    """科学/时事类禁止百科式中性提问（无误区、无反驳落点）。"""
    if resolve_category(category) == CATEGORY_HISTORY:
        return None
    text = title.strip()
    if not text:
        return None
    # 问句含 FAQ 关键词但已有完整反驳半句时允许（如「能提前多久？明明只有几十秒」）
    if incomplete_conversational_issue(text) is None:
        mark_idx = max(text.rfind("？"), text.rfind("?"))
        if mark_idx >= 0 and text[mark_idx + 1 :].strip():
            return None
    if _OPEN_FAQ_PATTERNS.search(text):
        return "百科式中性提问：缺少误区反驳或反差结构"
    return None


def misconception_template_issue(
    title: str,
    *,
    category: str | None = None,
    template: str | None = None,
) -> str | None:
    """误区反问式须为问号对话体，禁止纯陈述句。"""
    if resolve_category(category) == CATEGORY_HISTORY:
        return None
    if template != "误区反问式":
        return None
    text = title.strip()
    if not text:
        return None
    if "?" not in text and "？" not in text:
        return "误区反问式：须为问号对话体且含实质反驳"
    return None


def incomplete_conversational_issue(title: str) -> str | None:
    """对话反转式禁止半句问法（问号后无回应）。"""
    text = title.strip()
    mark_idx = max(text.rfind("？"), text.rfind("?"))
    if mark_idx < 0:
        return None
    if not text[mark_idx + 1 :].strip():
        return "对话反转式：问号后缺少回应"
    return None


def conversational_rebuttal_issue(title: str) -> str | None:
    """对话反转式：问号后须有实质反驳，禁止单独用语气词收尾。"""
    text = title.strip()
    mark_idx = max(text.rfind("？"), text.rfind("?"))
    if mark_idx < 0:
        return None
    response = text[mark_idx + 1 :].strip()
    if not response:
        return None
    core = re.sub(r"[！!？?。，,、…\s]+$", "", response)
    if _ATTITUDE_ONLY_RESPONSE.fullmatch(core):
        return "对话反转式：问号后仅有语气词，缺少实质反驳"
    if len(core) <= 4 and not _REBUTTAL_CUES.search(core):
        return "对话反转式：问号后过短且缺少反驳信息"
    return None


def topic_title_issue(
    title: str,
    *,
    category: str | None = None,
    template: str | None = None,
) -> str | None:
    """汇总选题标题在解析阶段的全部拒绝原因。"""
    text = title.strip()
    if not text:
        return "标题为空"
    for issue in (
        open_faq_title_issue(text, category=category),
        misconception_template_issue(text, category=category, template=template),
        incomplete_conversational_issue(text),
        conversational_rebuttal_issue(text),
    ):
        if issue:
            return issue
    return None


def conversational_rewrite_example(title: str) -> str:
    """为无问号标题生成对话反转改写示例（仅用于提示词）。"""
    base = _rewrite_base(title)
    if not base:
        return "误区挺大？压根不是那么回事"

    rules: list[tuple[str, list[str]]] = [
        (
            r"动物",
            [
                "{base}？监测数据压根对不上",
                "真以为动物能预警？压根没科学依据",
            ],
        ),
        (
            r"云",
            [
                "{base}？气象局早辟谣了",
                "真以为看云就行？压根没依据",
            ],
        ),
        (
            r"钱|砸钱|靠钱|堆钱|有钱",
            [
                "{base}？秒级靠的是地震波",
                "真以为靠砸钱就行？差的是地震波那几秒",
            ],
        ),
        (
            r"几十秒|几秒|秒|提前多久|来得及|来不及|多久",
            [
                "{base}？够你跑路的",
                "真以为来不及？几十秒够躲",
            ],
        ),
        (
            r"预警|地震",
            [
                "{base}？靠的是监测网不是玄学",
                "真以为预警没用？秒级差在地震波",
            ],
        ),
        (
            r"光刻|芯片|断供|仓库",
            [
                "{base}？仓库都堆成山了",
                "真以为会断供？产线根本管够",
            ],
        ),
    ]
    for pattern, templates in rules:
        if re.search(pattern, base):
            return templates[hash(base) % len(templates)].format(base=base)

    defaults = [
        f"{base}？压根没那么玄乎",
        f"真以为{base}？哪有那么夸张",
        f"{base}？根本站不住",
    ]
    return defaults[hash(base) % len(defaults)]


def _rewrite_base(title: str) -> str:
    base = re.sub(r"\s+", "", title.strip())
    base = re.sub(r"[？?！!。…]+$", "", base)
    return re.sub(r"(吗|呢|吧|啊|嘛)$", "", base)


def needs_conversational_rewrite(
    title: str,
    *,
    category: str | None = None,
    template: str | None = None,
) -> bool:
    """科学/时事类标题是否须改成完整对话反转句式。"""
    if resolve_category(category) == CATEGORY_HISTORY:
        return False
    if open_faq_title_issue(title, category=category):
        return True
    if misconception_template_issue(title, category=category, template=template):
        return True
    if incomplete_conversational_issue(title):
        return True
    if conversational_rebuttal_issue(title):
        return True
    return False


def normalize_title(title: str, *, max_len: int) -> str:
    cleaned = re.sub(r"\s+", "", title.strip())
    if len(cleaned) <= max_len + 2:
        return cleaned
    truncated = cleaned[:max_len]
    for punct in ("。", "！", "？", "，", "——"):
        idx = truncated.rfind(punct)
        if idx >= max_len // 2:
            return truncated[:idx]
    return cleaned[:max_len]
