"""H 类观感 profile（第三方化解）。"""

from __future__ import annotations

from app.services.daily_story.story_types.h import humor as h_humor
from app.services.daily_story.story_types.h import opening as h_opening
from app.services.daily_story.story_types.h.validate import (
    RE_MOM_MEDIATE,
    RE_RECONCILE,
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
    del prev2
    n = len(lines)
    if n < 4:
        return 0, []

    tail4 = "".join(lines[-4:])
    tail6 = "".join(lines[-6:])
    bonus = 0
    details: list[str] = []

    if RE_RECONCILE.search(tail4):
        bonus += 6
        details.append("仪式性和好")
    if RE_MOM_MEDIATE.search(tail6):
        bonus += 4
        details.append("第三方调解")
    if speakers and speakers[-1] != "妈妈" and RE_RECONCILE.search(tail4):
        bonus += 2
        details.append("末句姐弟收场")

    return bonus, details


QUALITY_PROFILE = TypeQualityProfile(
    code="H",
    score_punchline=score_punchline,
    closing_pro_markers=("和好", "调解", "仪式", "拉手", "不打了", "碘伏"),
    summary_highlight_tokens=(
        "升级",
        "调解",
        "和好",
        "仪式",
        "定责",
        "互毁",
    ),
    punch_before_soft_markers=SHARED_PUNCH_SOFT
    + (
        "拉手",
        "不打了",
        "对不起",
        "碘伏",
        "涂药",
    ),
    mom_lines_penalty_at=5,
    penalize_wait_mom_end=False,
    penalize_split_end=False,
    penalize_stubborn_end=False,
    penalize_mom_judge=False,
    collect_humor_issues=h_humor.collect_h_humor_issues,
    score_opening_quality=h_opening.score_opening_quality,
    score_funniness_tail=h_humor.score_funniness_tail,
)
