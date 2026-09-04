"""O 类观感 profile（目标错位）。"""

from __future__ import annotations

from app.services.daily_story.story_types.o import humor as o_humor
from app.services.daily_story.story_types.o import opening as o_opening
from app.services.daily_story.story_types.o.validate import (
    RE_A_BACKFIRE,
    RE_GAME_RULE,
    RE_GOAL_PUNCH,
    RE_PRIZE_GONE,
    RE_PROCESS_FOCUS,
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
    if RE_A_BACKFIRE.search(tail6):
        return 0, ["O收束含A式反噬标记"]

    has_process = bool(
        RE_GAME_RULE.search(body) or RE_PROCESS_FOCUS.search(body)
    )
    has_gone = bool(RE_PRIZE_GONE.search(body))
    has_punch = bool(
        RE_GOAL_PUNCH.search(body) or RE_GOAL_PUNCH.search(tail6)
    )
    if not (has_gone and (has_process or has_punch)):
        return 0, []

    bonus = 0
    details: list[str] = []
    if has_process:
        details.append("立规死磕过程")
    if has_gone:
        bonus = 5
        details.append("资源溜走")
    if has_punch:
        bonus = 8 if has_gone else 5
        details.append("点题认栽")
    elif has_gone:
        details.append("缺点题落点")

    return bonus, details


QUALITY_PROFILE = TypeQualityProfile(
    code="O",
    score_punchline=score_punchline,
    closing_pro_markers=("光顾着赢", "没了", "只剩", "白赢", "偷笑"),
    summary_highlight_tokens=(
        "推进",
        "立规",
        "死磕",
        "溜走",
        "点题",
        "错位",
    ),
    punch_before_soft_markers=SHARED_PUNCH_SOFT
    + (
        "光顾着赢",
        "没了",
        "只剩",
        "白赢",
    ),
    mom_lines_penalty_at=3,
    penalize_wait_mom_end=False,
    penalize_stubborn_end=False,
    penalize_mom_judge=False,
    collect_humor_issues=o_humor.collect_o_humor_issues,
    score_opening_quality=o_opening.score_opening_quality,
    score_funniness_tail=o_humor.score_funniness_tail,
)
