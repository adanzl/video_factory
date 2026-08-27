"""J 类观感 profile（权威压住）。"""

from __future__ import annotations

from app.services.daily_story.story_types.j import humor as j_humor
from app.services.daily_story.story_types.j import opening as j_opening
from app.services.daily_story.story_types.j.validate import (
    RE_A_BACKFIRE,
    RE_HOLD,
    RE_PLEAD,
    RE_SURRENDER,
    RE_VETO,
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
        return 0, ["J收束含A式反噬标记"]

    has_plead = bool(RE_PLEAD.search(body))
    has_veto = bool(RE_VETO.search(body))
    has_surrender = bool(RE_SURRENDER.search(body))
    has_hold = bool(RE_HOLD.search(tail6))
    if not has_plead or not has_veto:
        return 0, []

    bonus = 0
    details: list[str] = ["否决压住落位"]
    if has_surrender:
        details.append("对方怂退")
    if has_hold:
        bonus = 8
        details.append("镇住收场")
    else:
        bonus = 5
        details.append("缺镇住收场")

    return bonus, details


def humor_revision_hint(issue_text: str) -> str | None:
    if "镇住" in issue_text or "收束" in issue_text:
        return "【J收束】末段灿灿仍占上风（我说了算/反正…），昭昭怂退；勿 A 破功。"
    if "否决" in issue_text or "推进" in issue_text:
        return "【J推进】补一锤否决（不行/我说了算），哀求仍无效。"
    return None


QUALITY_PROFILE = TypeQualityProfile(
    code="J",
    score_punchline=score_punchline,
    closing_pro_markers=("镇住", "压住", "我说了算", "否决", "怂退", "权威"),
    summary_highlight_tokens=(
        "求放行",
        "否决",
        "镇住",
        "怂退",
        "权威",
        "妈妈说",
    ),
    punch_before_soft_markers=SHARED_PUNCH_SOFT
    + (
        "我说了算",
        "不同意",
        "不行就不行",
        "反正",
    ),
    mom_lines_penalty_at=4,
    penalize_wait_mom_end=False,
    penalize_split_end=False,
    penalize_stubborn_end=False,
    penalize_mom_judge=False,
    collect_humor_issues=j_humor.collect_j_humor_issues,
    score_opening_quality=j_opening.score_opening_quality,
    score_funniness_tail=j_humor.score_funniness_tail,
    humor_revision_hint=humor_revision_hint,
)
