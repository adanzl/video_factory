"""Q 类观感 profile（耍赖翻车）。"""

from __future__ import annotations

from app.services.daily_story.story_types.q import humor as q_humor
from app.services.daily_story.story_types.q import opening as q_opening
from app.services.daily_story.story_types.q.validate import (
    RE_BACKFIRE,
    RE_CHEAT,
    RE_C_BOOMERANG,
    RE_EXPOSE,
    RE_E_MOM_BREAK,
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
    tail4 = "".join(lines[-4:])
    if RE_E_MOM_BREAK.search(tail4) or RE_C_BOOMERANG.search(tail4):
        return 0, ["Q收束含E/C边界标记"]

    has_cheat = bool(RE_CHEAT.search(body))
    has_expose = bool(RE_EXPOSE.search(body))
    has_backfire = bool(
        RE_BACKFIRE.search(body) or RE_BACKFIRE.search(tail4)
    )
    if not (has_cheat and has_expose):
        return 0, []

    bonus = 0
    details: list[str] = []
    if has_cheat:
        details.append("耍赖加码")
    if has_expose:
        bonus = 5
        details.append("被拆穿")
    if has_backfire:
        bonus = 8 if has_expose else 5
        details.append("反噬收场")
    elif has_expose:
        details.append("缺反噬落点")

    return bonus, details


QUALITY_PROFILE = TypeQualityProfile(
    code="Q",
    score_punchline=score_punchline,
    closing_pro_markers=("看穿", "拆穿", "洗碗", "活该", "心思"),
    summary_highlight_tokens=(
        "推进",
        "耍赖",
        "拆穿",
        "反噬",
        "翻车",
    ),
    punch_before_soft_markers=SHARED_PUNCH_SOFT
    + (
        "看穿",
        "拆穿",
        "洗碗",
        "活该",
    ),
    mom_lines_penalty_at=3,
    penalize_wait_mom_end=False,
    penalize_stubborn_end=False,
    penalize_mom_judge=False,
    collect_humor_issues=q_humor.collect_q_humor_issues,
    score_opening_quality=q_opening.score_opening_quality,
    score_funniness_tail=q_humor.score_funniness_tail,
)
