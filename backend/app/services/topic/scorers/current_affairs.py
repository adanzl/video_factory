"""时事相关科普分类打分。"""

from __future__ import annotations

import re

from app.services.topic.scorers.base import (
    CURIOSITY_PATTERNS,
    TIMELY_PATTERNS,
    ScoreResult,
    check_conversational_rebuttal,
    check_hard_reject,
    check_misconception_template,
    check_open_faq_title,
    finalize_score,
    has_pattern,
    hook_curiosity_adjustment,
    rebuttal_tone_curiosity_adjustment,
)

CURRENT_VISUAL = (
    r"水|电|温度|气压|化学|光|磁|电池|地震波|能量|刻度|表|规则|分数|志愿|"
    r"震|地震|烈度|震级|空调|路由器|宽带|网线|芯片",
)


def score_current_affairs(
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
    rejected = check_misconception_template(
        text, category=category, template=template
    )
    if rejected:
        return rejected
    rejected = check_conversational_rebuttal(text)
    if rejected:
        return rejected

    visual = 70.0
    if has_pattern(text, CURRENT_VISUAL):
        visual += 15
    if re.search(r"热|冷|暑|寒", text):
        visual += 12
    if len(text) > 28:
        visual -= 10

    fact = 65.0 + 12
    if template in {"误区反问式", "反差好奇式"}:
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
    curiosity += rebuttal_tone_curiosity_adjustment(text)
    curiosity += hook_curiosity_adjustment(hook)

    compliance = 78.0
    if has_pattern(text, TIMELY_PATTERNS):
        compliance -= 35
    if has_pattern(combined, TIMELY_PATTERNS):
        compliance -= 10

    return finalize_score(visual=visual, fact=fact, curiosity=curiosity, compliance=compliance)
