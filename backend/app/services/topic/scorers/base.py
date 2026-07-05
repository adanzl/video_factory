"""选题打分：共用类型与工具。"""

from __future__ import annotations

import re
from dataclasses import dataclass

SCORE_THRESHOLD = 85

HARD_REJECT_PATTERNS = (
    r"医疗|养生|保健|药品|治病|手术|癌症|肿瘤",
    r"理财|股票|股市|基金|投资|赚钱|暴富",
    r"情感|离婚|出轨|明星八卦",
    r"热搜|今日|昨天|刚刚|突发",
    r"真人出镜|真人拍摄|实拍|采访",
)

TIMELY_PATTERNS = (
    r"\d{4}年|今年|去年|春节|国庆|高考季|双十一",
)

CURIOSITY_PATTERNS = (
    r"[?？]",
    r"为什么|为何|怎么|如何|居然|竟然|真相|误区|多数人|不知道|暗藏|猫腻|之谜|下落|去了哪|无人|不敢|惊魂|诡异|反常|到底",
    r"等你呢|笑而不语|就这|慌了|顶得住|备好了|悄悄|就位|后路|慌了神|怕什么|明明|真以为|天真|堆成山|管够|满仓",
)

WITTY_REBUTTAL_PATTERNS = (
    r"跑路|跑不掉|掉渣|堆成|管够|满仓|慌什么|怕什么|顶得住|没那么|哪有那么|早就|辟谣|"
    r"够你跑|笑死|离谱|玄学|扯淡|哪回事|"
    r"降维打击|反向输出|拿捏|赢麻了|教做人|上了一课",
)

BLAND_REBUTTAL_PATTERNS = (
    r"足够你|够你躲|建议你|应该注意|要注意|记得要|别忘了|标准做法|规范动作|躲桌下|趴地上",
)


@dataclass(frozen=True)
class ScoreResult:
    visual: int
    fact: int
    curiosity: int
    compliance: int
    total: int
    rejected_reason: str | None

    def to_dict(self) -> dict:
        return {
            "visual": self.visual,
            "fact": self.fact,
            "curiosity": self.curiosity,
            "compliance": self.compliance,
            "total": self.total,
            "rejected_reason": self.rejected_reason,
        }


def has_pattern(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(p, text) for p in patterns)


# 选题解析与打分共用的画面锚点词表（科学 + 时事）
VISUAL_ANCHOR_PATTERNS: tuple[str, ...] = (
    r"水|电|温度|气压|化学|光|磁|电池|地震波|能量|刻度|表|规则|分数|志愿|"
    r"震|地震|烈度|震级|空调|路由器|宽带|网线|芯片|冰箱|热水器|WiFi|网速|"
    r"玻璃|塑料|胶|产线|工厂|仓库|不锈钢|油轮|货轮|海峡|航线|航道|管道|"
    r"凉席|风扇|冰丝|降温|消暑|",
)


def has_visual_anchor(text: str) -> bool:
    return has_pattern(text, VISUAL_ANCHOR_PATTERNS)


def rebuttal_text(title: str) -> str:
    text = title.strip()
    mark_idx = max(text.rfind("？"), text.rfind("?"))
    if mark_idx < 0:
        return ""
    return text[mark_idx + 1 :].strip()


BLAND_HOOK_PATTERNS = (
    r"别小看|足够你|够你冲出|够你跑出|够你躲|应该注意|要注意|记得要|别忘了|"
    r"标准做法|规范动作|躲桌下|趴地上",
)


def hook_curiosity_adjustment(hook: str | None) -> float:
    """hook：奖励好奇表达，压低说教与复述标题口吻。"""
    text = (hook or "").strip()
    if not text:
        return 0.0
    delta = 0.0
    if has_pattern(text, CURIOSITY_PATTERNS):
        delta += 8.0
    if has_pattern(text, BLAND_HOOK_PATTERNS):
        delta -= 15.0
    if has_pattern(text, BLAND_REBUTTAL_PATTERNS):
        delta -= 12.0
    return delta


def rebuttal_tone_curiosity_adjustment(title: str) -> float:
    """反驳半句：奖励口语趣味，压低说教式建议。"""
    response = rebuttal_text(title)
    if not response:
        return 0.0
    delta = 0.0
    if has_pattern(response, WITTY_REBUTTAL_PATTERNS):
        delta += 12.0
    if has_pattern(response, BLAND_REBUTTAL_PATTERNS):
        delta -= 18.0
    return delta


def clamp(value: float) -> int:
    return max(0, min(100, round(value)))


def check_conversational_rebuttal(title: str) -> ScoreResult | None:
    """对话反转式：问号后须有实质反驳，禁止单独用语气词收尾。"""
    from app.services.topic.text import (
        conversational_rebuttal_issue,
        incomplete_conversational_issue,
    )

    text = title.strip()
    issue = incomplete_conversational_issue(text) or conversational_rebuttal_issue(text)
    if not issue:
        return None
    return ScoreResult(
        visual=0,
        fact=0,
        curiosity=0,
        compliance=0,
        total=0,
        rejected_reason=issue,
    )


def check_misconception_template(
    title: str,
    *,
    category: str | None = None,
    template: str | None = None,
) -> ScoreResult | None:
    from app.services.topic.text import misconception_template_issue

    reason = misconception_template_issue(title, category=category, template=template)
    if not reason:
        return None
    return ScoreResult(
        visual=0,
        fact=0,
        curiosity=0,
        compliance=0,
        total=0,
        rejected_reason=reason,
    )


def check_open_faq_title(title: str, *, category: str | None = None) -> ScoreResult | None:
    from app.services.topic.text import open_faq_title_issue

    reason = open_faq_title_issue(title, category=category)
    if not reason:
        return None
    return ScoreResult(
        visual=0,
        fact=0,
        curiosity=0,
        compliance=0,
        total=0,
        rejected_reason=reason,
    )


def check_hard_reject(combined: str) -> ScoreResult | None:
    for pattern in HARD_REJECT_PATTERNS:
        if re.search(pattern, combined):
            return ScoreResult(
                visual=0,
                fact=0,
                curiosity=0,
                compliance=0,
                total=0,
                rejected_reason=f"命中硬性约束：{pattern}",
            )
    return None


def _repetition_penalty(title: str) -> float:
    """同一 2/3 字词在标题中重复出现，扣好奇分。"""
    text = re.sub(r"[？?，。！…、]", "", title)
    # 3 字及以上重复，明显冗余
    for i in range(len(text) - 2):
        chunk = text[i : i + 3]
        if text.count(chunk) > 1:
            return -15.0
    # 2 字重复，轻扣
    for i in range(len(text) - 1):
        chunk = text[i : i + 2]
        if len(chunk) < 2:
            continue
        if text.count(chunk) > 1:
            return -8.0
    return 0.0


def finalize_score(
    *,
    visual: float,
    fact: float,
    curiosity: float,
    compliance: float,
    title: str = "",
) -> ScoreResult:
    curiosity += _repetition_penalty(title)
    total = clamp(visual * 0.3 + fact * 0.3 + curiosity * 0.2 + compliance * 0.2)
    rejected_reason = None
    if total < SCORE_THRESHOLD:
        rejected_reason = f"总分 {total} 低于阈值 {SCORE_THRESHOLD}"
    return ScoreResult(
        visual=clamp(visual),
        fact=clamp(fact),
        curiosity=clamp(curiosity),
        compliance=clamp(compliance),
        total=total,
        rejected_reason=rejected_reason,
    )
