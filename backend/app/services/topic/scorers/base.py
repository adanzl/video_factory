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
    r"为什么|怎么|如何|居然|竟然|真相|误区|多数人|不知道|暗藏|猫腻|之谜|下落|去了哪|无人|不敢|惊魂|诡异|反常|到底",
    r"等你呢|笑而不语|就这|慌了|顶得住|备好了|悄悄|就位|后路|慌了神|怕什么|明明|真以为|天真|堆成山|管够|满仓",
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


def clamp(value: float) -> int:
    return max(0, min(100, round(value)))


_ATTITUDE_ONLY_RESPONSE = re.compile(
    r"^(就这|真就这|就那样|就这些?|笑而不语|等你呢|慌了神?|顶得住|天真了?)"
    r"([吗嘛啊呢吧！？?…]*)$"
)

_REBUTTAL_CUES = re.compile(
    r"明明|根本|并非|不是|没有|从未|辟谣|谣言|误区|误会|科学依据|站不住|对不上|"
    r"监测|气象局|形态|形状|证据|仓库|堆成|产线|电表|温度|气压|地震波"
)


def check_conversational_rebuttal(title: str) -> ScoreResult | None:
    """对话反转式：问号后须有实质反驳，禁止单独用语气词收尾。"""
    text = title.strip()
    mark_idx = max(text.rfind("？"), text.rfind("?"))
    if mark_idx < 0:
        return None
    response = text[mark_idx + 1 :].strip()
    if not response:
        return ScoreResult(
            visual=0,
            fact=0,
            curiosity=0,
            compliance=0,
            total=0,
            rejected_reason="对话反转式：问号后缺少回应",
        )
    core = re.sub(r"[！!？?。，,、…\s]+$", "", response)
    if _ATTITUDE_ONLY_RESPONSE.fullmatch(core):
        return ScoreResult(
            visual=0,
            fact=0,
            curiosity=0,
            compliance=0,
            total=0,
            rejected_reason="对话反转式：问号后仅有语气词，缺少实质反驳",
        )
    if len(core) <= 4 and not _REBUTTAL_CUES.search(core):
        return ScoreResult(
            visual=0,
            fact=0,
            curiosity=0,
            compliance=0,
            total=0,
            rejected_reason="对话反转式：问号后过短且缺少反驳信息",
        )
    return None


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


def finalize_score(
    *,
    visual: float,
    fact: float,
    curiosity: float,
    compliance: float,
) -> ScoreResult:
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
