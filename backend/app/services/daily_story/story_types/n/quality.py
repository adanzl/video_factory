"""N 类观感 profile（正经胡说）。"""

from __future__ import annotations

from app.services.daily_story.story_types.n import humor as n_humor
from app.services.daily_story.story_types.n import opening as n_opening
from app.services.daily_story.story_types.n.validate import (
    RE_A_BACKFIRE,
    RE_CHALLENGE,
    RE_SOLEMN_REASON,
    RE_STUN_CLOSE,
    RE_WHY,
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
        return 0, ["N收束含A式反噬标记"]

    has_q = bool(RE_CHALLENGE.search(body) and RE_WHY.search(body))
    has_reason = bool(RE_SOLEMN_REASON.search(body))
    has_stun = bool(RE_STUN_CLOSE.search(body) or RE_STUN_CLOSE.search(tail6))
    if not (has_reason and (has_q or has_stun)):
        return 0, []

    bonus = 0
    details: list[str] = []
    if has_q:
        details.append("设问追问链")
    if has_reason:
        bonus = 5
        details.append("一本正经自洽")
    if has_stun:
        bonus = 8 if has_reason else 5
        details.append("愣住收束")
    elif has_reason:
        details.append("缺愣住落点")

    return bonus, details


QUALITY_PROFILE = TypeQualityProfile(
    code="N",
    score_punchline=score_punchline,
    closing_pro_markers=("因为", "所以", "愣", "服了", "行吧", "哭笑", "自洽"),
    summary_highlight_tokens=(
        "推进",
        "设问",
        "追问",
        "胡说",
        "自洽",
        "愣住",
    ),
    punch_before_soft_markers=SHARED_PUNCH_SOFT
    + (
        "因为",
        "所以",
        "就能",
        "行吧",
        "服了",
    ),
    mom_lines_penalty_at=3,
    penalize_wait_mom_end=False,
    penalize_stubborn_end=False,
    penalize_mom_judge=False,
    collect_humor_issues=n_humor.collect_n_humor_issues,
    score_opening_quality=n_opening.score_opening_quality,
    score_funniness_tail=n_humor.score_funniness_tail,
)
