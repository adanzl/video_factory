"""I 类观感 profile（问倒收束）。"""

from __future__ import annotations

from app.services.daily_story.story_types.i import humor as i_humor
from app.services.daily_story.story_types.i import opening as i_opening
from app.services.daily_story.story_types.i.validate import (
    RE_A_BACKFIRE,
    RE_SOUL_QUESTION,
    RE_SPEECHLESS,
    RE_WIN_STUBBORN,
)
from app.services.daily_story.story_types.quality import (
    SHARED_PUNCH_SOFT,
    TypeQualityProfile,
)

_I_CLOSING_TAIL_ALLOW = 2


def score_i_trailing_tail(lines: list[str]) -> tuple[int, list[str]]:
    """pass2：一招制敌后拖尾轻扣（结构分，非 punchline 满扣）。"""
    win_indices = [i for i, ln in enumerate(lines) if RE_WIN_STUBBORN.search(ln)]
    win_idx = win_indices[-1] if win_indices else -1
    if win_idx < 0:
        return 0, []
    trailing = len(lines) - win_idx - 1
    extra = trailing - _I_CLOSING_TAIL_ALLOW
    if extra <= 0:
        return 0, []
    deduction = min(4, extra * 2)
    return deduction, [f"I收束后拖尾（-{deduction}）"]


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
    if RE_A_BACKFIRE.search(tail6):
        return 0, ["I收束含A式反噬标记"]

    has_question = bool(RE_SOUL_QUESTION.search(body))
    has_speechless = bool(RE_SPEECHLESS.search(body))
    has_win = bool(RE_WIN_STUBBORN.search(tail6))
    if not has_question or not has_speechless:
        return 0, []

    bonus = 0
    details: list[str] = ["灵魂拷问落位", "对方语塞"]
    if has_win:
        bonus = 8
        details.append("赢家一招制敌")
    else:
        bonus = 5
        details.append("缺赢家一招制敌")

    return bonus, details


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
    penalize_stubborn_end=False,
    penalize_mom_judge=False,
    collect_humor_issues=i_humor.collect_i_humor_issues,
    score_opening_quality=i_opening.score_opening_quality,
    score_funniness_tail=i_humor.score_funniness_tail,
)
