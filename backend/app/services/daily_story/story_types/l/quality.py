"""L 类观感 profile（退让点破）。"""

from __future__ import annotations

from app.services.daily_story.story_types.l import humor as l_humor
from app.services.daily_story.story_types.l import opening as l_opening
from app.services.daily_story.story_types.l.validate import (
    RE_A_BACKFIRE,
    RE_BIAS_EXPOSE,
    RE_REFUSE,
    RE_URGE_GIVE,
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
        return 0, ["L收束含A式反噬标记"]

    has_urge = bool(RE_URGE_GIVE.search(body))
    has_refuse = bool(RE_REFUSE.search(body))
    has_expose = bool(RE_BIAS_EXPOSE.search(body))
    if not (has_urge and has_refuse):
        return 0, []

    bonus = 0
    details: list[str] = ["催让渡落位", "拒收退让"]
    if has_expose:
        bonus = 8
        details.append("点破偏心收束")
    else:
        bonus = 5
        details.append("缺点破偏心落点")

    return bonus, details


QUALITY_PROFILE = TypeQualityProfile(
    code="L",
    score_punchline=score_punchline,
    closing_pro_markers=("偏心", "公平", "拒收", "退让", "语塞", "点破"),
    summary_highlight_tokens=(
        "推进",
        "催让",
        "拒收",
        "偏心",
        "退让",
        "语塞",
    ),
    punch_before_soft_markers=SHARED_PUNCH_SOFT
    + (
        "偏心",
        "哪门子公平",
        "不想",
        "你们喝吧",
        "公平压",
    ),
    mom_lines_penalty_at=3,
    penalize_wait_mom_end=False,
    penalize_stubborn_end=False,
    penalize_mom_judge=False,
    collect_humor_issues=l_humor.collect_l_humor_issues,
    score_opening_quality=l_opening.score_opening_quality,
    score_funniness_tail=l_humor.score_funniness_tail,
)
