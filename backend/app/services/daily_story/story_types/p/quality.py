"""P 类观感 profile（整蛊互整）。"""

from __future__ import annotations

from app.services.daily_story.story_types.p import humor as p_humor
from app.services.daily_story.story_types.p import opening as p_opening
from app.services.daily_story.story_types.p.validate import (
    RE_A_BACKFIRE,
    RE_C_BOOMERANG,
    RE_OFFER,
    RE_RETALIATE,
    RE_SURRENDER,
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
    if RE_A_BACKFIRE.search(tail6) or RE_C_BOOMERANG.search(tail6):
        return 0, ["P收束含C/A边界标记"]

    has_offer = bool(RE_OFFER.search(body))
    has_retaliate = bool(RE_RETALIATE.search(body))
    has_surrender = bool(
        RE_SURRENDER.search(body) or RE_SURRENDER.search(tail6)
    )
    if not (has_offer and (has_retaliate or has_surrender)):
        return 0, []

    bonus = 0
    details: list[str] = []
    if has_offer:
        details.append("下料挑战")
    if has_retaliate:
        bonus = 5
        details.append("回敬加码")
    if has_surrender:
        bonus = 8 if has_retaliate else 5
        details.append("认怂散场")
    elif has_retaliate:
        details.append("缺认怂落点")

    return bonus, details


QUALITY_PROFILE = TypeQualityProfile(
    code="P",
    score_punchline=score_punchline,
    closing_pro_markers=("认输", "不了不了", "不敢再", "再试试", "也给你"),
    summary_highlight_tokens=(
        "推进",
        "下料",
        "回敬",
        "认怂",
        "整蛊",
    ),
    punch_before_soft_markers=SHARED_PUNCH_SOFT
    + (
        "认输",
        "不了不了",
        "不敢再",
        "再试试",
    ),
    mom_lines_penalty_at=3,
    penalize_wait_mom_end=False,
    penalize_stubborn_end=False,
    penalize_mom_judge=False,
    collect_humor_issues=p_humor.collect_p_humor_issues,
    score_opening_quality=p_opening.score_opening_quality,
    score_funniness_tail=p_humor.score_funniness_tail,
)
