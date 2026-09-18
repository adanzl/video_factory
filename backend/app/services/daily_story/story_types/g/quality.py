"""G 类观感 profile。"""

from __future__ import annotations

from app.services.daily_story.story_types.g import humor as g_humor
from app.services.daily_story.story_types.quality import (
    SHARED_PUNCH_SOFT,
    TypeQualityProfile,
)

RE_PIVOT = g_humor.RE_PIVOT
RE_SOFT = g_humor.RE_SOFT


def score_scene_beat(
    lines: list[str],
    *,
    text_has_hammer_beat,
) -> tuple[int, list[str]]:
    del text_has_hammer_beat
    body = "".join(lines)
    reasons: list[str] = []
    score = 0
    if g_humor.authority_punchline_slots_hit(lines):
        if g_humor.RE_AUTH_RULE.search(body):
            score += 2
            reasons.append("立规约好")
        if g_humor.RE_AUTH_REVERSE.search(body):
            score += 3
            reasons.append("反将任务")
        if g_humor.RE_AUTH_CEDE.search(body):
            score += 3
            reasons.append("认怂让渡")
        if g_humor.RE_AUTH_PUNCH.search(body):
            score += 3
            reasons.append("权威点题")
        return score, reasons
    if g_humor.RE_ESCALATE.search(body):
        score += 3
        reasons.append("数落升级")
    if RE_PIVOT.search(body):
        score += 5
        reasons.append("护短 pivot")
    if g_humor.RE_STUNNED.search(body):
        score += 3
        reasons.append("愣住 beat")
    return score, reasons


def score_punchline(
    lines: list[str],
    speakers: list[str],
    prev2: str,
    last: str,
) -> tuple[int, list[str]]:
    del speakers
    if g_humor.authority_punchline_slots_hit(lines):
        tail = prev2 + last
        if g_humor.RE_AUTH_PUNCH.search(last) or g_humor.RE_AUTH_PUNCH.search(tail):
            return 8, ["权威点题收束"]
        if g_humor.RE_AUTH_CEDE.search(tail):
            return 4, ["让渡后点题偏弱"]
        return 0, []
    if RE_SOFT.search(last) or RE_SOFT.search(prev2 + last):
        return 6, ["暖收或半暖"]
    if any(m in last for m in SHARED_PUNCH_SOFT):
        return 3, ["软收束"]
    return 0, []


QUALITY_PROFILE = TypeQualityProfile(
    code="G",
    score_punchline=score_punchline,
    # 权威点题旁路常需妈妈 2–3 句点题；真 G 仍宜少妈妈句
    mom_lines_penalty_at=4,
    closing_pro_markers=(
        "暖收",
        "半暖",
        "撑腰",
        "擦药",
        "说好了",
        "软化",
        "pivot",
        "权威点题",
        "反将",
        "让渡",
    ),
    summary_highlight_tokens=(
        "推进",
        "护短",
        "pivot",
        "暖收",
        "愣住",
        "数落",
        "反将",
        "让渡",
        "点题",
    ),
    punch_before_soft_markers=SHARED_PUNCH_SOFT
    + (
        "护",
        "撑腰",
        "拼命",
        "你说啥",
        "擦",
        "药",
        "重要",
        "舍不得",
        "在乎",
        "记住",
        "并列",
        "这个家",
        "这个班",
    ),
    penalize_stubborn_end=False,
    collect_humor_issues=g_humor.collect_g_humor_issues,
    score_scene_beat=score_scene_beat,  # type: ignore[union-attr]
)
