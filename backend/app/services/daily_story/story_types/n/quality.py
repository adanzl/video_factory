"""N 类观感 profile（正经胡说）。"""

from __future__ import annotations

from app.services.daily_story.story_types.n import humor as n_humor
from app.services.daily_story.story_types.n import opening as n_opening
from app.services.daily_story.story_types.n.validate import (
    RE_A_BACKFIRE,
    n_structure_hits,
    source_rhetorical_contract,
    stun_close_hit,
)
from app.services.daily_story.story_types.quality import (
    SHARED_PUNCH_SOFT,
    TypeQualityProfile,
)


def declared_escalation_hits(lines: list[str], story: dict) -> tuple[str, ...] | None:
    """声明形态的结构槽命中；语义是否成立仍由四项 N 终审核验。"""
    declared = story.get("gold_n_expression_contract")
    if not declared:
        return None
    if declared != source_rhetorical_contract(story.get("gold_source_line_plan")):
        return ()
    hits = (*n_structure_hits(lines, story), stun_close_hit(lines))
    return tuple(label for label, hit in zip(("设问", "追问", "反问自洽", "愣住收束"), hits) if hit)


def score_punchline(
    lines: list[str],
    speakers: list[str],
    prev2: str,
    last: str,
    *, story: dict | None = None,
) -> tuple[int, list[str]]:
    del speakers, prev2, last
    n = len(lines)
    if n < 4:
        return 0, []

    tail6 = "".join(lines[-6:])
    if RE_A_BACKFIRE.search(tail6):
        return 0, ["N收束含A式反噬标记"]

    challenge, followup, has_reason = n_structure_hits(lines, story)
    has_q = challenge and followup
    # 愣住须落在收束窗（末四拍或末三句），勿把中段「接不住」当收束达标
    has_stun_close = stun_close_hit(lines)
    if not (has_reason and (has_q or has_stun_close)):
        return 0, []

    bonus = 0
    details: list[str] = []
    if has_q:
        details.append("设问追问链")
    if has_reason:
        bonus = 5
        details.append("一本正经自洽")
    if has_stun_close:
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
