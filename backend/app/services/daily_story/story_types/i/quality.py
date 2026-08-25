"""I 类观感 profile（问倒收束）。"""

from __future__ import annotations

from app.services.daily_story.story_types.i import humor as i_humor
from app.services.daily_story.story_types.i import opening as i_opening
from app.services.daily_story.story_types.i.validate import (
    RE_SOUL_QUESTION,
    RE_SPEECHLESS,
    RE_WIN_STUBBORN,
)
from app.services.daily_story.story_types.quality import (
    SHARED_PUNCH_SOFT,
    TypeQualityProfile,
)


def score_punchline(
    lines: list[str],
    speakers: list[str],
    prev2: str,
    last: str,
) -> tuple[int, list[str]]:
    del speakers, prev2, last
    n = len(lines)
    if n < 4:
        return 0, []

    body = "".join(lines)
    tail6 = "".join(lines[-6:])
    bonus = 0
    details: list[str] = []

    if RE_SOUL_QUESTION.search(body):
        bonus += 3
        details.append("灵魂拷问落位")
    if RE_SPEECHLESS.search(tail6) or RE_SPEECHLESS.search(body):
        bonus += 3
        details.append("对方语塞")
    if RE_WIN_STUBBORN.search(tail6):
        bonus += 4
        details.append("赢家一招制敌")

    return min(bonus, 8), details


QUALITY_PROFILE = TypeQualityProfile(
    code="I",
    score_punchline=score_punchline,
    closing_pro_markers=("拷问", "语塞", "一招制敌", "问倒", "制敌", "服不服"),
    summary_highlight_tokens=(
        "推进",
        "拷问",
        "语塞",
        "一招制敌",
        "价值高地",
        "双标",
    ),
    punch_before_soft_markers=SHARED_PUNCH_SOFT
    + (
        "一招制敌",
        "制敌",
        "服不服",
        "说不过",
        "不爱学习",
    ),
    mom_lines_penalty_at=5,
    penalize_wait_mom_end=False,
    penalize_split_end=False,
    penalize_stubborn_end=False,
    penalize_mom_judge=False,
    collect_humor_issues=i_humor.collect_i_humor_issues,
    score_opening_quality=i_opening.score_opening_quality,
    score_funniness_tail=i_humor.score_funniness_tail,
)
