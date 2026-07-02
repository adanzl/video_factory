"""科学原理分类打分。"""

from __future__ import annotations

import re

from app.services.topic.scorers.base import (
    CURIOSITY_PATTERNS,
    ScoreResult,
    check_conversational_rebuttal,
    check_hard_reject,
    check_open_faq_title,
    finalize_score,
    has_pattern,
)

SCIENCE_VISUAL = (
    r"水|电|温度|气压|化学|光|磁|电池|网线|宽带|路由器|不锈钢|玻璃|塑料|芯片|光刻|半导体|"
    r"产能|仓库|产线|工厂|胶|禁运|限芯|禁令|断供|震|地震|烈度|震级|地震波|能量",
)

LIFE_VISUAL = (
    r"空调|暖气|制冷|凉快|省电|电费|电表|家居|厨房|洗衣机|冰箱|热水器|WiFi|网速",
)


def score_science(
    title: str,
    *,
    category: str | None = None,
    template: str | None = None,
    hook: str | None = None,
) -> ScoreResult:
    text = title.strip()
    combined = f"{text} {hook or ''}"
    rejected = check_hard_reject(combined)
    if rejected:
        return rejected
    rejected = check_open_faq_title(text, category=category)
    if rejected:
        return rejected
    rejected = check_conversational_rebuttal(text)
    if rejected:
        return rejected

    visual = 70.0
    visual_bonus = 0
    if has_pattern(text, SCIENCE_VISUAL):
        visual_bonus = max(visual_bonus, 15)
    if has_pattern(text, LIFE_VISUAL):
        visual_bonus = max(visual_bonus, 15)
    if re.search(r"热|冷|暑|寒", text):
        visual_bonus = max(visual_bonus, 12)
    visual += visual_bonus
    if len(text) > 28:
        visual -= 10

    fact = 65.0 + 15
    if template in {"误区反问式", "实操避坑式"}:
        fact += 5

    curiosity = 50.0
    if has_pattern(text, CURIOSITY_PATTERNS):
        curiosity += 30
    if "?" in text or "？" in text:
        curiosity += 8
        if any(kw in text for kw in ("明明", "真以为", "天真", "慌了", "堆成山")):
            curiosity += 7
    if template == "反差好奇式":
        curiosity += 10
    if hook and len(hook) >= 10:
        curiosity += 5

    compliance = 80.0
    return finalize_score(visual=visual, fact=fact, curiosity=curiosity, compliance=compliance)
