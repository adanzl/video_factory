"""历史悬案分类打分。"""

from __future__ import annotations

import re

from app.services.topic.scorers.base import (
    CURIOSITY_PATTERNS,
    SCORE_THRESHOLD,
    ScoreResult,
    check_hard_reject,
    finalize_score,
    has_pattern,
)

HISTORY_VISUAL = (
    r"尸|墓|棺|陵|夜|血|火|刀|毒|失踪|消失|烧|埋|挖|盗|杀|死|逃|藏|封",
)


def score_history(
    title: str,
    *,
    template: str | None = None,
    hook: str | None = None,
) -> ScoreResult:
    text = title.strip()
    combined = f"{text} {hook or ''}"
    rejected = check_hard_reject(combined)
    if rejected:
        return rejected

    visual = 70.0
    if has_pattern(text, HISTORY_VISUAL):
        visual += 20
    if "：" in text or ":" in text:
        visual += 10
    if len(text) > 28:
        visual -= 10

    fact = float(SCORE_THRESHOLD)
    if any(kw in text for kw in ("墓", "尸", "失踪", "消失", "真相", "之谜")):
        fact += 10

    curiosity = 50.0
    if has_pattern(text, CURIOSITY_PATTERNS):
        curiosity += 30
    if any(kw in text for kw in ("无人", "不敢", "消失", "失踪", "惊魂", "诡异", "反常", "到底")):
        curiosity += 10
    if template == "反差好奇式":
        curiosity += 10
    if hook and len(hook) >= 10:
        curiosity += 5

    compliance = float(SCORE_THRESHOLD)
    return finalize_score(visual=visual, fact=fact, curiosity=curiosity, compliance=compliance, title=text)
