"""K 类观感 profile（家长看戏）。"""

from __future__ import annotations

from app.services.daily_story.story_types.k import humor as k_humor
from app.services.daily_story.story_types.k import opening as k_opening
from app.services.daily_story.story_types.k.validate import (
    RE_A_BACKFIRE,
    RE_FIGHT,
    RE_H_RECONCILE,
    RE_PARENT_FAIL,
    RE_STALEMATE,
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
        return 0, ["K收束含A式反噬标记"]
    if RE_H_RECONCILE.search(tail6):
        return 0, ["K收束含H式和好"]

    has_fight = bool(RE_FIGHT.search(body))
    has_fail = bool(RE_PARENT_FAIL.search(body))
    has_stale = bool(RE_STALEMATE.search(tail6))
    if not has_fight:
        return 0, []

    bonus = 0
    details: list[str] = ["互骂升级落位"]
    if has_fail:
        details.append("大人劝失败")
    if has_stale:
        bonus = 8
        details.append("僵持不和好")
    else:
        bonus = 5
        details.append("缺僵持收场")

    return bonus, details


def humor_revision_hint(issue_text: str) -> str | None:
    if "和好" in issue_text or "收束" in issue_text:
        return "【K收束】末段僵持不和好；勿拉手/不打了/和好。"
    if "劝" in issue_text or "推进" in issue_text:
        return "【K推进】补大人劝失败（叹气/管不了），越劝越凶更佳。"
    return None


QUALITY_PROFILE = TypeQualityProfile(
    code="K",
    score_punchline=score_punchline,
    closing_pro_markers=("僵持", "劝失败", "不和好", "看戏", "越劝越", "不理"),
    summary_highlight_tokens=(
        "互骂",
        "升级",
        "劝失败",
        "僵持",
        "看戏",
        "不和好",
    ),
    punch_before_soft_markers=SHARED_PUNCH_SOFT
    + (
        "不和好",
        "别理",
        "越劝越",
        "管不了",
    ),
    mom_lines_penalty_at=5,
    penalize_wait_mom_end=False,
    penalize_split_end=False,
    penalize_stubborn_end=False,
    penalize_mom_judge=False,
    collect_humor_issues=k_humor.collect_k_humor_issues,
    score_opening_quality=k_opening.score_opening_quality,
    score_funniness_tail=k_humor.score_funniness_tail,
    humor_revision_hint=humor_revision_hint,
)
