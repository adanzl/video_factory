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
    del speakers, lines
    if RE_SOFT.search(last) or RE_SOFT.search(prev2 + last):
        return 6, ["暖收或半暖"]
    if any(m in last for m in SHARED_PUNCH_SOFT):
        return 3, ["软收束"]
    return 0, []


QUALITY_PROFILE = TypeQualityProfile(
    code="G",
    score_punchline=score_punchline,
    closing_pro_markers=("暖收", "半暖", "撑腰", "擦药", "说好了", "软化", "pivot"),
    summary_highlight_tokens=(
        "推进",
        "护短",
        "pivot",
        "暖收",
        "愣住",
        "数落",
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
    ),
    penalize_stubborn_end=False,
    collect_humor_issues=g_humor.collect_g_humor_issues,
    score_scene_beat=score_scene_beat,  # type: ignore[union-attr]
)
